"""Shared text extraction helpers for openpipixia memory backends."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from google.adk.memory.memory_entry import MemoryEntry


_FACT_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "preferences",
        (
            "i prefer",
            "i like",
            "i don't like",
            "i dislike",
            "prefer to",
            "preference",
            "我喜欢",
            "我不喜欢",
            "偏好",
            "习惯",
        ),
    ),
    (
        "relationships",
        (
            "my wife",
            "my husband",
            "my girlfriend",
            "my boyfriend",
            "my friend",
            "my manager",
            "my team",
            "colleague",
            "关系",
            "朋友",
            "同事",
            "家人",
            "团队",
        ),
    ),
    (
        "context",
        (
            "my project",
            "our project",
            "working on",
            "deadline",
            "background",
            "my name is",
            "i am",
            "i'm",
            "我叫",
            "我是",
            "项目",
            "背景",
            "目标",
            "计划",
            "仓库",
        ),
    ),
)


def _parts_from_content(content: object) -> list[object]:
    """Return a best-effort parts list from a loose content-like object."""
    if content is None:
        return []
    if isinstance(content, Mapping):
        raw_parts = content.get("parts")
        return list(raw_parts) if isinstance(raw_parts, list) else []
    raw_parts = getattr(content, "parts", None)
    return list(raw_parts) if isinstance(raw_parts, list) else []


def _part_text(part: object) -> str:
    """Extract a text field from one content part object."""
    if isinstance(part, Mapping):
        text = part.get("text")
    else:
        text = getattr(part, "text", None)
    return text if isinstance(text, str) else ""


def content_text_lines(content: object) -> list[str]:
    """Extract text parts from one content-like object in original order."""
    lines: list[str] = []
    for part in _parts_from_content(content):
        text = _part_text(part)
        if text:
            lines.append(text)
    return lines


def event_text_lines(event: object) -> list[str]:
    """Extract text parts from one ADK event-like object in original order."""
    return content_text_lines(getattr(event, "content", None))


def content_text_for_memory(content: object) -> str:
    """Return normalized inline text suitable for fact extraction."""
    lines = content_text_lines(content)
    if not lines:
        return ""
    return " ".join(segment.strip() for segment in lines if segment.strip()).strip()


def event_text_for_memory(event: object) -> str:
    """Return normalized event text suitable for fact extraction."""
    return content_text_for_memory(getattr(event, "content", None))


def event_text_for_history(event: object) -> str:
    """Return raw event text transcript suitable for archive storage."""
    lines = event_text_lines(event)
    if not lines:
        return ""
    return "\n".join(lines)


def tokenize(text: str) -> set[str]:
    """Tokenize text for lightweight keyword matching."""
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text)}


def iso_from_unix_seconds(raw: object) -> str | None:
    """Convert unix timestamp seconds to ISO8601 string when possible."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def now_iso() -> str:
    """Return current UTC time in ISO8601 format."""
    return datetime.now(timezone.utc).isoformat()


def event_timestamp_iso(event: object) -> str:
    """Resolve one event timestamp, falling back to current UTC time."""
    return iso_from_unix_seconds(getattr(event, "timestamp", None)) or now_iso()


def is_user_author(author: str) -> bool:
    """Return whether one author marker should be treated as a human user."""
    normalized = (author or "").strip().lower()
    if not normalized:
        return False
    if normalized in {"user", "human"}:
        return True
    if normalized.endswith("user"):
        return True
    return False


def infer_fact_category(text: str) -> str | None:
    """Infer one durable-fact category from text when possible."""
    lowered = text.lower()
    for category, keywords in _FACT_CATEGORY_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return category
    return None


def normalize_memory_text(text: str) -> str:
    """Return a normalized memory string used for dedupe and hashing."""
    return " ".join((text or "").strip().lower().split())


def build_fact_key(*, category: str, text: str) -> str:
    """Build a stable fact fingerprint from category plus normalized text."""
    normalized = normalize_memory_text(text)
    digest = hashlib.sha1(f"{category}\n{normalized}".encode("utf-8")).hexdigest()
    return digest[:40]


def memory_entry_text(memory: MemoryEntry | str | object) -> str:
    """Extract best-effort plain text from one explicit memory item."""
    if isinstance(memory, str):
        return memory.strip()
    if isinstance(memory, MemoryEntry):
        return content_text_for_memory(memory.content)
    return content_text_for_memory(getattr(memory, "content", None))
