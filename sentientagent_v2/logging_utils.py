"""Logging helpers with a Loguru-first backend."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger


def emit_debug(tag: str, payload: Any) -> None:
    """Emit a debug line in a consistent format."""
    try:
        body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        body = str(payload)

    # depth=2 points to the original caller above local `_debug` wrappers.
    logger.opt(depth=2).debug("[DEBUG] {}: {}", tag, body)
