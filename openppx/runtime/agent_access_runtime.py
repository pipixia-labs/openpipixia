"""Shared runtime helpers for agent ownership and access bootstrap."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..core.config import load_config
from ..core.config import normalize_agent_privilege_level
from .agent_access_store import AgentAccessStore
from .agent_access_store import AgentRecord
from .identity_models import ResolvedPrincipal
from .identity_store import IdentityStore


@dataclass(slots=True)
class AgentAccessBootstrap:
    """Normalized access-related settings derived from config and env."""

    privilege_level: str
    owner_principal_id: str
    owner_source: str = ""


def load_agent_access_bootstrap(
    *,
    config_path: Path | None = None,
    apply_env_overrides: bool = True,
    default_privilege_level: str = "low",
) -> AgentAccessBootstrap:
    """Load one agent's privilege and owner settings from config/env."""
    try:
        cfg = load_config(config_path)
    except Exception:
        cfg = {}
    agent_cfg = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}

    raw_privilege_level = str(agent_cfg.get("privilegeLevel", "")).strip().lower()
    owner_principal_id = str(agent_cfg.get("ownerPrincipalId", "")).strip()
    owner_source = "config" if owner_principal_id else ""

    if apply_env_overrides:
        env_privilege_level = os.getenv("OPENPPX_AGENT_PRIVILEGE_LEVEL", "").strip().lower()
        env_owner_principal_id = os.getenv("OPENPPX_AGENT_OWNER_PRINCIPAL_ID", "").strip()
        if env_privilege_level:
            raw_privilege_level = env_privilege_level
        if env_owner_principal_id:
            owner_principal_id = env_owner_principal_id
            owner_source = "env"

    return AgentAccessBootstrap(
        privilege_level=normalize_agent_privilege_level(
            raw_privilege_level,
            default=default_privilege_level,
        ),
        owner_principal_id=owner_principal_id,
        owner_source=owner_source,
    )


def ensure_access_principal(
    identity_store: IdentityStore,
    *,
    principal_id: str,
    source: str,
    account_kind: str,
    display_name: str | None = None,
    authenticated: bool = False,
) -> ResolvedPrincipal | None:
    """Ensure one referenced principal exists for access checks and management."""
    normalized_principal_id = str(principal_id or "").strip()
    if not normalized_principal_id:
        return None
    existing = identity_store.get_principal(normalized_principal_id)
    if existing is not None:
        return existing
    return identity_store.put_principal(
        ResolvedPrincipal(
            principal_id=normalized_principal_id,
            principal_type="human",
            privilege_level="minimal",
            account_kind=account_kind,
            display_name=display_name or normalized_principal_id,
            authenticated=authenticated,
            external_subject_id=normalized_principal_id,
            external_display_id=normalized_principal_id,
            metadata={"source": source},
        )
    )


def ensure_owner_principal(
    identity_store: IdentityStore,
    *,
    owner_principal_id: str,
) -> ResolvedPrincipal | None:
    """Ensure the configured owner principal exists for access checks."""
    return ensure_access_principal(
        identity_store,
        principal_id=owner_principal_id,
        source="agent_owner_config",
        account_kind="configured_owner",
    )


def ensure_agent_access_record(
    *,
    agent_id: str,
    identity_store: IdentityStore,
    agent_access_store: AgentAccessStore,
    agent_name: str = "",
    config_path: Path | None = None,
    apply_env_overrides: bool = True,
) -> AgentRecord:
    """Ensure one agent record exists and reflects configured owner settings."""
    existing = agent_access_store.get_agent_record(agent_id)
    existing_owner_source = ""
    if existing is not None:
        existing_owner_source = str(existing.metadata.get("owner_source", "")).strip().lower()
    bootstrap = load_agent_access_bootstrap(
        config_path=config_path,
        apply_env_overrides=apply_env_overrides,
        default_privilege_level=(existing.privilege_level if existing else "low"),
    )
    owner_principal_id = bootstrap.owner_principal_id or (existing.owner_principal_id if existing else "")
    owner_source = bootstrap.owner_source or existing_owner_source
    if existing is not None and existing.owner_principal_id and existing_owner_source not in {"", "config", "env"}:
        owner_principal_id = existing.owner_principal_id
        owner_source = existing_owner_source
    if owner_principal_id:
        ensure_access_principal(
            identity_store,
            principal_id=owner_principal_id,
            source=owner_source or "agent_owner_config",
            account_kind="configured_owner" if owner_source in {"", "config", "env"} else "managed_access",
        )

    metadata = {
        **(existing.metadata if existing else {}),
        "auto_registered": True,
    }
    if owner_source:
        metadata["owner_source"] = owner_source

    return agent_access_store.upsert_agent_record(
        AgentRecord(
            agent_id=agent_id,
            name=(existing.name if existing and existing.name else agent_name or agent_id),
            privilege_level=bootstrap.privilege_level,
            owner_principal_id=owner_principal_id,
            status=(existing.status if existing else "active"),
            config_ref=(
                str(config_path)
                if config_path is not None
                else (existing.config_ref if existing else "")
            ),
            metadata=metadata,
        )
    )
