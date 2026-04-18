"""Serializable invocation-scoped interaction context for gateway/runtime use."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


INTERACTION_CONTEXT_STATE_KEY = "temp:_openppx:ctx"
MEMORY_INGEST_OFFSET_STATE_KEY = "temp:_openppx:ingest_offset"


@dataclass(slots=True)
class InteractionContext:
    """Invocation-scoped identity and routing context written into ADK state."""

    app_name: str
    agent_id: str
    session_id: str
    session_route_key: str
    channel: str
    chat_id: str
    requester_principal_id: str
    requester_principal_type: str
    requester_level: str
    requester_relation_to_agent: str
    requester_account_kind: str
    authenticated: bool
    requester_display_name: str = ""
    external_subject_id: str = ""
    external_display_id: str = ""
    memory_ingest_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_state_value(self) -> dict[str, Any]:
        """Return a plain dict suitable for `state_delta` transport."""
        return {
            "app_name": self.app_name,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "session_route_key": self.session_route_key,
            "channel": self.channel,
            "chat_id": self.chat_id,
            "requester_principal_id": self.requester_principal_id,
            "requester_principal_type": self.requester_principal_type,
            "requester_level": self.requester_level,
            "requester_relation_to_agent": self.requester_relation_to_agent,
            "requester_account_kind": self.requester_account_kind,
            "authenticated": self.authenticated,
            "requester_display_name": self.requester_display_name,
            "external_subject_id": self.external_subject_id,
            "external_display_id": self.external_display_id,
            "memory_ingest_enabled": self.memory_ingest_enabled,
            "metadata": dict(self.metadata),
        }

    def to_state_delta(self, *, ingest_offset: int | None = None) -> dict[str, Any]:
        """Return the `state_delta` payload for one runner invocation."""
        state_delta: dict[str, Any] = {
            INTERACTION_CONTEXT_STATE_KEY: self.to_state_value(),
        }
        if ingest_offset is not None:
            state_delta[MEMORY_INGEST_OFFSET_STATE_KEY] = ingest_offset
        return state_delta
