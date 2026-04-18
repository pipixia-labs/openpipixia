"""Artifact service factory for ADK runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.adk.artifacts import FileArtifactService

from ..core.config import get_data_dir


@dataclass(slots=True)
class ArtifactConfig:
    """Runtime artifact storage configuration."""

    enabled: bool
    root_dir: str


def _parse_enabled(raw: str | None, *, default: bool) -> bool:
    """Parse common truthy/falsey env values with a deterministic fallback."""
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if not normalized:
        return default
    return normalized not in {"0", "false", "off", "no"}


def _default_artifact_dir() -> Path:
    """Return the default filesystem root for local artifacts."""
    root_dir = get_data_dir() / "artifacts"
    root_dir.mkdir(parents=True, exist_ok=True)
    return root_dir


def load_artifact_config() -> ArtifactConfig:
    """Load artifact configuration from environment variables."""
    enabled = _parse_enabled(
        os.getenv("OPENPPX_ARTIFACTS_ENABLED"),
        default=True,
    )
    root_dir = os.getenv("OPENPPX_ARTIFACTS_DIR", "").strip() or str(_default_artifact_dir())
    return ArtifactConfig(enabled=enabled, root_dir=root_dir)


def create_artifact_service(config: ArtifactConfig | None = None) -> Any | None:
    """Create a local file-backed ADK artifact service from runtime config."""
    cfg = config or load_artifact_config()
    if not cfg.enabled:
        return None
    return FileArtifactService(root_dir=cfg.root_dir)
