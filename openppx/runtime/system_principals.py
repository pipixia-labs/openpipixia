"""Definitions for built-in service principals."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemPrincipalDefinition:
    """One built-in system principal definition."""

    principal_id: str
    display_name: str
    privilege_level: str
    account_kind: str = "internal"
    memory_ingest_enabled: bool = False


_SYSTEM_PRINCIPALS: dict[str, SystemPrincipalDefinition] = {
    "heartbeat": SystemPrincipalDefinition(
        principal_id="heartbeat",
        display_name="Heartbeat Runner",
        privilege_level="high",
    ),
    "cron": SystemPrincipalDefinition(
        principal_id="cron",
        display_name="Cron Runner",
        privilege_level="high",
    ),
    "gui_planner": SystemPrincipalDefinition(
        principal_id="gui_planner",
        display_name="GUI Planner",
        privilege_level="high",
    ),
    "gui_grounding": SystemPrincipalDefinition(
        principal_id="gui_grounding",
        display_name="GUI Grounding",
        privilege_level="high",
    ),
}


def get_system_principal(name: str) -> SystemPrincipalDefinition | None:
    """Return the built-in service principal definition for one runtime name."""
    return _SYSTEM_PRINCIPALS.get(str(name or "").strip().lower())
