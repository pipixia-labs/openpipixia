"""Routing capability flags for channel metadata support."""

from __future__ import annotations


# Channels that can emit stable scope metadata (guild/team/roles) for routing.
SCOPE_METADATA_SUPPORTED_CHANNELS = frozenset({"discord"})


def channel_supports_scope_metadata(channel: str) -> bool:
    """Return whether one channel supports stable guild/team/roles metadata."""
    return str(channel or "").strip().lower() in SCOPE_METADATA_SUPPORTED_CHANNELS


def list_scope_metadata_supported_channels() -> list[str]:
    """Return sorted channel names that support scope metadata."""
    return sorted(SCOPE_METADATA_SUPPORTED_CHANNELS)
