from __future__ import annotations

from openppx.runtime.agent_access_store import AgentAccessStore


def test_agent_access_store_records_and_lists_audit_rows(tmp_path) -> None:
    db_path = tmp_path / "identity.db"
    store = AgentAccessStore(db_path=db_path)

    older = store.record_audit(
        agent_id="writer",
        actor_principal_id="owner",
        actor_relation="owner",
        action="upsert_membership",
        target_principal_id="participant",
        details={"relation": "participant"},
        created_at_ms=100,
    )
    newer = store.record_audit(
        agent_id="writer",
        actor_principal_id="root-user",
        actor_relation="root",
        action="set_owner",
        target_principal_id="new-owner",
        details={"previous_owner_principal_id": "owner"},
        created_at_ms=200,
    )

    rows = store.list_audit(agent_id="writer", limit=10)
    filtered_rows = store.list_audit(agent_id="writer", limit=10, actions=("set_owner",))

    assert [row.audit_id for row in rows] == [newer.audit_id, older.audit_id]
    assert [row.audit_id for row in filtered_rows] == [newer.audit_id]
    assert rows[0].details["previous_owner_principal_id"] == "owner"
    assert rows[1].details["relation"] == "participant"
