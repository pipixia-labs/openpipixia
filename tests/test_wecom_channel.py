"""Tests for WeCom channel adapter behavior."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from openppx.bus.events import OutboundMessage
from openppx.bus.queue import MessageBus
from openppx.channels.wecom import WecomChannel


class WecomChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_uses_cached_frame_and_client(self) -> None:
        bus = MessageBus()
        channel = WecomChannel(bus=bus, bot_id="bot-1", secret="secret-1")
        channel._client = SimpleNamespace(reply_stream=AsyncMock())
        channel._generate_req_id = lambda prefix: f"{prefix}-001"
        channel._chat_frames["chat-1"] = {"frame": 1}

        await channel.send(
            OutboundMessage(
                channel="wecom",
                chat_id="chat-1",
                content="hello wecom",
            )
        )

        channel._client.reply_stream.assert_awaited_once_with(
            {"frame": 1},
            "stream-001",
            "hello wecom",
            finish=True,
        )

    async def test_process_message_publishes_allowed_inbound(self) -> None:
        bus = MessageBus()
        channel = WecomChannel(
            bus=bus,
            bot_id="bot-1",
            secret="secret-1",
            allow_from=["u02"],
        )

        denied = SimpleNamespace(body={"msgid": "m-1", "chatid": "chat-1", "from": {"userid": "u01"}, "text": {"content": "denied"}})
        allowed = SimpleNamespace(body={"msgid": "m-2", "chatid": "chat-2", "from": {"userid": "u02"}, "text": {"content": "allowed"}})

        await channel._process_message(denied, "text")
        await channel._process_message(allowed, "text")

        inbound = await asyncio.wait_for(bus.consume_inbound(), timeout=0.2)
        self.assertEqual(inbound.channel, "wecom")
        self.assertEqual(inbound.chat_id, "chat-2")
        self.assertEqual(inbound.sender_id, "u02")
        self.assertEqual(inbound.content, "allowed")
        self.assertEqual(inbound.metadata.get("message_id"), "m-2")


if __name__ == "__main__":
    unittest.main()
