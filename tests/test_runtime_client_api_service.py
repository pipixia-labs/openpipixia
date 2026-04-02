from __future__ import annotations

import io
import json
from pathlib import Path

from google.adk.events.event import Event
from google.genai import types

from openpipixia.runtime.client_api_service import (
    ClientApiCoordinator,
    build_agent_profile,
    list_enabled_agent_names,
    project_session_event,
)
from openpipixia.runtime.session_service import SessionConfig, create_session_service


class _FakeProcess:
    def __init__(self, stdout_text: str, stderr_text: str = "", returncode: int = 0) -> None:
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO(stderr_text)
        self._returncode = returncode
        self.terminated = False

    def poll(self) -> int | None:
        return None if not self.terminated else self._returncode

    def terminate(self) -> None:
        self.terminated = True

    def wait(self) -> int:
        self.terminated = True
        return self._returncode


def test_list_enabled_agent_names_reads_global_config(tmp_path: Path) -> None:
    (tmp_path / "writer").mkdir()
    (tmp_path / "reviewer").mkdir()
    (tmp_path / "global_config.json").write_text(
        json.dumps(
            {
                "agents": [
                    {"name": "writer", "enabled": True},
                    {"name": "reviewer", "enabled": False},
                    {"name": "operator", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )

    names = list_enabled_agent_names(tmp_path)
    assert names == ["writer", "operator"]


def test_build_agent_profile_uses_workspace_description(tmp_path: Path) -> None:
    agent_dir = tmp_path / "writer"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(
        json.dumps({"agent": {"workspace": "workspace/writer"}}),
        encoding="utf-8",
    )

    profile = build_agent_profile("writer", tmp_path)
    assert profile["id"] == "writer"
    assert profile["workspace"] == "workspace/writer"
    assert "Workspace:" in profile["description"]


def test_project_session_event_builds_structured_parts() -> None:
    message = project_session_event(
        {
            "id": "evt_1",
            "author": "assistant",
            "timestamp": 1_717_171_717,
            "content": {
                "parts": [
                    {"text": "I will inspect the repo."},
                    {"function_call": {"id": "call_1", "name": "inspect_repo", "args": {"path": "."}}},
                    {"function_response": {"id": "call_1", "name": "inspect_repo", "response": {"ok": True}}},
                ]
            },
        },
        "session_1",
    )

    assert message["role"] == "assistant"
    assert message["parts"][0]["type"] == "markdown"
    assert message["parts"][1]["type"] == "step_ref"
    assert message["parts"][2]["type"] == "step_ref"
    assert message["parts"][3]["type"] == "code"


def test_project_session_event_skips_unrenderable_events() -> None:
    message = project_session_event(
        {
            "id": "evt_2",
            "author": "system",
            "timestamp": 1_717_171_718,
            "content": {"parts": [{}]},
        },
        "session_2",
    )

    assert message is None


def test_create_run_streams_replayable_events(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "global_config.json").write_text(
        json.dumps({"agents": [{"name": "writer", "enabled": True}]}),
        encoding="utf-8",
    )
    agent_dir = tmp_path / "writer"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(json.dumps({"agent": {"workspace": "workspace/writer"}}), encoding="utf-8")

    stdout_lines = "\n".join(
        [
            json.dumps(
                {
                    "type": "event",
                    "event": {
                        "content": {
                            "parts": [
                                {"function_call": {"id": "call_1", "name": "inspect_repo", "args": {"path": "."}}},
                            ]
                        }
                    },
                }
            ),
            json.dumps({"type": "delta", "text": "hello"}),
            json.dumps({"type": "final", "text": "hello world"}),
        ]
    )

    monkeypatch.setattr(
        "openpipixia.runtime.client_api_service.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout_lines),
    )

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    payload = coordinator.create_run("writer", "session_1", "hi")
    assert payload["ok"] is True
    run_id = payload["data"]["run"]["id"]

    handle = coordinator._runs[run_id]
    assert handle.done.wait(timeout=1.0)

    subscriber = coordinator.stream_run_events(run_id)
    assert subscriber is not None

    events: list[str] = []
    while True:
        item = subscriber.get(timeout=1.0)
        if item is None:
            break
        events.append(item.event)

    assert "run.started" in events
    assert "message.created" in events
    assert "step.updated" in events
    assert "message.delta" in events
    assert "message.completed" in events
    assert "run.finished" in events


def test_create_run_tolerates_null_long_running_tool_ids(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "global_config.json").write_text(
        json.dumps({"agents": [{"name": "writer", "enabled": True}]}),
        encoding="utf-8",
    )
    agent_dir = tmp_path / "writer"
    agent_dir.mkdir()
    (agent_dir / "config.json").write_text(json.dumps({"agent": {"workspace": "workspace/writer"}}), encoding="utf-8")

    stdout_lines = "\n".join(
        [
            json.dumps(
                {
                    "type": "event",
                    "event": {
                        "long_running_tool_ids": None,
                        "content": {
                            "parts": [
                                {"function_call": {"id": "call_2", "name": "inspect_repo", "args": {"path": "."}}},
                            ]
                        },
                    },
                }
            ),
            json.dumps({"type": "final", "text": "done"}),
        ]
    )

    monkeypatch.setattr(
        "openpipixia.runtime.client_api_service.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout_lines),
    )

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    payload = coordinator.create_run("writer", "session_2", "hi")
    assert payload["ok"] is True

    handle = coordinator._runs[payload["data"]["run"]["id"]]
    assert handle.done.wait(timeout=1.0)
    assert handle.failed is False


def test_client_api_reads_sessions_directly_without_worker(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "global_config.json").write_text(
        json.dumps({"agents": [{"name": "writer", "enabled": True}]}),
        encoding="utf-8",
    )
    agent_dir = tmp_path / "writer"
    agent_dir.mkdir()
    (agent_dir / "database").mkdir()
    config_path = agent_dir / "config.json"
    config_path.write_text(json.dumps({"agent": {"workspace": "workspace/writer"}}), encoding="utf-8")

    async def _seed() -> None:
        service = create_session_service(
            SessionConfig(db_url=f"sqlite+aiosqlite:///{agent_dir / 'database' / 'sessions.db'}")
        )
        async with service:
            session = await service.create_session(
                app_name="openpipixia",
                user_id="ppx-client-user",
                session_id="writer-seeded",
            )
            await service.append_event(
                session=session,
                event=Event(
                    invocation_id="inv-1",
                    author="assistant",
                    content=types.Content(role="model", parts=[types.Part.from_text(text="Hello direct path")]),
                ),
            )

    import asyncio

    asyncio.run(_seed())

    monkeypatch.setattr(
        "openpipixia.runtime.client_api_service._run_worker_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("worker path should not be used")),
    )

    coordinator = ClientApiCoordinator(data_dir=tmp_path)
    sessions = coordinator.list_sessions("writer")
    assert sessions["ok"] is True
    assert sessions["data"]["items"][0]["id"] == "writer-seeded"

    messages = coordinator.get_session_messages("writer-seeded")
    assert messages["ok"] is True
    assert messages["data"]["items"][0]["parts"][0]["text"] == "Hello direct path"
