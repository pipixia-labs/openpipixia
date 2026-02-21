# openheron

`openheron` is a lightweight, skills-first agent runtime built on Google ADK.

It focuses on:

- Multi-channel gateway execution
- Local skill loading (`SKILL.md`)
- Built-in action tools (file/shell/web/message/cron/subagent)
- Persistent session + optional long-term memory

Compared with larger systems, this project keeps the core runtime compact and easy to iterate.

## Quick Start

```bash
cd openheron
pip install -e .
openheron onboard
python -m openheron.cli -m "Describe what you can do"
```

## Common Commands

```bash
# local gateway
python -m openheron.cli gateway-local

# multi-channel gateway
openheron gateway --channels local,feishu --interactive-local

# diagnostics
openheron doctor
openheron skills
```

## Core Capabilities

- Runtime: Google ADK (`LlmAgent` + tools + callbacks)
- Session: SQLite-backed ADK session service
- Memory backends: `in_memory` / `markdown`
- Context compaction: ADK `EventsCompactionConfig`
- Slash commands: `/help` and `/new`
- Channel bridge: local + mainstream chat connectors

## Project Layout

```text
openheron/
├── README.md
├── docs/
├── openheron/
├── tests/
└── scripts/
```

## Documentation

Detailed docs are in [`docs/`](./docs/):

- [`docs/PROJECT_OVERVIEW.md`](./docs/PROJECT_OVERVIEW.md)
- [`docs/OPERATIONS.md`](./docs/OPERATIONS.md)
- [`docs/CONFIGURATION.md`](./docs/CONFIGURATION.md)
- [`docs/MCP_SECURITY.md`](./docs/MCP_SECURITY.md)
- [`docs/README.md`](./docs/README.md)

## Testing

```bash
source .venv/bin/activate
pytest -q
```
