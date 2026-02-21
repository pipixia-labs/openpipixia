"""Markdown-backed ADK memory service.

This service persists user-scoped memory into local markdown files and supports
simple keyword-based retrieval.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types


def _sanitize_scope(value: str) -> str:
    """Sanitize scope keys for filesystem-safe paths."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return sanitized or "_"


def _tokenize(text: str) -> set[str]:
    """Tokenize text for lightweight keyword matching."""
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", text)}


def _event_text(event: object) -> str:
    """Extract plain text content from an ADK event-like object."""
    content = getattr(event, "content", None)
    if not content or not getattr(content, "parts", None):
        return ""
    lines: list[str] = []
    for part in content.parts:
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return " ".join(lines).strip()


class MarkdownMemoryService(BaseMemoryService):
    """Local markdown-backed memory service for incremental iteration.

    Storage layout:
    - ``<root>/<app>/<user>/MEMORY.md``: human-readable memory log
    - ``<root>/<app>/<user>/.event_ids.json``: ingested ADK event ids for dedup
    """

    def __init__(self, *, root_dir: str | Path):
        self._root_dir = Path(root_dir).expanduser().resolve()
        self._lock = threading.Lock()

    def _scope_dir(self, *, app_name: str, user_id: str) -> Path:
        return self._root_dir / _sanitize_scope(app_name) / _sanitize_scope(user_id)

    def _memory_file(self, *, app_name: str, user_id: str) -> Path:
        return self._scope_dir(app_name=app_name, user_id=user_id) / "MEMORY.md"

    def _event_ids_file(self, *, app_name: str, user_id: str) -> Path:
        return self._scope_dir(app_name=app_name, user_id=user_id) / ".event_ids.json"

    def _load_event_ids(self, *, app_name: str, user_id: str) -> set[str]:
        event_ids_path = self._event_ids_file(app_name=app_name, user_id=user_id)
        if not event_ids_path.exists():
            return set()
        try:
            raw = json.loads(event_ids_path.read_text(encoding="utf-8"))
        except Exception:
            return set()
        if not isinstance(raw, list):
            return set()
        return {str(item) for item in raw if isinstance(item, str) and item}

    def _save_event_ids(self, *, app_name: str, user_id: str, event_ids: set[str]) -> None:
        scope_dir = self._scope_dir(app_name=app_name, user_id=user_id)
        scope_dir.mkdir(parents=True, exist_ok=True)
        event_ids_path = self._event_ids_file(app_name=app_name, user_id=user_id)
        payload = sorted(event_ids)
        event_ids_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_markdown_block(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str | None,
        items: Sequence[tuple[str, str]],
        block_title: str,
    ) -> None:
        scope_dir = self._scope_dir(app_name=app_name, user_id=user_id)
        scope_dir.mkdir(parents=True, exist_ok=True)
        memory_path = self._memory_file(app_name=app_name, user_id=user_id)

        timestamp = self._now_iso()
        session_label = session_id or "-"
        lines: list[str] = [
            f"## {block_title} {timestamp} (session={session_label})",
        ]
        for author, text in items:
            author_label = (author or "unknown").strip() or "unknown"
            lines.append(f"- [{author_label}] {text}")
        lines.append("")
        block = "\n".join(lines)
        with memory_path.open("a", encoding="utf-8") as f:
            f.write(block)

    async def add_session_to_memory(self, session: object) -> None:
        """Ingest all events in a session with event-id deduplication."""
        await self.add_events_to_memory(
            app_name=getattr(session, "app_name", ""),
            user_id=getattr(session, "user_id", ""),
            session_id=getattr(session, "id", None),
            events=getattr(session, "events", []),
        )

    async def add_events_to_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        events: Sequence[object],
        session_id: str | None = None,
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Append new textual events into markdown memory log."""
        _ = custom_metadata
        if not app_name or not user_id:
            return
        if not events:
            return

        with self._lock:
            known_event_ids = self._load_event_ids(app_name=app_name, user_id=user_id)
            pending_rows: list[tuple[str, str]] = []
            new_event_ids: set[str] = set()
            for event in events:
                event_id = getattr(event, "id", "") or ""
                if event_id and event_id in known_event_ids:
                    continue
                text = _event_text(event)
                if not text:
                    continue
                author = str(getattr(event, "author", "") or "").strip() or "unknown"
                pending_rows.append((author, text))
                if event_id:
                    new_event_ids.add(event_id)

            if not pending_rows:
                return

            self._append_markdown_block(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                items=pending_rows,
                block_title="SessionEvents",
            )
            if new_event_ids:
                known_event_ids.update(new_event_ids)
                self._save_event_ids(app_name=app_name, user_id=user_id, event_ids=known_event_ids)

    async def add_memory(
        self,
        *,
        app_name: str,
        user_id: str,
        memories: Sequence[str],
        custom_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Append explicit memory items into markdown memory log."""
        _ = custom_metadata
        if not app_name or not user_id:
            return
        rows = []
        for raw in memories:
            text = (raw or "").strip()
            if text:
                rows.append(("memory", text))
        if not rows:
            return
        with self._lock:
            self._append_markdown_block(
                app_name=app_name,
                user_id=user_id,
                session_id=None,
                items=rows,
                block_title="ExplicitMemory",
            )

    async def search_memory(self, *, app_name: str, user_id: str, query: str) -> SearchMemoryResponse:
        """Search markdown memory lines using case-insensitive keyword matching."""
        response = SearchMemoryResponse()
        if not app_name or not user_id:
            return response

        memory_path = self._memory_file(app_name=app_name, user_id=user_id)
        if not memory_path.exists():
            return response

        query_tokens = _tokenize(query)
        if not query_tokens:
            return response

        with self._lock:
            lines = memory_path.read_text(encoding="utf-8").splitlines()

        for line in lines:
            if not line.startswith("- ["):
                continue
            # line format: - [author] text
            match = re.match(r"^- \[(.*?)\]\s*(.*)$", line)
            if not match:
                continue
            author = match.group(1).strip() or None
            text = match.group(2).strip()
            if not text:
                continue
            if query_tokens.isdisjoint(_tokenize(text)):
                continue
            response.memories.append(
                MemoryEntry(
                    author=author,
                    timestamp=None,
                    content=types.Content(role="user", parts=[types.Part(text=text)]),
                )
            )

        return response

