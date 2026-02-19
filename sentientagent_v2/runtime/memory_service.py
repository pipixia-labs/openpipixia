"""Memory service factory for ADK runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService

from .markdown_memory_service import MarkdownMemoryService


@dataclass(slots=True)
class MemoryConfig:
    """Runtime memory configuration for sentientagent_v2.

    Attributes:
        enabled: Whether long-term memory is enabled for the runner.
        backend: Memory backend name. Supported values:
            - ``in_memory`` (default)
            - ``vertex`` / ``vertex_memory_bank``
            - ``markdown``
        project: Google Cloud project for Vertex Memory Bank.
        location: Google Cloud location for Vertex Memory Bank.
        agent_engine_id: Vertex Agent Engine id for Memory Bank scope.
        markdown_dir: Root directory for markdown memory files.
    """

    enabled: bool
    backend: str
    project: str
    location: str
    agent_engine_id: str
    markdown_dir: str


def _parse_enabled(raw: str | None, *, default: bool) -> bool:
    """Parse common truthy/falsey env values with a deterministic fallback."""
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if not normalized:
        return default
    return normalized not in {"0", "false", "off", "no"}


def load_memory_config() -> MemoryConfig:
    """Load memory configuration from environment variables.

    Environment variables:
        - ``SENTIENTAGENT_V2_MEMORY_ENABLED`` (default: ``1``)
        - ``SENTIENTAGENT_V2_MEMORY_BACKEND`` (default: ``in_memory``)
        - ``SENTIENTAGENT_V2_MEMORY_BANK_PROJECT`` (optional)
        - ``SENTIENTAGENT_V2_MEMORY_BANK_LOCATION`` (optional)
        - ``SENTIENTAGENT_V2_MEMORY_BANK_AGENT_ENGINE_ID`` (optional)
        - ``SENTIENTAGENT_V2_MEMORY_MARKDOWN_DIR`` (optional)
    """
    enabled = _parse_enabled(
        os.getenv("SENTIENTAGENT_V2_MEMORY_ENABLED"),
        default=True,
    )
    backend = (os.getenv("SENTIENTAGENT_V2_MEMORY_BACKEND", "in_memory").strip().lower() or "in_memory")
    project = os.getenv("SENTIENTAGENT_V2_MEMORY_BANK_PROJECT", "").strip()
    location = os.getenv("SENTIENTAGENT_V2_MEMORY_BANK_LOCATION", "").strip()
    agent_engine_id = os.getenv("SENTIENTAGENT_V2_MEMORY_BANK_AGENT_ENGINE_ID", "").strip()
    markdown_dir = os.getenv("SENTIENTAGENT_V2_MEMORY_MARKDOWN_DIR", "").strip() or str(
        Path.home() / ".sentientagent_v2" / "memory"
    )
    return MemoryConfig(
        enabled=enabled,
        backend=backend,
        project=project,
        location=location,
        agent_engine_id=agent_engine_id,
        markdown_dir=markdown_dir,
    )


def create_memory_service(config: MemoryConfig | None = None) -> Any | None:
    """Create an ADK memory service instance from runtime config.

    Fallback behavior is intentionally conservative:
    - If memory is disabled, returns ``None``.
    - If Vertex backend is requested but mandatory id is missing, falls back to
      in-memory to keep the agent runnable.
    """
    cfg = config or load_memory_config()
    if not cfg.enabled:
        return None

    if cfg.backend in {"vertex", "vertex_memory_bank"} and cfg.agent_engine_id:
        return VertexAiMemoryBankService(
            project=cfg.project or None,
            location=cfg.location or None,
            agent_engine_id=cfg.agent_engine_id,
        )
    if cfg.backend == "markdown":
        return MarkdownMemoryService(root_dir=cfg.markdown_dir)
    return InMemoryMemoryService()
