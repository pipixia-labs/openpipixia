"""Personal WeChat (Weixin) channel adapter using HTTP long polling."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx

from ..bus.events import OutboundMessage
from ..core.config import get_data_dir
from .base import BaseChannel

logger = logging.getLogger(__name__)

ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_FINISH = 2

BASE_INFO: dict[str, str] = {"channel_version": "1.0.2"}
ERRCODE_SESSION_EXPIRED = -14
DEFAULT_LONG_POLL_TIMEOUT_S = 35


class WeixinChannel(BaseChannel):
    """Weixin adapter with QR-code login and long-poll message receive."""

    name = "weixin"

    def __init__(
        self,
        bus,
        *,
        allow_from: list[str] | None = None,
        base_url: str = "https://ilinkai.weixin.qq.com",
        token: str = "",
        state_dir: str = "",
        poll_timeout_seconds: int = DEFAULT_LONG_POLL_TIMEOUT_S,
    ) -> None:
        super().__init__(bus, allow_from=allow_from)
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self.state_dir = state_dir.strip()
        self.poll_timeout_seconds = max(int(poll_timeout_seconds), 5)
        self._client: httpx.AsyncClient | None = None
        self._token = self.token
        self._get_updates_buf = ""
        self._context_tokens: dict[str, str] = {}
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._next_poll_timeout_seconds = self.poll_timeout_seconds

    async def start(self) -> None:
        """Start long polling Weixin messages."""
        self._running = True
        self._next_poll_timeout_seconds = self.poll_timeout_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._next_poll_timeout_seconds + 10, connect=30),
            follow_redirects=True,
        )

        if not self._token and not self._load_state():
            ok = await self._qr_login()
            if not ok:
                self._running = False
                return

        consecutive_failures = 0
        while self._running:
            try:
                await self._poll_once()
                consecutive_failures = 0
            except httpx.TimeoutException:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                consecutive_failures += 1
                logger.exception("Weixin polling failed (%s/3)", consecutive_failures)
                await asyncio.sleep(30 if consecutive_failures >= 3 else 2)
                if consecutive_failures >= 3:
                    consecutive_failures = 0

    async def stop(self) -> None:
        """Stop the Weixin client and persist state."""
        self._running = False
        self._save_state()
        if self._client:
            await self._client.aclose()
            self._client = None

    async def login(self, force: bool = False) -> bool:
        """Run interactive Weixin QR-code login and persist the token."""
        if force:
            self._clear_state()
        if self._token or self._load_state():
            return True

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=30),
            follow_redirects=True,
        )
        self._running = True
        try:
            return await self._qr_login()
        finally:
            self._running = False
            if self._client:
                await self._client.aclose()
                self._client = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a text reply to the Weixin user."""
        if not self._client or not self._token:
            logger.warning("Skip Weixin send: client is not ready.")
            return

        content = (msg.content or "").strip()
        if not content:
            return

        context_token = self._context_tokens.get(msg.chat_id, "")
        if not context_token:
            logger.warning("Skip Weixin send: missing context token for chat_id=%s.", msg.chat_id)
            return
        await self._send_text(msg.chat_id, content, context_token)

    def _get_state_dir(self) -> Path:
        if self.state_dir:
            return Path(self.state_dir).expanduser()
        return get_data_dir() / "weixin"

    def _state_file(self) -> Path:
        path = self._get_state_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path / "account.json"

    def _clear_state(self) -> None:
        self._token = ""
        self._get_updates_buf = ""
        state_file = self._state_file()
        if state_file.exists():
            state_file.unlink()

    def _load_state(self) -> bool:
        """Load saved Weixin token and cursor state from disk."""
        state_file = self._state_file()
        if not state_file.exists():
            return False
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed loading Weixin state file")
            return False

        self._token = str(data.get("token", "")).strip()
        self._get_updates_buf = str(data.get("get_updates_buf", "")).strip()
        base_url = str(data.get("base_url", "")).strip()
        if base_url:
            self.base_url = base_url.rstrip("/")
        return bool(self._token)

    def _save_state(self) -> None:
        """Persist current Weixin token and polling cursor."""
        state_file = self._state_file()
        payload = {
            "token": self._token,
            "get_updates_buf": self._get_updates_buf,
            "base_url": self.base_url,
        }
        state_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _random_wechat_uin() -> str:
        """Build the per-request `X-WECHAT-UIN` header value."""
        value = int.from_bytes(os.urandom(4), "big")
        return base64.b64encode(str(value).encode("utf-8")).decode("utf-8")

    def _make_headers(self, *, auth: bool = True) -> dict[str, str]:
        """Build request headers expected by the Weixin bridge API."""
        headers = {
            "X-WECHAT-UIN": self._random_wechat_uin(),
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
        }
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def _api_get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        auth: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        assert self._client is not None
        headers = self._make_headers(auth=auth)
        if extra_headers:
            headers.update(extra_headers)
        response = await self._client.get(f"{self.base_url}/{endpoint}", params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def _api_post(
        self,
        endpoint: str,
        body: dict[str, Any] | None = None,
        *,
        auth: bool = True,
    ) -> dict[str, Any]:
        assert self._client is not None
        payload = dict(body or {})
        payload.setdefault("base_info", BASE_INFO)
        response = await self._client.post(
            f"{self.base_url}/{endpoint}",
            json=payload,
            headers=self._make_headers(auth=auth),
        )
        response.raise_for_status()
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {}

    async def _qr_login(self) -> bool:
        """Perform QR-code login and cache the returned bot token."""
        try:
            data = await self._api_get(
                "ilink/bot/get_bot_qrcode",
                params={"bot_type": "3"},
                auth=False,
            )
            qr_id = str(data.get("qrcode", "")).strip()
            qr_content = str(data.get("qrcode_img_content", "")).strip()
            if not qr_id:
                logger.error("Weixin login failed: QR code missing in response.")
                return False
            self._print_qr_code(qr_content or qr_id)

            while self._running:
                status_data = await self._api_get(
                    "ilink/bot/get_qrcode_status",
                    params={"qrcode": qr_id},
                    auth=False,
                    extra_headers={"iLink-App-ClientVersion": "1"},
                )
                status = str(status_data.get("status", "")).strip()
                if status == "confirmed":
                    token = str(status_data.get("bot_token", "")).strip()
                    if not token:
                        logger.error("Weixin login confirmed but no bot token was returned.")
                        return False
                    self._token = token
                    base_url = str(status_data.get("baseurl", "")).strip()
                    if base_url:
                        self.base_url = base_url.rstrip("/")
                    self._save_state()
                    return True
                if status == "expired":
                    logger.warning("Weixin QR code expired before confirmation.")
                    return False
                await asyncio.sleep(1)
        except Exception:
            logger.exception("Weixin QR login failed")
            return False
        return False

    @staticmethod
    def _print_qr_code(url: str) -> None:
        """Print an ASCII QR code or the raw login URL."""
        try:
            import qrcode

            qr = qrcode.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        except Exception:
            print(f"\nWeixin login URL: {url}\n")

    async def _poll_once(self) -> None:
        """Run one Weixin long-poll cycle and process returned messages."""
        assert self._client is not None
        self._client.timeout = httpx.Timeout(self._next_poll_timeout_seconds + 10, connect=30)
        data = await self._api_post(
            "ilink/bot/getupdates",
            {"get_updates_buf": self._get_updates_buf, "base_info": BASE_INFO},
        )
        ret = data.get("ret", 0)
        errcode = data.get("errcode", 0)
        if ret not in (None, 0) or errcode not in (None, 0):
            if ret == ERRCODE_SESSION_EXPIRED or errcode == ERRCODE_SESSION_EXPIRED:
                logger.warning("Weixin session expired; waiting before retry.")
                await asyncio.sleep(3600)
                return
            raise RuntimeError(f"Weixin getupdates failed: ret={ret} errcode={errcode}")

        timeout_ms = data.get("longpolling_timeout_ms")
        if isinstance(timeout_ms, int) and timeout_ms > 0:
            self._next_poll_timeout_seconds = max(timeout_ms // 1000, 5)

        updates_buf = str(data.get("get_updates_buf", "")).strip()
        if updates_buf:
            self._get_updates_buf = updates_buf
            self._save_state()

        messages = data.get("msgs", [])
        if not isinstance(messages, list):
            return
        for message in messages:
            if isinstance(message, dict):
                await self._process_message(message)

    async def _process_message(self, msg: dict[str, Any]) -> None:
        """Normalize one inbound Weixin message into the bus format."""
        if msg.get("message_type") == MESSAGE_TYPE_BOT:
            return

        msg_id = str(msg.get("message_id", "") or msg.get("seq", "")).strip()
        if not msg_id:
            msg_id = f"{msg.get('from_user_id', '')}_{msg.get('create_time_ms', '')}"
        if msg_id in self._processed_ids:
            return
        self._processed_ids[msg_id] = None
        while len(self._processed_ids) > 1000:
            self._processed_ids.popitem(last=False)

        sender_id = str(msg.get("from_user_id", "")).strip()
        if not sender_id:
            return

        context_token = str(msg.get("context_token", "")).strip()
        if context_token:
            self._context_tokens[sender_id] = context_token

        content_parts: list[str] = []
        item_list = msg.get("item_list", [])
        if isinstance(item_list, list):
            for item in item_list:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type == ITEM_TEXT:
                    text_item = item.get("text_item", {})
                    if isinstance(text_item, dict):
                        text = str(text_item.get("text", "")).strip()
                        if text:
                            content_parts.append(text)
                elif item_type == ITEM_IMAGE:
                    content_parts.append("[image]")
                elif item_type == ITEM_VOICE:
                    content_parts.append("[voice]")
                elif item_type == ITEM_FILE:
                    content_parts.append("[file]")
                elif item_type == ITEM_VIDEO:
                    content_parts.append("[video]")

        content = "\n".join(part for part in content_parts if part).strip()
        if not content:
            return

        await self.publish_inbound(
            sender_id=sender_id,
            chat_id=sender_id,
            content=content,
            metadata={"message_id": msg_id},
        )

    async def _send_text(self, to_user_id: str, text: str, context_token: str) -> None:
        """Send a plain text Weixin message."""
        body = {
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": f"openpipixia-{uuid.uuid4().hex[:12]}",
                "message_type": MESSAGE_TYPE_BOT,
                "message_state": MESSAGE_STATE_FINISH,
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
                "context_token": context_token,
            },
            "base_info": BASE_INFO,
        }
        response = await self._api_post("ilink/bot/sendmessage", body)
        errcode = response.get("errcode", 0)
        if errcode not in (None, 0):
            logger.warning("Weixin send error: code=%s message=%s", errcode, response.get("errmsg", ""))
