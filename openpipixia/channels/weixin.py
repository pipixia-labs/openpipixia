"""Personal WeChat (微信) channel using HTTP long-poll API.

Uses the ilinkai.weixin.qq.com API for personal WeChat messaging.
No WebSocket, no local WeChat client needed — just HTTP requests with a
bot token obtained via QR code login.

Protocol reverse-engineered from ``@tencent-weixin/openclaw-weixin`` v1.0.2.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from loguru import logger

from .base import BaseChannel
from .polling_utils import cancel_background_task
from ..bus.events import OutboundMessage

# ---------------------------------------------------------------------------
# Protocol constants (from openclaw-weixin types.ts)
# ---------------------------------------------------------------------------

# MessageItemType
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

# MessageType  (1 = inbound from user, 2 = outbound from bot)
MESSAGE_TYPE_USER = 1
MESSAGE_TYPE_BOT = 2

# MessageState
MESSAGE_STATE_FINISH = 2

WEIXIN_MAX_MESSAGE_LEN = 4000
BASE_INFO: dict[str, str] = {"channel_version": "1.0.2"}

# Session-expired error code
ERRCODE_SESSION_EXPIRED = -14

# Retry constants (matching the reference plugin's monitor.ts)
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_S = 30
RETRY_DELAY_S = 2

# Default long-poll timeout; overridden by server via longpolling_timeout_ms.
DEFAULT_LONG_POLL_TIMEOUT_S = 35

# Media-type codes for getuploadurl  (1=image, 2=video, 3=file)
UPLOAD_MEDIA_IMAGE = 1
UPLOAD_MEDIA_VIDEO = 2
UPLOAD_MEDIA_FILE = 3

# File extensions considered as images / videos for outbound media
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".ico", ".svg"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}


def _split_message(text: str, max_len: int = WEIXIN_MAX_MESSAGE_LEN) -> list[str]:
    """Split text into chunks of at most *max_len* characters."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    while text:
        chunks.append(text[:max_len])
        text = text[max_len:]
    return chunks



class WeixinChannel(BaseChannel):
    """Personal WeChat channel using HTTP long-poll.

    Connects to ilinkai.weixin.qq.com API to receive and send personal
    WeChat messages. Authentication is via QR code login which produces
    a bot token.
    """

    name = "weixin"

    def __init__(
        self,
        bus,
        *,
        allow_from: list[str] | None = None,
        base_url: str = "https://ilinkai.weixin.qq.com",
        cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c",
        token: str = "",
        state_dir: str = "",
        poll_timeout_seconds: int = DEFAULT_LONG_POLL_TIMEOUT_S,
    ) -> None:
        super().__init__(bus, allow_from=allow_from)
        self.base_url = base_url.rstrip("/")
        self.cdn_base_url = cdn_base_url.rstrip("/")
        self._config_token = token.strip()
        self._config_state_dir = state_dir.strip()
        self._poll_timeout_seconds = max(int(poll_timeout_seconds), 5)

        # State
        self._client: httpx.AsyncClient | None = None
        self._get_updates_buf: str = ""
        self._context_tokens: dict[str, str] = {}  # from_user_id -> context_token
        self._processed_ids: OrderedDict[str, None] = OrderedDict()
        self._state_dir_path: Path | None = None
        self._token: str = ""
        self._poll_task: asyncio.Task[None] | None = None
        self._next_poll_timeout_s: int = self._poll_timeout_seconds

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    def _get_state_dir(self) -> Path:
        if self._state_dir_path:
            return self._state_dir_path
        if self._config_state_dir:
            d = Path(self._config_state_dir).expanduser()
        else:
            d = Path.home() / ".openpipixia" / "weixin"
        d.mkdir(parents=True, exist_ok=True)
        self._state_dir_path = d
        return d

    def _get_media_dir(self) -> Path:
        d = self._get_state_dir() / "media"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> bool:
        """Load saved account state. Returns True if a valid token was found."""
        state_file = self._get_state_dir() / "account.json"
        if not state_file.exists():
            return False
        try:
            data = json.loads(state_file.read_text())
            self._token = data.get("token", "")
            self._get_updates_buf = data.get("get_updates_buf", "")
            base_url = data.get("base_url", "")
            if base_url:
                self.base_url = base_url
            return bool(self._token)
        except Exception as e:
            logger.warning(f"Failed to load WeChat state: {e}")
            return False

    def _save_state(self) -> None:
        state_file = self._get_state_dir() / "account.json"
        try:
            data = {
                "token": self._token,
                "get_updates_buf": self._get_updates_buf,
                "base_url": self.base_url,
            }
            state_file.write_text(json.dumps(data, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Failed to save WeChat state: {e}")

    # ------------------------------------------------------------------
    # HTTP helpers  (matches api.ts buildHeaders / apiFetch)
    # ------------------------------------------------------------------

    @staticmethod
    def _random_wechat_uin() -> str:
        """X-WECHAT-UIN: random uint32 -> decimal string -> base64."""
        uint32 = int.from_bytes(os.urandom(4), "big")
        return base64.b64encode(str(uint32).encode()).decode()

    def _make_headers(self, *, auth: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {
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
        params: dict | None = None,
        *,
        auth: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        assert self._client is not None
        url = f"{self.base_url}/{endpoint}"
        hdrs = self._make_headers(auth=auth)
        if extra_headers:
            hdrs.update(extra_headers)
        resp = await self._client.get(url, params=params, headers=hdrs)
        resp.raise_for_status()
        return resp.json()

    async def _api_post(
        self,
        endpoint: str,
        body: dict | None = None,
        *,
        auth: bool = True,
    ) -> dict:
        assert self._client is not None
        url = f"{self.base_url}/{endpoint}"
        payload = body or {}
        if "base_info" not in payload:
            payload["base_info"] = BASE_INFO
        resp = await self._client.post(url, json=payload, headers=self._make_headers(auth=auth))
        resp.raise_for_status()
        return resp.json()


    # ------------------------------------------------------------------
    # QR Code Login  (matches login-qr.ts)
    # ------------------------------------------------------------------

    async def _qr_login(self) -> bool:
        """Perform QR code login flow. Returns True on success."""
        try:
            logger.info("Starting WeChat QR code login...")

            data = await self._api_get(
                "ilink/bot/get_bot_qrcode",
                params={"bot_type": "3"},
                auth=False,
            )
            qrcode_img_content = data.get("qrcode_img_content", "")
            qrcode_id = data.get("qrcode", "")

            if not qrcode_id:
                logger.error(f"Failed to get QR code from WeChat API: {data}")
                return False

            scan_url = qrcode_img_content or qrcode_id
            self._print_qr_code(scan_url)

            logger.info("Waiting for QR code scan...")
            while self._running:
                try:
                    status_data = await self._api_get(
                        "ilink/bot/get_qrcode_status",
                        params={"qrcode": qrcode_id},
                        auth=False,
                        extra_headers={"iLink-App-ClientVersion": "1"},
                    )
                except httpx.TimeoutException:
                    continue

                status = status_data.get("status", "")
                if status == "confirmed":
                    token = status_data.get("bot_token", "")
                    bot_id = status_data.get("ilink_bot_id", "")
                    base_url = status_data.get("baseurl", "")
                    user_id = status_data.get("ilink_user_id", "")
                    if token:
                        self._token = token
                        if base_url:
                            self.base_url = base_url
                        self._save_state()
                        logger.info(
                            f"WeChat login successful! bot_id={bot_id} user_id={user_id}"
                        )
                        return True
                    else:
                        logger.error("Login confirmed but no bot_token in response")
                        return False
                elif status == "scaned":
                    logger.info("QR code scanned, waiting for confirmation...")
                elif status == "expired":
                    logger.warning("QR code expired")
                    return False

                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"WeChat QR login failed: {e}")

        return False

    @staticmethod
    def _print_qr_code(url: str) -> None:
        try:
            import qrcode as qr_lib

            qr = qr_lib.QRCode(border=1)
            qr.add_data(url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
        except ImportError:
            logger.info(f"QR code URL (install 'qrcode' for terminal display): {url}")
            print(f"\nLogin URL: {url}\n")

    # ------------------------------------------------------------------
    # Channel lifecycle
    # ------------------------------------------------------------------

    async def login(self, force: bool = False) -> bool:
        """Perform QR code login and save token. Returns True on success."""
        if force:
            self._token = ""
            self._get_updates_buf = ""
            state_file = self._get_state_dir() / "account.json"
            if state_file.exists():
                state_file.unlink()
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

    async def start(self) -> None:
        if self._poll_task and not self._poll_task.done():
            return
        self._running = True
        self._next_poll_timeout_s = self._poll_timeout_seconds
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._next_poll_timeout_s + 10, connect=30),
            follow_redirects=True,
        )

        if self._config_token:
            self._token = self._config_token
        elif not self._load_state():
            if not await self._qr_login():
                logger.error(
                    "WeChat login failed. Set WEIXIN_TOKEN or run QR login to authenticate."
                )
                self._running = False
                return

        logger.info("WeChat channel starting with long-poll...")
        self._poll_task = asyncio.create_task(self._poll_loop(), name="weixin-poll")

    async def stop(self) -> None:
        self._running = False
        await cancel_background_task(self._poll_task)
        self._poll_task = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self._save_state()
        logger.info("WeChat channel stopped")


    # ------------------------------------------------------------------
    # Polling  (matches monitor.ts monitorWeixinProvider)
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        consecutive_failures = 0
        while self._running:
            try:
                await self._poll_once()
                consecutive_failures = 0
            except asyncio.CancelledError:
                break
            except httpx.TimeoutException:
                continue
            except Exception:
                if not self._running:
                    break
                consecutive_failures += 1
                logger.error(
                    f"WeChat poll error ({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await asyncio.sleep(BACKOFF_DELAY_S)
                else:
                    await asyncio.sleep(RETRY_DELAY_S)

    async def _poll_once(self) -> None:
        body: dict[str, Any] = {
            "get_updates_buf": self._get_updates_buf,
            "base_info": BASE_INFO,
        }

        assert self._client is not None
        self._client.timeout = httpx.Timeout(self._next_poll_timeout_s + 10, connect=30)

        data = await self._api_post("ilink/bot/getupdates", body)

        ret = data.get("ret", 0)
        errcode = data.get("errcode", 0)
        is_error = (ret is not None and ret != 0) or (errcode is not None and errcode != 0)

        if is_error:
            if errcode == ERRCODE_SESSION_EXPIRED or ret == ERRCODE_SESSION_EXPIRED:
                logger.warning(
                    f"WeChat session expired (errcode {errcode}). Pausing 60 min."
                )
                await asyncio.sleep(3600)
                return
            raise RuntimeError(
                f"getUpdates failed: ret={ret} errcode={errcode} errmsg={data.get('errmsg', '')}"
            )

        server_timeout_ms = data.get("longpolling_timeout_ms")
        if server_timeout_ms and server_timeout_ms > 0:
            self._next_poll_timeout_s = max(server_timeout_ms // 1000, 5)

        new_buf = data.get("get_updates_buf", "")
        if new_buf:
            self._get_updates_buf = new_buf
            self._save_state()

        msgs: list[dict] = data.get("msgs", []) or []
        for msg in msgs:
            try:
                await self._process_message(msg)
            except Exception as e:
                logger.error(f"Error processing WeChat message: {e}")

    # ------------------------------------------------------------------
    # Inbound message processing
    # ------------------------------------------------------------------

    async def _process_message(self, msg: dict) -> None:
        """Process a single WeixinMessage from getUpdates."""
        if msg.get("message_type") == MESSAGE_TYPE_BOT:
            return

        msg_id = str(msg.get("message_id", "") or msg.get("seq", ""))
        if not msg_id:
            msg_id = f"{msg.get('from_user_id', '')}_{msg.get('create_time_ms', '')}"
        if msg_id in self._processed_ids:
            return
        self._processed_ids[msg_id] = None
        while len(self._processed_ids) > 1000:
            self._processed_ids.popitem(last=False)

        from_user_id = msg.get("from_user_id", "") or ""
        if not from_user_id:
            return

        ctx_token = msg.get("context_token", "")
        if ctx_token:
            self._context_tokens[from_user_id] = ctx_token

        item_list: list[dict] = msg.get("item_list") or []
        content_parts: list[str] = []
        media_paths: list[str] = []

        for item in item_list:
            item_type = item.get("type", 0)

            if item_type == ITEM_TEXT:
                text = (item.get("text_item") or {}).get("text", "")
                if text:
                    ref = item.get("ref_msg")
                    if ref:
                        ref_item = ref.get("message_item")
                        if ref_item and ref_item.get("type", 0) in (
                            ITEM_IMAGE, ITEM_VOICE, ITEM_FILE, ITEM_VIDEO,
                        ):
                            content_parts.append(text)
                        else:
                            parts: list[str] = []
                            if ref.get("title"):
                                parts.append(ref["title"])
                            if ref_item:
                                ref_text = (ref_item.get("text_item") or {}).get("text", "")
                                if ref_text:
                                    parts.append(ref_text)
                            if parts:
                                content_parts.append(f"[引用: {' | '.join(parts)}]\n{text}")
                            else:
                                content_parts.append(text)
                    else:
                        content_parts.append(text)

            elif item_type == ITEM_IMAGE:
                image_item = item.get("image_item") or {}
                file_path = await self._download_media_item(image_item, "image")
                if file_path:
                    content_parts.append(f"[image]\n[Image: source: {file_path}]")
                    media_paths.append(file_path)
                else:
                    content_parts.append("[image]")

            elif item_type == ITEM_VOICE:
                voice_item = item.get("voice_item") or {}
                voice_text = voice_item.get("text", "")
                if voice_text:
                    content_parts.append(f"[voice] {voice_text}")
                else:
                    file_path = await self._download_media_item(voice_item, "voice")
                    if file_path:
                        content_parts.append(f"[voice]\n[Audio: source: {file_path}]")
                        media_paths.append(file_path)
                    else:
                        content_parts.append("[voice]")

            elif item_type == ITEM_FILE:
                file_item = item.get("file_item") or {}
                file_name = file_item.get("file_name", "unknown")
                file_path = await self._download_media_item(file_item, "file", file_name)
                if file_path:
                    content_parts.append(f"[file: {file_name}]\n[File: source: {file_path}]")
                    media_paths.append(file_path)
                else:
                    content_parts.append(f"[file: {file_name}]")

            elif item_type == ITEM_VIDEO:
                video_item = item.get("video_item") or {}
                file_path = await self._download_media_item(video_item, "video")
                if file_path:
                    content_parts.append(f"[video]\n[Video: source: {file_path}]")
                    media_paths.append(file_path)
                else:
                    content_parts.append("[video]")

        content = "\n".join(content_parts)
        if not content:
            return

        items_str = ",".join(str(i.get("type", 0)) for i in item_list)
        logger.info(
            f"WeChat inbound: from={from_user_id} items={items_str} bodyLen={len(content)}"
        )

        await self.publish_inbound(
            sender_id=from_user_id,
            chat_id=from_user_id,
            content=content,
            media=media_paths or None,
            metadata={"message_id": msg_id},
        )


    # ------------------------------------------------------------------
    # Media download  (matches media-download.ts + pic-decrypt.ts)
    # ------------------------------------------------------------------

    async def _download_media_item(
        self,
        typed_item: dict,
        media_type: str,
        filename: str | None = None,
    ) -> str | None:
        """Download + AES-decrypt a media item. Returns local path or None."""
        try:
            media = typed_item.get("media") or {}
            encrypt_query_param = media.get("encrypt_query_param", "")

            if not encrypt_query_param:
                return None

            raw_aeskey_hex = typed_item.get("aeskey", "")
            media_aes_key_b64 = media.get("aes_key", "")

            aes_key_b64: str = ""
            if raw_aeskey_hex:
                aes_key_b64 = base64.b64encode(bytes.fromhex(raw_aeskey_hex)).decode()
            elif media_aes_key_b64:
                aes_key_b64 = media_aes_key_b64

            cdn_url = (
                f"{self.cdn_base_url}/download"
                f"?encrypted_query_param={quote(encrypt_query_param)}"
            )

            assert self._client is not None
            resp = await self._client.get(cdn_url)
            resp.raise_for_status()
            data = resp.content

            if aes_key_b64 and data:
                data = _decrypt_aes_ecb(data, aes_key_b64)
            elif not aes_key_b64:
                logger.debug(f"No AES key for {media_type} item, using raw bytes")

            if not data:
                return None

            media_dir = self._get_media_dir()
            ext = _ext_for_type(media_type)
            if not filename:
                ts = int(time.time())
                h = abs(hash(encrypt_query_param)) % 100000
                filename = f"{media_type}_{ts}_{h}{ext}"
            safe_name = os.path.basename(filename)
            file_path = media_dir / safe_name
            file_path.write_bytes(data)
            logger.debug(f"Downloaded WeChat {media_type} to {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"Error downloading WeChat media: {e}")
            return None

    # ------------------------------------------------------------------
    # Outbound  (matches send.ts)
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> None:
        if not self._client or not self._token:
            logger.warning("WeChat client not initialized or not authenticated")
            return

        content = msg.content.strip()
        ctx_token = self._context_tokens.get(msg.chat_id, "")
        if not ctx_token:
            logger.warning(
                f"WeChat: no context_token for chat_id={msg.chat_id}, cannot send"
            )
            return

        # Send media files referenced in metadata, if any
        media_paths: list[str] = []
        raw_media = msg.metadata.get("media")
        if isinstance(raw_media, list):
            media_paths = [str(p) for p in raw_media if p]
        elif isinstance(raw_media, str) and raw_media:
            media_paths = [raw_media]

        for media_path in media_paths:
            try:
                await self._send_media_file(msg.chat_id, media_path, ctx_token)
            except Exception:
                filename = Path(media_path).name
                logger.error(f"Failed to send WeChat media {media_path}")
                await self._send_text(
                    msg.chat_id, f"[Failed to send: {filename}]", ctx_token,
                )

        if not content:
            return

        try:
            chunks = _split_message(content, WEIXIN_MAX_MESSAGE_LEN)
            for chunk in chunks:
                await self._send_text(msg.chat_id, chunk, ctx_token)
        except Exception as e:
            logger.error(f"Error sending WeChat message: {e}")

    async def _send_text(
        self,
        to_user_id: str,
        text: str,
        context_token: str,
    ) -> None:
        """Send a text message matching the exact protocol from send.ts."""
        client_id = f"openpipixia-{uuid.uuid4().hex[:12]}"

        item_list: list[dict] = []
        if text:
            item_list.append({"type": ITEM_TEXT, "text_item": {"text": text}})

        weixin_msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
        }
        if item_list:
            weixin_msg["item_list"] = item_list
        if context_token:
            weixin_msg["context_token"] = context_token

        body: dict[str, Any] = {
            "msg": weixin_msg,
            "base_info": BASE_INFO,
        }

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            logger.warning(
                f"WeChat send error (code {errcode}): {data.get('errmsg', '')}"
            )


    async def _send_media_file(
        self,
        to_user_id: str,
        media_path: str,
        context_token: str,
    ) -> None:
        """Upload a local file to WeChat CDN and send it as a media message.

        Follows the exact protocol from ``@tencent-weixin/openclaw-weixin`` v1.0.2:
        1. Generate a random 16-byte AES key (client-side).
        2. Call ``getuploadurl`` with file metadata + hex-encoded AES key.
        3. AES-128-ECB encrypt the file and POST to CDN.
        4. Read ``x-encrypted-param`` header from CDN response as the download param.
        5. Send a ``sendmessage`` with the appropriate media item referencing the upload.
        """
        p = Path(media_path)
        if not p.is_file():
            raise FileNotFoundError(f"Media file not found: {media_path}")

        raw_data = p.read_bytes()
        raw_size = len(raw_data)
        raw_md5 = hashlib.md5(raw_data).hexdigest()

        ext = p.suffix.lower()
        if ext in _IMAGE_EXTS:
            upload_type = UPLOAD_MEDIA_IMAGE
            item_type = ITEM_IMAGE
            item_key = "image_item"
        elif ext in _VIDEO_EXTS:
            upload_type = UPLOAD_MEDIA_VIDEO
            item_type = ITEM_VIDEO
            item_key = "video_item"
        else:
            upload_type = UPLOAD_MEDIA_FILE
            item_type = ITEM_FILE
            item_key = "file_item"

        aes_key_raw = os.urandom(16)
        aes_key_hex = aes_key_raw.hex()

        padded_size = ((raw_size + 1 + 15) // 16) * 16

        file_key = os.urandom(16).hex()
        upload_body: dict[str, Any] = {
            "filekey": file_key,
            "media_type": upload_type,
            "to_user_id": to_user_id,
            "rawsize": raw_size,
            "rawfilemd5": raw_md5,
            "filesize": padded_size,
            "no_need_thumb": True,
            "aeskey": aes_key_hex,
        }

        assert self._client is not None
        upload_resp = await self._api_post("ilink/bot/getuploadurl", upload_body)
        logger.debug(f"WeChat getuploadurl response: {upload_resp}")

        upload_param = upload_resp.get("upload_param", "")
        if not upload_param:
            raise RuntimeError(f"getuploadurl returned no upload_param: {upload_resp}")

        aes_key_b64 = base64.b64encode(aes_key_raw).decode()
        encrypted_data = _encrypt_aes_ecb(raw_data, aes_key_b64)

        cdn_upload_url = (
            f"{self.cdn_base_url}/upload"
            f"?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(file_key)}"
        )
        logger.debug(f"WeChat CDN POST url={cdn_upload_url[:80]} ciphertextSize={len(encrypted_data)}")

        cdn_resp = await self._client.post(
            cdn_upload_url,
            content=encrypted_data,
            headers={"Content-Type": "application/octet-stream"},
        )
        cdn_resp.raise_for_status()

        download_param = cdn_resp.headers.get("x-encrypted-param", "")
        if not download_param:
            raise RuntimeError(
                "CDN upload response missing x-encrypted-param header; "
                f"status={cdn_resp.status_code} headers={dict(cdn_resp.headers)}"
            )
        logger.debug(f"WeChat CDN upload success for {p.name}, got download_param")

        cdn_aes_key_b64 = base64.b64encode(aes_key_hex.encode()).decode()

        media_item: dict[str, Any] = {
            "media": {
                "encrypt_query_param": download_param,
                "aes_key": cdn_aes_key_b64,
                "encrypt_type": 1,
            },
        }

        if item_type == ITEM_IMAGE:
            media_item["mid_size"] = padded_size
        elif item_type == ITEM_VIDEO:
            media_item["video_size"] = padded_size
        elif item_type == ITEM_FILE:
            media_item["file_name"] = p.name
            media_item["len"] = str(raw_size)

        client_id = f"openpipixia-{uuid.uuid4().hex[:12]}"
        item_list: list[dict] = [{"type": item_type, item_key: media_item}]

        weixin_msg: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to_user_id,
            "client_id": client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_FINISH,
            "item_list": item_list,
        }
        if context_token:
            weixin_msg["context_token"] = context_token

        body: dict[str, Any] = {
            "msg": weixin_msg,
            "base_info": BASE_INFO,
        }

        data = await self._api_post("ilink/bot/sendmessage", body)
        errcode = data.get("errcode", 0)
        if errcode and errcode != 0:
            raise RuntimeError(
                f"WeChat send media error (code {errcode}): {data.get('errmsg', '')}"
            )
        logger.info(f"WeChat media sent: {p.name} (type={item_key})")


# ---------------------------------------------------------------------------
# AES-128-ECB encryption / decryption  (matches pic-decrypt.ts / aes-ecb.ts)
# ---------------------------------------------------------------------------


def _parse_aes_key(aes_key_b64: str) -> bytes:
    """Parse a base64-encoded AES key, handling both encodings seen in the wild.

    * ``base64(raw 16 bytes)``            -> images (media.aes_key)
    * ``base64(hex string of 16 bytes)``  -> file / voice / video
    """
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and re.fullmatch(rb"[0-9a-fA-F]{32}", decoded):
        return bytes.fromhex(decoded.decode("ascii"))
    raise ValueError(
        f"aes_key must decode to 16 raw bytes or 32-char hex string, got {len(decoded)} bytes"
    )


def _encrypt_aes_ecb(data: bytes, aes_key_b64: str) -> bytes:
    """Encrypt data with AES-128-ECB and PKCS7 padding for CDN upload."""
    try:
        key = _parse_aes_key(aes_key_b64)
    except Exception as e:
        logger.warning(f"Failed to parse AES key for encryption, sending raw: {e}")
        return data

    pad_len = 16 - len(data) % 16
    padded = data + bytes([pad_len] * pad_len)

    try:
        from Crypto.Cipher import AES

        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(padded)
    except ImportError:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher_obj = Cipher(algorithms.AES(key), modes.ECB())
        encryptor = cipher_obj.encryptor()
        return encryptor.update(padded) + encryptor.finalize()
    except ImportError:
        logger.warning("Cannot encrypt media: install 'pycryptodome' or 'cryptography'")
        return data


def _decrypt_aes_ecb(data: bytes, aes_key_b64: str) -> bytes:
    """Decrypt AES-128-ECB media data."""
    try:
        key = _parse_aes_key(aes_key_b64)
    except Exception as e:
        logger.warning(f"Failed to parse AES key, returning raw data: {e}")
        return data

    try:
        from Crypto.Cipher import AES

        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.decrypt(data)
    except ImportError:
        pass

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        cipher_obj = Cipher(algorithms.AES(key), modes.ECB())
        decryptor = cipher_obj.decryptor()
        return decryptor.update(data) + decryptor.finalize()
    except ImportError:
        logger.warning("Cannot decrypt media: install 'pycryptodome' or 'cryptography'")
        return data


def _ext_for_type(media_type: str) -> str:
    return {
        "image": ".jpg",
        "voice": ".silk",
        "video": ".mp4",
        "file": "",
    }.get(media_type, "")
