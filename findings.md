# Findings & Decisions

## Requirements
- 对齐 OpenClaw 的安装/引导能力，高优先是 daemon 安装能力。
- 每次小步实现，且完整测试通过。

## Research Findings
- OpenClaw 支持 onboarding `--install-daemon`（`../openclaw/src/cli/program/register.onboard.ts:102`）。
- Openheron 目前仅有 `install/onboard/doctor`，无 daemon install 命令。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 先做 runtime/gateway_service.py 基础能力 | 便于后续 CLI 复用并独立测试 |
| 先提供纯渲染函数，不直接写系统目录 | 降低副作用，便于单测验证与跨平台复用 |
| CLI 先做 `gateway-service install/status` | 先实现最小可用能力，再迭代到 `gateway install` 语义 |
| doctor --fix 先做“确定性默认修复” | 低风险：无 provider 启用时启用默认 provider、无 channel 启用时启用 local |
| doctor --fix 增加 provider alias 迁移 | 处理 legacy key（如 `openai-codex`）到 canonical key，减少升级断层 |
| doctor --fix 扩展 snake_case 迁移 | 修复历史配置字段命名差异（如 `api_key`、`bot_token`） |
| doctor --fix 输出分组摘要 | 让修复结果可快速判读（defaults/env_backfill/legacy_migration/other） |
| doctor --fix 增加 skipped/failed 可观测 | 便于定位“为什么没修”与“修复保存失败”场景 |
| doctor --fix-dry-run | 先看修复计划不落盘，降低误操作风险 |
| doctor --fix 迁移规则表驱动常量化 | 降低函数内硬编码，便于继续扩展更多 legacy/ENV 规则且不改行为 |
| doctor --fix channel 规则执行器辅助函数化 | 统一 channel 迁移与 env 回填执行路径，减少重复逻辑与后续扩展成本 |
| doctor --fix provider 规则执行器辅助函数化 | 对 provider alias + snake_case 迁移逻辑做集中封装，降低维护复杂度并保持行为稳定 |
| doctor --fix 默认启用逻辑 helper 化 | 将 provider/channel 默认兜底启用逻辑模块化，减少主流程复杂度并便于复用测试 |
| doctor --fix email consent helper 化 | 将 email 同意标记回填逻辑独立，保证规则边界清晰并便于后续扩展 |
| doctor --fix provider env backfill helper 化 | 将 active provider 的 API key 回填逻辑独立，方便后续扩展更多 provider 凭证修复规则 |
| doctor --fix 内部结构化 event 记录 | 在保持文本输出兼容前提下统一记录 outcome/code/rule/message，为后续 JSON 可观测增强打基础 |
| doctor --json fix 增强 reasonCodes/byRule | 对外暴露可统计的修复原因与规则维度聚合，方便上层自动诊断与策略反馈 |
| doctor --fix e2e 场景回归扩展 | 覆盖真实 apply mixed outcome 与 save-failure 路径，降低后续规则迭代回归风险 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 无 | - |

## Resources
- `docs/OPENCLAW_INSTALL_ALIGNMENT.md`
- `openheron/cli.py`
- `../openclaw/src/cli/program/register.onboard.ts`
- `openheron/runtime/gateway_service.py`
- `tests/test_runtime_gateway_service.py`
- `tests/test_cli.py`
- `docs/OPERATIONS.md`
- `README.md`

## Visual/Browser Findings
- 本轮无。
