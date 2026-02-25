# Progress Log

## Session: 2026-02-25

### Phase 1: Scope & baseline
- **Status:** complete
- **Started:** 2026-02-25
- Actions taken:
  - 启用 planning-with-files 并创建 plan/findings/progress。
  - 确认当前缺口集中在 daemon install 能力。
- Files created/modified:
  - `task_plan.md` (created)
  - `findings.md` (created)
  - `progress.md` (created)

### Phase 2: Minimal service runtime primitives
- **Status:** complete
- Actions taken:
  - 新增 `openheron/runtime/gateway_service.py`，提供：
    - service manager 检测（launchd/systemd/unsupported）
    - service name 规范化
    - launchd plist 渲染
    - systemd unit 渲染
  - 新增 `tests/test_runtime_gateway_service.py` 覆盖基础能力。
  - 执行目标测试与完整回归。
- Files created/modified:
  - `openheron/runtime/gateway_service.py` (created)
  - `tests/test_runtime_gateway_service.py` (created)
  - `task_plan.md` (updated)
  - `findings.md` (updated)

### Phase 3: CLI install command
- **Status:** complete
- Actions taken:
  - 新增 `gateway-service` 子命令：
    - `openheron gateway-service install [--force] [--channels ...]`
    - `openheron gateway-service status [--json]`
  - install 行为：
    - 按平台检测 launchd/systemd user
    - 生成并写入用户级 manifest（launchd plist / systemd unit）
    - 输出 enable/disable 提示命令
  - status 行为：
    - 输出 manager / service name / manifest path / exists（文本或 JSON）
  - 新增 CLI 相关测试并通过回归。
- Files created/modified:
  - `openheron/cli.py` (modified)
  - `tests/test_cli.py` (modified)

### Phase 4: Docs and smoke
- **Status:** complete
- Actions taken:
  - 在 README / OPERATIONS 增加 `gateway-service install/status` 用法。
  - 在对齐清单中将 daemon 能力状态更新为“部分对齐（已支持 manifest）”。
  - 完成完整回归测试。
- Files created/modified:
  - `README.md` (modified)
  - `docs/OPERATIONS.md` (modified)
  - `docs/OPENCLAW_INSTALL_ALIGNMENT.md` (modified)

### Phase 5: Delivery
- **Status:** complete
- Actions taken:
  - 为 `gateway-service install` 增加 `--enable`，自动调用 launchctl/systemctl user 启用。
  - 新增 `openheron doctor --fix` 最小闭环：从环境变量回填启用 provider/channel 的缺失关键字段。
  - 扩展 `doctor --fix`：在“无 provider 启用 / 无 channel 启用”时自动修复为默认可运行状态。
  - 扩展 `doctor --fix`：迁移 legacy provider alias key（如 `openai-codex` -> `openai_codex`）。
  - 扩展 `doctor --fix`：迁移 legacy snake_case 键（provider `api_key/api_base`、channel `bot_token/client_id/...`）。
  - 增加 `doctor --fix` 修复分组摘要输出（defaults/env_backfill/legacy_migration/other）并写入 JSON 报告。
  - 增加 `doctor --fix` skipped/failed 统计与明细（文本 summary + JSON `skippedItems`/`failedItems`）。
  - 增加 `doctor --fix-dry-run`（只展示修复计划，不写入配置）。
  - 补充 enable 成功/失败测试，并完成整套回归。
  - 文档同步新增 `--enable` 与 `doctor --fix` 使用方式，并更新对齐清单状态。
- Files created/modified:
  - `openheron/cli.py` (modified)
  - `tests/test_cli.py` (modified)
  - `README.md` (modified)
  - `docs/OPERATIONS.md` (modified)
  - `docs/OPENCLAW_INSTALL_ALIGNMENT.md` (modified)

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Planning files created | ls task_plan.md findings.md progress.md | all exist | all exist | ✓ |
| Runtime service + CLI subset | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py -q` | pass | 90 passed | ✓ |
| Full regression | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 287 passed | ✓ |
| Runtime service + CLI subset (phase 3) | `pytest tests/test_cli.py tests/test_runtime_gateway_service.py -q` | pass | 95 passed | ✓ |
| Full regression (phase 3) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 292 passed | ✓ |
| Full regression (phase 4 docs sync) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 292 passed | ✓ |
| Full regression (phase 5 enable flow) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 294 passed | ✓ |
| Full regression (doctor --fix) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 296 passed | ✓ |
| Full regression (doctor default repairs) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 297 passed | ✓ |
| Full regression (doctor alias migration) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 298 passed | ✓ |
| Full regression (doctor snake_case migration) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 300 passed | ✓ |
| Full regression (doctor fix summary grouping) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 301 passed | ✓ |
| Full regression (doctor fix skipped/failed visibility) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 301 passed | ✓ |
| Full regression (doctor fix dry-run) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 303 passed | ✓ |
| Full regression (doctor rules table refactor) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 304 passed | ✓ |
| Full regression (doctor channel helper refactor) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 305 passed | ✓ |
| Full regression (doctor provider helper refactor) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 306 passed | ✓ |
| Full regression (doctor defaults helper refactor) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 308 passed | ✓ |
| Full regression (doctor email consent helper refactor) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 310 passed | ✓ |
| Full regression (doctor provider env helper refactor) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 312 passed | ✓ |
| Full regression (doctor structured events internal) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 313 passed | ✓ |
| Full regression (doctor json reasonCodes/byRule) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 315 passed | ✓ |
| Full regression (doctor e2e coverage expansion) | `pytest tests/test_runtime_gateway_service.py tests/test_cli.py tests/test_runtime_heartbeat_status_store.py tests/test_bus_gateway.py tests/test_runtime_heartbeat_runner.py tests/test_runtime_heartbeat_utils.py tests/test_tools.py tests/test_config.py tests/test_runtime_cron_service.py tests/test_channels_factory.py -q` | pass | 317 passed | ✓ |
| Docs sync (doctor json reasonCodes/byRule) | README + docs/OPERATIONS 更新 | doc-only | done | ✓ |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
|           |       | 1       |            |

## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | 本轮计划完成并扩展 doctor --fix 最小闭环 |
| Where am I going? | 下个高优：扩展 doctor --fix 迁移能力 |
| What's the goal? | 补齐 daemon install 最小能力 |
| What have I learned? | OpenClaw 有 install-daemon，openheron 缺失 |
| What have I done? | 完成 service 模块 + CLI + auto-enable + doctor --fix 默认修复 + 文档同步 + 回归 |
