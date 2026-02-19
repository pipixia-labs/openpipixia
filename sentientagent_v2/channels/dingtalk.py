"""DingTalk channel adapter (token-based API + minimal inbound normalization)."""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..bus.events import OutboundMessage
from .base import BaseChannel

logger = logging.getLogger(__name__)

try:
    import dingtalk_stream  # noqa: F401

    DINGTALK_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime dependency
    DINGTALK_AVAILABLE = False


class DingTalkChannel(BaseChannel):
    """Minimal DingTalk adapter focused on private outbound messaging."""

    name = "dingtalk"

    def __init__(
        self,
        bus,
        *,
        client_id: str,
        client_secret: str,
        allow_from: list[str] | None = None,
        api_base: str = "https://api.dingtalk.com",
        token_margin_seconds: int = 60,
    ) -> None:
        super().__init__(bus, allow_from=allow_from)
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.api_base = api_base.rstrip("/")
        self.token_margin_seconds = max(int(token_margin_seconds), 0)

        self._access_token: str | None = None
        self._token_expiry_epoch: float = 0.0

    def _endpoint(self, path: str) -> str:
        return f"{self.api_base}{path}"

    def _api_call_sync(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body: bytes | None = None
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json; charset=utf-8")

        req = Request(
            self._endpoint(path),
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
        except HTTPError as exc:
            raise RuntimeError(f"DingTalk API HTTP error ({path}): {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"DingTalk API network error ({path}): {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"DingTalk API invalid JSON ({path}): {exc}") from exc

        if not isinstance(parsed, dict):
            raise RuntimeError(f"DingTalk API unexpected response ({path})")
        return parsed

    async def _api_call(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        call = functools.partial(
            self._api_call_sync,
            method,
            path,
            payload=payload,
            headers=headers,
        )
        return await loop.run_in_executor(None, call)

    async def start(self) -> None:
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Missing DINGTALK_CLIENT_ID or DINGTALK_CLIENT_SECRET for dingtalk channel.")
        self._running = True
        if not DINGTALK_AVAILABLE:
            logger.info("dingtalk-stream not installed: inbound stream mode disabled in minimal adapter.")

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        token = await self._get_access_token()
        if not token:
            logger.warning("Skip DingTalk send: access token is unavailable.")
            return
        user_id = msg.chat_id.strip()
        if not user_id:
            logger.warning("Skip DingTalk send: empty chat_id.")
            return

        payload = {
            "robotCode": self.client_id,
            "userIds": [user_id],
            "msgKey": "sampleMarkdown",
            "msgParam": json.dumps(
                {
                    "text": msg.content or "[empty message]",
                    "title": "sentientagent_v2 reply",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        await self._api_call(
            "POST",
            "/v1.0/robot/oToMessages/batchSend",
            payload=payload,
            headers={"x-acs-dingtalk-access-token": token},
        )

    async def _get_access_token(self) -> str | None:
        if self._access_token and time.time() < self._token_expiry_epoch:
            return self._access_token

        response = await self._api_call(
            "POST",
            "/v1.0/oauth2/accessToken",
            payload={
                "appKey": self.client_id,
                "appSecret": self.client_secret,
            },
            headers=None,
        )
        token = str(response.get("accessToken", "")).strip()
        if not token:
            return None
        expire_in_raw = response.get("expireIn", 7200)
        try:
            expire_in = int(expire_in_raw)
        except Exception:
            expire_in = 7200

        self._access_token = token
        self._token_expiry_epoch = time.time() + max(expire_in - self.token_margin_seconds, 30)
        return token

    async def _on_message(self, *, content: str, sender_id: str, sender_name: str = "") -> None:
        """Normalize one DingTalk inbound message into bus format."""
        text = str(content).strip()
        user_id = str(sender_id).strip()
        if not text or not user_id:
            return
        await self.publish_inbound(
            sender_id=user_id,
            chat_id=user_id,
            content=text,
            metadata={"sender_name": str(sender_name).strip()},
        )
