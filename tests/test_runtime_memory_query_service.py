from __future__ import annotations

import asyncio

from google.adk.memory.memory_entry import MemoryEntry
from google.genai import types

from openpipixia.runtime.access_policy import AccessPolicy
from openpipixia.runtime.agent_access_store import AgentAccessStore, AgentMembership
from openpipixia.runtime.identity_models import ResolvedPrincipal
from openpipixia.runtime.identity_store import IdentityStore
from openpipixia.runtime.memory_query_service import MemoryQueryService
from openpipixia.runtime.sqlite_memory_service import SQLiteMemoryService


def _principal(*, principal_id: str, privilege_level: str = "minimal") -> ResolvedPrincipal:
    return ResolvedPrincipal(
        principal_id=principal_id,
        principal_type="human",
        privilege_level=privilege_level,
        account_kind="local",
        display_name=principal_id,
        authenticated=True,
    )


def _memory(text: str, *, timestamp: str) -> MemoryEntry:
    return MemoryEntry(
        id=f"mem-{abs(hash((text, timestamp)))}",
        author="user",
        timestamp=timestamp,
        content=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
    )


def test_memory_query_service_owner_can_query_participant_scope(tmp_path) -> None:
    db_path = tmp_path / "identity.db"
    memory_db_path = tmp_path / "memory.db"
    identity_store = IdentityStore(db_path=db_path)
    access_store = AgentAccessStore(db_path=db_path)
    owner = identity_store.put_principal(_principal(principal_id="owner"))
    participant = identity_store.put_principal(_principal(principal_id="participant"))
    access_store.set_agent_owner(agent_id="writer", owner_principal_id=owner.principal_id)
    access_store.upsert_membership(
        AgentMembership(agent_id="writer", principal_id=participant.principal_id, relation="participant")
    )

    memory_service = SQLiteMemoryService(db_path=memory_db_path)
    asyncio.run(
        memory_service.add_memory(
            app_name="openpipixia",
            user_id=participant.principal_id,
            memories=[_memory("remember the launch checklist", timestamp="2026-04-18T10:00:00+08:00")],
        )
    )
    query_service = MemoryQueryService(
        identity_store=identity_store,
        access_policy=AccessPolicy(identity_store=identity_store, agent_access_store=access_store),
        memory_service=memory_service,
        audit_db_path=memory_db_path,
    )

    result = asyncio.run(
        query_service.search(
            agent_id="writer",
            requester_principal_id=owner.principal_id,
            query="launch",
        )
    )

    assert result.decision.allow is True
    assert result.decision.reason == "agent_owner_scope"
    assert len(result.memories) == 1
    assert result.memories[0].custom_metadata["subject_principal_id"] == participant.principal_id
    audit_rows = query_service.list_audit_rows()
    assert audit_rows[-1]["requester_principal_id"] == owner.principal_id
    assert audit_rows[-1]["result_count"] == 1


def test_memory_query_service_root_gets_all_principals(tmp_path) -> None:
    db_path = tmp_path / "identity.db"
    memory_db_path = tmp_path / "memory.db"
    identity_store = IdentityStore(db_path=db_path)
    access_store = AgentAccessStore(db_path=db_path)
    root = identity_store.put_principal(_principal(principal_id="root-user", privilege_level="root"))
    user_a = identity_store.put_principal(_principal(principal_id="user-a"))
    user_b = identity_store.put_principal(_principal(principal_id="user-b"))
    memory_service = SQLiteMemoryService(db_path=memory_db_path)
    asyncio.run(
        memory_service.add_memory(
            app_name="openpipixia",
            user_id=user_a.principal_id,
            memories=[_memory("project atlas milestone", timestamp="2026-04-18T09:00:00+08:00")],
        )
    )
    asyncio.run(
        memory_service.add_memory(
            app_name="openpipixia",
            user_id=user_b.principal_id,
            memories=[_memory("atlas postmortem notes", timestamp="2026-04-18T11:00:00+08:00")],
        )
    )
    query_service = MemoryQueryService(
        identity_store=identity_store,
        access_policy=AccessPolicy(identity_store=identity_store, agent_access_store=access_store),
        memory_service=memory_service,
        audit_db_path=memory_db_path,
    )

    result = asyncio.run(
        query_service.search(
            agent_id="writer",
            requester_principal_id=root.principal_id,
            query="atlas",
        )
    )

    subject_ids = [item.custom_metadata["subject_principal_id"] for item in result.memories]
    assert result.decision.allow is True
    assert result.decision.scope_kind == "all"
    assert subject_ids == ["user-b", "user-a"]


def test_memory_query_service_audit_respects_visible_scope(tmp_path) -> None:
    db_path = tmp_path / "identity.db"
    memory_db_path = tmp_path / "memory.db"
    identity_store = IdentityStore(db_path=db_path)
    access_store = AgentAccessStore(db_path=db_path)
    owner = identity_store.put_principal(_principal(principal_id="owner"))
    participant = identity_store.put_principal(_principal(principal_id="participant"))
    access_store.set_agent_owner(agent_id="writer", owner_principal_id=owner.principal_id)
    access_store.upsert_membership(
        AgentMembership(agent_id="writer", principal_id=participant.principal_id, relation="participant")
    )

    query_service = MemoryQueryService(
        identity_store=identity_store,
        access_policy=AccessPolicy(identity_store=identity_store, agent_access_store=access_store),
        memory_service=SQLiteMemoryService(db_path=memory_db_path),
        audit_db_path=memory_db_path,
    )
    asyncio.run(
        query_service.search(
            agent_id="writer",
            requester_principal_id=participant.principal_id,
            query="checklist",
        )
    )
    asyncio.run(
        query_service.search(
            agent_id="writer",
            requester_principal_id=owner.principal_id,
            query="summary",
        )
    )

    participant_rows = query_service.list_audit(
        agent_id="writer",
        requester_principal_id=participant.principal_id,
    )
    owner_rows = query_service.list_audit(
        agent_id="writer",
        requester_principal_id=owner.principal_id,
    )

    assert participant_rows.decision.allow is True
    assert participant_rows.decision.scope_kind == "self"
    assert [row["requester_principal_id"] for row in participant_rows.rows] == ["participant"]
    assert owner_rows.decision.allow is True
    assert owner_rows.decision.scope_kind == "agent"
    assert [row["requester_principal_id"] for row in owner_rows.rows] == ["owner", "participant"]
