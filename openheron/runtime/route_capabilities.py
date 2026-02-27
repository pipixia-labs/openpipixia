"""Routing capability declarations for channel metadata support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CapabilityLevel = Literal["unsupported", "best_effort", "stable"]


@dataclass(frozen=True, slots=True)
class ScopeCapability:
    """One channel capability declaration for scope metadata routing."""

    level: CapabilityLevel
    reason: str


_SCOPE_CAPABILITIES: dict[str, ScopeCapability] = {
    "discord": ScopeCapability(
        level="best_effort",
        reason="depends on upstream event payload (guild/member roles may be absent)",
    ),
    "telegram": ScopeCapability(
        level="unsupported",
        reason="protocol model does not provide stable guild/team/roles fields",
    ),
    "feishu": ScopeCapability(
        level="unsupported",
        reason="current adapter only normalizes peer/chat_type metadata",
    ),
    "whatsapp": ScopeCapability(
        level="unsupported",
        reason="current routing model focuses on accountId + peer",
    ),
    "local": ScopeCapability(
        level="unsupported",
        reason="local channel has no native organization/role metadata",
    ),
}


def channel_supports_scope_metadata(channel: str) -> bool:
    """Return whether one channel can carry scope metadata for routing."""
    capability = get_scope_capability(channel)
    return capability.level in {"best_effort", "stable"}


def get_scope_capability(channel: str) -> ScopeCapability:
    """Return scope capability for one channel (defaults to unsupported)."""
    normalized = str(channel or "").strip().lower()
    return _SCOPE_CAPABILITIES.get(
        normalized,
        ScopeCapability(
            level="unsupported",
            reason="channel capability is unknown; no stable scope contract declared",
        ),
    )


def list_scope_metadata_supported_channels() -> list[str]:
    """Return sorted channel names that can carry scope metadata."""
    return sorted(
        channel
        for channel, capability in _SCOPE_CAPABILITIES.items()
        if capability.level in {"best_effort", "stable"}
    )
