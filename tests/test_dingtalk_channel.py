"""Tests for DingTalk channel adapter behavior."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from sentientagent_v2.bus.events import OutboundMessage
from sentientagent_v2.bus.queue import MessageBus
from sentientagent_v2.channels.dingtalk import DingTalkChannel


class DingTalkChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_send_posts_message_when_token_available(self) -> None:
        bus = MessageBus()
        channel = DingTalkChannel(
            bus=bus,
            client_id="dt-app-id",
            client_secret="dt-app-secret",
        )

        with (
            patch.object(channel, "_get_access_token", new=AsyncMock(return_value="token-1")),
            patch.object(channel, "_api_call", new=AsyncMock()) as api_call,
        ):
            await channel.send(
                OutboundMessage(
                    channel="dingtalk",
                    chat_id="staff-1",
                    content="hello dingtalk",
                )
            )

        api_call.assert_awaited_once_with(
            "POST",
            "/v1.0/robot/oToMessages/batchSend",
            payload={
                "robotCode": "dt-app-id",
                "userIds": ["staff-1"],
                "msgKey": "sampleMarkdown",
                "msgParam": '{"text":"hello dingtalk","title":"sentientagent_v2 reply"}',
            },
            headers={"x-acs-dingtalk-access-token": "token-1"},
        )

    async def test_on_message_publishes_allowed_inbound(self) -> None:
        bus = MessageBus()
        channel = DingTalkChannel(
            bus=bus,
            client_id="dt-app-id",
            client_secret="dt-app-secret",
            allow_from=["u02"],
        )

        await channel._on_message(content="denied", sender_id="u01", sender_name="alice")
        await channel._on_message(content="allowed", sender_id="u02", sender_name="bob")

        inbound = await asyncio.wait_for(bus.consume_inbound(), timeout=0.2)
        self.assertEqual(inbound.channel, "dingtalk")
        self.assertEqual(inbound.chat_id, "u02")
        self.assertEqual(inbound.sender_id, "u02")
        self.assertEqual(inbound.content, "allowed")
        self.assertEqual(inbound.metadata.get("sender_name"), "bob")


if __name__ == "__main__":
    unittest.main()
