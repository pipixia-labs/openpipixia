"""Behavior tests for markdown-backed memory service."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import dataclass

from sentientagent_v2.runtime.markdown_memory_service import MarkdownMemoryService


@dataclass(slots=True)
class _Part:
    text: str


@dataclass(slots=True)
class _Content:
    parts: list[_Part]


@dataclass(slots=True)
class _Event:
    id: str
    author: str
    content: _Content


@dataclass(slots=True)
class _Session:
    app_name: str
    user_id: str
    id: str
    events: list[_Event]


class MarkdownMemoryServiceTests(unittest.TestCase):
    def test_add_events_and_search(self) -> None:
        async def _scenario() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                service = MarkdownMemoryService(root_dir=tmp)
                events = [
                    _Event(id="e1", author="user", content=_Content(parts=[_Part(text="My project is Alpha")])),
                    _Event(id="e2", author="agent", content=_Content(parts=[_Part(text="Noted project details")])),
                ]
                await service.add_events_to_memory(
                    app_name="sentientagent_v2",
                    user_id="user-1",
                    session_id="s1",
                    events=events,
                )
                response = await service.search_memory(
                    app_name="sentientagent_v2",
                    user_id="user-1",
                    query="alpha",
                )
                self.assertEqual(len(response.memories), 1)
                text = response.memories[0].content.parts[0].text or ""
                self.assertIn("Alpha", text)

        asyncio.run(_scenario())

    def test_search_is_user_scoped(self) -> None:
        async def _scenario() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                service = MarkdownMemoryService(root_dir=tmp)
                await service.add_memory(
                    app_name="sentientagent_v2",
                    user_id="alice",
                    memories=["Alice likes green tea"],
                )
                await service.add_memory(
                    app_name="sentientagent_v2",
                    user_id="bob",
                    memories=["Bob likes black coffee"],
                )
                response = await service.search_memory(
                    app_name="sentientagent_v2",
                    user_id="bob",
                    query="green tea",
                )
                self.assertEqual(len(response.memories), 0)

        asyncio.run(_scenario())

    def test_add_session_deduplicates_event_ids(self) -> None:
        async def _scenario() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                service = MarkdownMemoryService(root_dir=tmp)
                session = _Session(
                    app_name="sentientagent_v2",
                    user_id="user-2",
                    id="session-1",
                    events=[
                        _Event(
                            id="event-42",
                            author="user",
                            content=_Content(parts=[_Part(text="Remember deduplication behavior")]),
                        )
                    ],
                )
                await service.add_session_to_memory(session)
                await service.add_session_to_memory(session)
                response = await service.search_memory(
                    app_name="sentientagent_v2",
                    user_id="user-2",
                    query="deduplication",
                )
                self.assertEqual(len(response.memories), 1)

        asyncio.run(_scenario())

    def test_add_memory_is_searchable(self) -> None:
        async def _scenario() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                service = MarkdownMemoryService(root_dir=tmp)
                await service.add_memory(
                    app_name="sentientagent_v2",
                    user_id="user-3",
                    memories=["Lives in Seattle", "Prefers morning meetings"],
                )
                response = await service.search_memory(
                    app_name="sentientagent_v2",
                    user_id="user-3",
                    query="Seattle",
                )
                self.assertEqual(len(response.memories), 1)
                self.assertIn("Seattle", response.memories[0].content.parts[0].text or "")

        asyncio.run(_scenario())


if __name__ == "__main__":
    unittest.main()

