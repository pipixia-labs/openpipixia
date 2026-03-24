"""WeCom (Enterprise WeChat) channel adapter."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from collections import OrderedDict
from typing import Any

from ..bus.events import OutboundMessage
from .base import BaseChannel

logger = logging.getLogger(__name__)

WECOM_AVAILABLE = importlib.util.find_spec("wecom_aibot_sdk") is not None


class WecomChannel(BaseChannel):
    """WeCom adapter using the AI bot WebSocket long-connection SDK."""

    name = "wecom"

    def __init__(
        self,
        bus,
        *,
        bot_id: str,
        secret: str,
        allow_from: list[str] | None = None,
        welcome_message: str = "",
    ) -> None:
        super().__init__(bus, allow_from=allow_from)
        self.bot_id = bot_id.strip()
        self.secret = secret.strip()
        self.welcome_message = welcome_message
        self._client: Any = None
        self._generate_req_id: Any = None
        self._chat_frames: dict[str, Any] = {}
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()

    async def start(self) -> None:
        """Start the WeCom WebSocket client and keep it alive."""
        if not WECOM_AVAILABLE:
            raise RuntimeError("WeCom channel requires `wecom-aibot-sdk-python`.")
        if not self.bot_id or not self.secret:
            raise RuntimeError("Missing WECOM_BOT_ID or WECOM_SECRET for wecom channel.")

        from wecom_aibot_sdk import WSClient, generate_req_id

        self._running = True
        self._generate_req_id = generate_req_id
        self._client = WSClient(
            {
                "bot_id": self.bot_id,
                "secret": self.secret,
                "reconnect_interval": 1000,
                "max_reconnect_attempts": -1,
                "heartbeat_interval": 30000,
            }
        )
        self._client.on("connected", self._on_connected)
        self._client.on("authenticated", self._on_authenticated)
        self._client.on("disconnected", self._on_disconnected)
        self._client.on("error", self._on_error)
        self._client.on("message.text", self._on_text_message)
        self._client.on("message.image", self._on_image_message)
        self._client.on("message.voice", self._on_voice_message)
        self._client.on("message.file", self._on_file_message)
        self._client.on("message.mixed", self._on_mixed_message)
        self._client.on("event.enter_chat", self._on_enter_chat)

        await self._client.connect_async()
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the WeCom client."""
        self._running = False
        if self._client:
            disconnect = getattr(self._client, "disconnect", None)
            if callable(disconnect):
                await disconnect()
        self._client = None

    async def send(self, msg: OutboundMessage) -> None:
        """Reply to the current WeCom chat with plain text."""
        if not self._client:
            logger.warning("Skip WeCom send: client is not running.")
            return
        frame = self._chat_frames.get(msg.chat_id)
        if frame is None:
            logger.warning("Skip WeCom send: no frame cached for chat_id=%s.", msg.chat_id)
            return

        content = (msg.content or "").strip()
        if not content:
            return

        try:
            stream_id = self._generate_req_id("stream") if callable(self._generate_req_id) else "stream"
            await self._client.reply_stream(frame, stream_id, content, finish=True)
        except Exception:
            logger.exception("WeCom send failed")

    async def _on_connected(self, _frame: Any) -> None:
        logger.info("WeCom WebSocket connected")

    async def _on_authenticated(self, _frame: Any) -> None:
        logger.info("WeCom authenticated successfully")

    async def _on_disconnected(self, frame: Any) -> None:
        reason = getattr(frame, "body", None) or str(frame)
        logger.warning("WeCom WebSocket disconnected: %s", reason)

    async def _on_error(self, frame: Any) -> None:
        logger.error("WeCom error: %s", frame)

    async def _on_text_message(self, frame: Any) -> None:
        await self._process_message(frame, "text")

    async def _on_image_message(self, frame: Any) -> None:
        await self._process_message(frame, "image")

    async def _on_voice_message(self, frame: Any) -> None:
        await self._process_message(frame, "voice")

    async def _on_file_message(self, frame: Any) -> None:
        await self._process_message(frame, "file")

    async def _on_mixed_message(self, frame: Any) -> None:
        await self._process_message(frame, "mixed")

    async def _on_enter_chat(self, frame: Any) -> None:
        """Send an optional welcome message when the user opens the chat."""
        if not self.welcome_message or not self._client:
            return
        try:
            await self._client.reply_welcome(
                frame,
                {
                    "msgtype": "text",
                    "text": {"content": self.welcome_message},
                },
            )
        except Exception:
            logger.exception("WeCom welcome message failed")

    async def _process_message(self, frame: Any, msg_type: str) -> None:
        """Normalize inbound WeCom SDK frames into bus events."""
        body = getattr(frame, "body", None)
        if body is None and isinstance(frame, dict):
            body = frame.get("body", frame)
        if not isinstance(body, dict):
            return

        msg_id = str(body.get("msgid", "")).strip()
        if not msg_id:
            msg_id = f"{body.get('chatid', '')}_{body.get('sendertime', '')}"
        if msg_id in self._processed_message_ids:
            return
        self._processed_message_ids[msg_id] = None
        while len(self._processed_message_ids) > 1000:
            self._processed_message_ids.popitem(last=False)

        from_info = body.get("from", {})
        sender_id = ""
        if isinstance(from_info, dict):
            sender_id = str(from_info.get("userid", "")).strip()
        chat_id = str(body.get("chatid", "") or sender_id).strip()
        if not sender_id or not chat_id:
            return

        content = self._extract_content(body, msg_type)
        if not content:
            return

        self._chat_frames[chat_id] = frame
        await self.publish_inbound(
            sender_id=sender_id,
            chat_id=chat_id,
            content=content,
            metadata={
                "message_id": msg_id,
                "msg_type": msg_type,
                "chat_type": str(body.get("chattype", "")).strip(),
            },
        )

    def _extract_content(self, body: dict[str, Any], msg_type: str) -> str:
        """Extract user-visible text content from a WeCom message payload."""
        if msg_type == "text":
            text = body.get("text", {})
            if isinstance(text, dict):
                return str(text.get("content", "")).strip()
            return ""
        if msg_type == "voice":
            voice = body.get("voice", {})
            if isinstance(voice, dict):
                content = str(voice.get("content", "")).strip()
                return f"[voice] {content}".strip()
            return "[voice]"
        if msg_type == "image":
            image = body.get("image", {})
            name = ""
            if isinstance(image, dict):
                name = os.path.basename(str(image.get("name", "")).strip())
            return f"[image{': ' + name if name else ''}]"
        if msg_type == "file":
            file_info = body.get("file", {})
            name = ""
            if isinstance(file_info, dict):
                name = os.path.basename(str(file_info.get("name", "")).strip())
            return f"[file{': ' + name if name else ''}]"
        if msg_type == "mixed":
            parts: list[str] = []
            mixed = body.get("mixed", {})
            items = mixed.get("item", []) if isinstance(mixed, dict) else []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_type = str(item.get("type", "")).strip()
                    if item_type == "text":
                        text = item.get("text", {})
                        if isinstance(text, dict):
                            value = str(text.get("content", "")).strip()
                            if value:
                                parts.append(value)
                    elif item_type:
                        parts.append(f"[{item_type}]")
            return "\n".join(parts).strip()
        return f"[{msg_type}]"
