"""Structured access policy decisions for runtime query surfaces."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """One access-policy result with scope and audit-friendly reason data."""

    allow: bool
    reason: str
    access_kind: str
    requester_principal_id: str
    agent_id: str
    relation_to_agent: str = "none"
    scope_kind: str = "none"
    visible_principal_ids: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def allow_scope(
        cls,
        *,
        reason: str,
        access_kind: str,
        requester_principal_id: str,
        agent_id: str,
        relation_to_agent: str,
        scope_kind: str,
        visible_principal_ids: Iterable[str] = (),
    ) -> "AccessDecision":
        """Build one allow decision with an explicit visible scope."""
        return cls(
            allow=True,
            reason=reason,
            access_kind=access_kind,
            requester_principal_id=requester_principal_id,
            agent_id=agent_id,
            relation_to_agent=relation_to_agent,
            scope_kind=scope_kind,
            visible_principal_ids=frozenset(str(item) for item in visible_principal_ids if str(item).strip()),
        )

    @classmethod
    def deny(
        cls,
        *,
        reason: str,
        access_kind: str,
        requester_principal_id: str,
        agent_id: str,
        relation_to_agent: str = "none",
    ) -> "AccessDecision":
        """Build one deny decision with no visible scope."""
        return cls(
            allow=False,
            reason=reason,
            access_kind=access_kind,
            requester_principal_id=requester_principal_id,
            agent_id=agent_id,
            relation_to_agent=relation_to_agent,
            scope_kind="none",
        )

    def allows_principal(self, principal_id: str) -> bool:
        """Return whether the decision grants access to the target principal."""
        if not self.allow:
            return False
        if self.scope_kind == "all":
            return True
        return str(principal_id) in self.visible_principal_ids

    def resolved_scope(self, all_principal_ids: Iterable[str]) -> tuple[str, ...]:
        """Resolve the effective principal scope for iteration."""
        if not self.allow:
            return ()
        if self.scope_kind == "all":
            return tuple(str(item) for item in all_principal_ids if str(item).strip())
        return tuple(sorted(self.visible_principal_ids))
