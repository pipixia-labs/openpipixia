"""Small ADK helpers shared across CLI and gateway."""

from __future__ import annotations

from google.genai import types


def extract_text(content: types.Content | None) -> str:
    """Join text parts from an ADK content payload without altering spacing."""
    if content is None or not content.parts:
        return ""
    return "".join(getattr(part, "text", "") for part in content.parts if getattr(part, "text", None))


def _longest_suffix_prefix_overlap(current: str, candidate: str) -> int:
    """Return longest overlap where current suffix equals candidate prefix."""
    max_overlap = min(len(current), len(candidate))
    for size in range(max_overlap, 0, -1):
        if current.endswith(candidate[:size]):
            return size
    return 0


def merge_text_stream(current: str, new_text: str) -> str:
    """Merge streamed ADK text supporting delta chunks, snapshots, and finals."""
    candidate = new_text or ""
    if not candidate.strip():
        return current
    if not current:
        return candidate
    if candidate == current:
        return current
    # Snapshot stream: "hello" -> "hello world".
    if candidate.startswith(current):
        return candidate
    # Repeated shorter chunk after a fuller snapshot/final.
    if current.startswith(candidate):
        return current
    overlap = _longest_suffix_prefix_overlap(current, candidate)
    if overlap:
        return current + candidate[overlap:]
    return current + candidate
