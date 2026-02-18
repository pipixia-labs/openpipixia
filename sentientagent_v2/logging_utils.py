"""Logging helpers with a Loguru-first backend."""

from __future__ import annotations

import json
import sys
from typing import Any

try:  # pragma: no cover - depends on runtime env/package install
    from loguru import logger as _loguru_logger
except Exception:  # pragma: no cover - fallback path
    _loguru_logger = None


def emit_debug(tag: str, payload: Any) -> None:
    """Emit a debug line in a consistent format.

    Uses Loguru when available, otherwise falls back to stderr to keep
    local debugging usable before dependencies are refreshed.
    """
    try:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        body = str(payload)

    if _loguru_logger is not None:
        _loguru_logger.debug("[DEBUG] {}: {}", tag, body)
        return
    sys.stderr.write(f"[DEBUG] {tag}: {body}\n")
