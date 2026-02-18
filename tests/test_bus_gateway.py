"""Tests for bus and gateway skeleton."""

from __future__ import annotations

import asyncio
import types as pytypes
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

from sentientagent_v2.bus.events import InboundMessage, OutboundMessage
from sentientagent_v2.bus.queue import MessageBus
from sentientagent_v2.gateway import Gateway
from sentientagent_v2.runtime.cron_service import CronJob, CronJobState, CronPayload, CronSchedule


class MessageBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_roundtrip(self) -> None:
        bus = MessageBus()
        inbound = InboundMessage(channel="local", sender_id="u1", chat_id="c1", content="ping")
        outbound = OutboundMessage(channel="local", chat_id="c1", content="pong")

        await bus.publish_inbound(inbound)
        await bus.publish_outbound(outbound)

        got_inbound = await bus.consume_inbound()
        got_outbound = await bus.consume_outbound()

        self.assertEqual(got_inbound.content, "ping")
        self.assertEqual(got_outbound.content, "pong")


class GatewayTests(unittest.TestCase):
    def test_process_message_collects_final_text(self) -> None:
        fake_event_1 = pytypes.SimpleNamespace(content=pytypes.SimpleNamespace(parts=[]))
        fake_event_2 = pytypes.SimpleNamespace(
            content=pytypes.SimpleNamespace(parts=[pytypes.SimpleNamespace(text="gateway answer")])
        )
        captured: dict[str, object] = {}

        class _FakeRunner:
            async def run_async(self, **kwargs):
                captured.update(kwargs)
                yield fake_event_1
                yield fake_event_2

        fake_agent = pytypes.SimpleNamespace(name="sentientagent_v2")
        with patch("sentientagent_v2.gateway.create_runner", return_value=(_FakeRunner(), object())):
            gateway = Gateway(agent=fake_agent, app_name="sentientagent_v2", bus=MessageBus())
            inbound = InboundMessage(
                channel="local",
                sender_id="u1",
                chat_id="c1",
                content="hello",
                timestamp=datetime(2026, 2, 18, 9, 30, tzinfo=timezone.utc),
            )
            outbound = asyncio.run(gateway.process_message(inbound))

        self.assertEqual(outbound.channel, "local")
        self.assertEqual(outbound.chat_id, "c1")
        self.assertEqual(outbound.content, "gateway answer")
        request = captured["new_message"]
        text = request.parts[0].text
        self.assertIn("Current request time: 2026-02-18T09:30:00+00:00 (UTC)", text)
        self.assertIn("Use this as the reference 'now' for relative time expressions", text)
        self.assertIn("\n\nhello", text)

    def test_process_message_merges_stream_snapshots(self) -> None:
        fake_event_1 = pytypes.SimpleNamespace(
            content=pytypes.SimpleNamespace(parts=[pytypes.SimpleNamespace(text="hello")])
        )
        fake_event_2 = pytypes.SimpleNamespace(
            content=pytypes.SimpleNamespace(parts=[pytypes.SimpleNamespace(text="hello world")])
        )

        class _FakeRunner:
            async def run_async(self, **kwargs):
                yield fake_event_1
                yield fake_event_2

        fake_agent = pytypes.SimpleNamespace(name="sentientagent_v2")
        with patch("sentientagent_v2.gateway.create_runner", return_value=(_FakeRunner(), object())):
            gateway = Gateway(agent=fake_agent, app_name="sentientagent_v2", bus=MessageBus())
            inbound = InboundMessage(channel="local", sender_id="u1", chat_id="c1", content="hello")
            outbound = asyncio.run(gateway.process_message(inbound))

        self.assertEqual(outbound.content, "hello world")


class GatewayLoopResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_consume_inbound_continues_after_processing_error(self) -> None:
        class _FakeRunner:
            async def run_async(self, **kwargs):
                if False:
                    yield  # pragma: no cover

        fake_agent = pytypes.SimpleNamespace(name="sentientagent_v2")
        with patch("sentientagent_v2.gateway.create_runner", return_value=(_FakeRunner(), object())):
            bus = MessageBus()
            gateway = Gateway(agent=fake_agent, app_name="sentientagent_v2", bus=bus)

        success_outbound = OutboundMessage(channel="local", chat_id="c2", content="ok")
        gateway.process_message = AsyncMock(side_effect=[RuntimeError("boom"), success_outbound])  # type: ignore[method-assign]

        task = asyncio.create_task(gateway._consume_inbound())
        try:
            await bus.publish_inbound(InboundMessage(channel="local", sender_id="u1", chat_id="c1", content="one"))
            await bus.publish_inbound(InboundMessage(channel="local", sender_id="u1", chat_id="c2", content="two"))

            outbound = await asyncio.wait_for(bus.consume_outbound(), timeout=0.5)
            self.assertEqual(outbound.chat_id, "c2")
            self.assertEqual(outbound.content, "ok")
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task


class GatewayCronTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_and_stop_manage_cron_service(self) -> None:
        class _FakeRunner:
            async def run_async(self, **kwargs):
                if False:
                    yield  # pragma: no cover

        fake_agent = pytypes.SimpleNamespace(name="sentientagent_v2")
        fake_cron_service = pytypes.SimpleNamespace(start=AsyncMock(), stop=Mock())
        with patch("sentientagent_v2.gateway.create_runner", return_value=(_FakeRunner(), object())):
            with patch("sentientagent_v2.gateway.CronService", return_value=fake_cron_service):
                gateway = Gateway(agent=fake_agent, app_name="sentientagent_v2", bus=MessageBus())
                await gateway.start()
                fake_cron_service.start.assert_awaited_once()
                await gateway.stop()
                fake_cron_service.stop.assert_called_once()

    async def test_run_cron_job_delivers_outbound_when_enabled(self) -> None:
        fake_event = pytypes.SimpleNamespace(
            content=pytypes.SimpleNamespace(parts=[pytypes.SimpleNamespace(text="cron answer")])
        )
        captured: dict[str, object] = {}

        class _FakeRunner:
            async def run_async(self, **kwargs):
                captured.update(kwargs)
                yield fake_event

        fake_agent = pytypes.SimpleNamespace(name="sentientagent_v2")
        with patch("sentientagent_v2.gateway.create_runner", return_value=(_FakeRunner(), object())):
            bus = MessageBus()
            gateway = Gateway(agent=fake_agent, app_name="sentientagent_v2", bus=bus)

        job = CronJob(
            id="job12345",
            name="demo",
            enabled=True,
            schedule=CronSchedule(kind="every", every_seconds=60),
            payload=CronPayload(message="do work", deliver=True, channel="local", to="c1"),
            state=CronJobState(),
            created_at_ms=0,
            updated_at_ms=0,
        )
        result = await gateway._run_cron_job(job)
        self.assertEqual(result, "cron answer")
        request = captured["new_message"]
        text = request.parts[0].text
        self.assertTrue(text.startswith("do work"))
        self.assertIn("Current time:", text)

        outbound = await asyncio.wait_for(bus.consume_outbound(), timeout=0.5)
        self.assertEqual(outbound.channel, "local")
        self.assertEqual(outbound.chat_id, "c1")
        self.assertEqual(outbound.content, "cron answer")


if __name__ == "__main__":
    unittest.main()
