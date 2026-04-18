"""Memory service factory for ADK runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.adk.memory import InMemoryMemoryService

from ..core.config import get_data_dir
from ..core.config import get_agent_home_dir
from .markdown_memory_service import MarkdownMemoryService
from .sqlite_memory_service import SQLiteMemoryService


@dataclass(slots=True)
class MemoryConfig:
    """Runtime memory configuration for openpipixia.

    Attributes:
        enabled: Whether long-term memory is enabled for the runner.
        backend: Memory backend name. Supported values:
            - ``sqlite`` (default)
            - ``markdown`` (legacy local backend)
            - ``in_memory`` (debug fallback)
        markdown_dir: Root directory for markdown memory files.
        sqlite_db_path: SQLite database path for the primary backend.
    """

    enabled: bool
    backend: str
    markdown_dir: str
    sqlite_db_path: str = ""


def _parse_enabled(raw: str | None, *, default: bool) -> bool:
    """Parse common truthy/falsey env values with a deterministic fallback."""
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if not normalized:
        return default
    return normalized not in {"0", "false", "off", "no"}


def _default_markdown_dir() -> Path:
    """Resolve default markdown memory directory.

    By default memory files are colocated with agent bootstrap files so the
    runtime consistently uses ``<agent_home>/memory/{MEMORY.md,HISTORY.md}``.
    """
    return get_agent_home_dir() / "memory"


def _default_sqlite_db_path() -> Path:
    """Resolve default SQLite memory database path."""
    db_path = get_data_dir() / "database" / "memory.db"
    return db_path


def load_memory_config() -> MemoryConfig:
    """Load memory configuration from environment variables.

    Environment variables:
        - ``OPENPPX_MEMORY_ENABLED`` (default: ``1``)
        - ``OPENPPX_MEMORY_BACKEND`` (default: ``sqlite``)
        - ``OPENPPX_MEMORY_DB_PATH`` (optional)
        - ``OPENPPX_MEMORY_MARKDOWN_DIR`` (optional)
    """
    enabled = _parse_enabled(
        os.getenv("OPENPPX_MEMORY_ENABLED"),
        default=True,
    )
    backend = (
        os.getenv("OPENPPX_MEMORY_BACKEND", "sqlite").strip().lower() or "sqlite"
    )
    markdown_dir = os.getenv("OPENPPX_MEMORY_MARKDOWN_DIR", "").strip() or str(_default_markdown_dir())
    sqlite_db_path = os.getenv("OPENPPX_MEMORY_DB_PATH", "").strip() or str(_default_sqlite_db_path())
    return MemoryConfig(
        enabled=enabled,
        backend=backend,
        markdown_dir=markdown_dir,
        sqlite_db_path=sqlite_db_path,
    )


def create_memory_service(config: MemoryConfig | None = None) -> Any | None:
    """Create an ADK memory service instance from runtime config.

    Fallback behavior is intentionally conservative:
    - If memory is disabled, returns ``None``.
    - Unknown backends fall back to in-memory to keep the agent runnable.
    """
    cfg = config or load_memory_config()
    if not cfg.enabled:
        return None

    if cfg.backend == "sqlite":
        return SQLiteMemoryService(db_path=cfg.sqlite_db_path or str(_default_sqlite_db_path()))
    if cfg.backend == "markdown":
        return MarkdownMemoryService(root_dir=cfg.markdown_dir)
    return InMemoryMemoryService()
