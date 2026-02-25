# Task Plan: OpenClaw install alignment (P0 daemon install)

## Goal
在 openheron 中补齐与 OpenClaw 对齐的 daemon 安装能力（先最小可用实现），并保持测试通过。

## Current Phase
Phase 1

## Phases
### Phase 1: Scope & baseline
- [x] 明确 P0 目标与差异来源
- [x] 记录当前实现边界
- [x] 建立文件化计划
- **Status:** complete

### Phase 2: Minimal service runtime primitives
- [x] 新增 service 相关基础函数（platform/unit content）
- [x] 补单测覆盖基础函数
- [x] 回归现有测试
- **Status:** complete

### Phase 3: CLI install command
- [x] 新增 gateway service install/status 的最小命令
- [x] 补 CLI 测试
- [x] 回归测试
- **Status:** complete

### Phase 4: Docs and smoke
- [x] 更新 OPERATIONS/README 命令示例
- [x] 如有必要更新 smoke 脚本
- [x] 回归测试
- **Status:** complete

### Phase 5: Delivery
- [x] 汇总对齐进度与剩余差距
- [x] 给出下一迭代建议
- **Status:** complete

### Phase 6: doctor fix maintainability
- [x] 将 provider/channel legacy 迁移规则提取为模块级常量
- [x] 将 channel env backfill 映射提取为模块级常量
- [x] 补回归测试并执行完整回归
- **Status:** complete

### Phase 7: doctor fix channel rule execution helper
- [x] 抽取 channel legacy migration helper
- [x] 抽取 channel env backfill helper
- [x] 补跳过原因测试并执行完整回归
- **Status:** complete

### Phase 8: doctor fix provider rule execution helper
- [x] 抽取 provider legacy migration helper
- [x] 补 provider skipped reason 回归测试
- [x] 执行完整回归
- **Status:** complete

### Phase 9: doctor defaults helper extraction
- [x] 抽取 provider 默认启用 helper
- [x] 抽取 channel 默认启用 helper
- [x] 补 helper 单测并执行完整回归
- **Status:** complete

### Phase 10: doctor email consent helper extraction
- [x] 抽取 email consent env 回填 helper
- [x] 补 true/non-truthy 回归测试
- [x] 执行完整回归
- **Status:** complete

### Phase 11: doctor provider env helper extraction
- [x] 抽取 provider apiKey env 回填 helper
- [x] 补 helper 单测（active/none 两种路径）
- [x] 执行完整回归
- **Status:** complete

### Phase 12: doctor structured events (internal)
- [x] 引入统一的 doctor fix event 记录结构（outcome/code/rule/message）
- [x] 在 provider/channel/email/save-fail 路径接入 event 记录
- [x] 保持现有文本输出兼容并补 event sink 回归测试
- [x] 执行完整回归
- **Status:** complete

### Phase 13: doctor json observability enhancement
- [x] 在 fix summary 中增加 reasonCodes/byRule 统计输出
- [x] 在 doctor --json 的 fix 顶层增加 reasonCodes/byRule（兼容保留 summary）
- [x] 补 summary/json 回归测试并执行完整回归
- **Status:** complete

### Phase 14: doctor fix e2e coverage expansion
- [x] 增加 apply 场景 e2e 测试（mixed applied/skipped + event sink）
- [x] 增加 save-failure 场景 e2e 测试（failedItems + failed event）
- [x] 执行完整回归
- **Status:** complete

### Phase 15: doctor json docs alignment
- [x] 在 OPERATIONS 增加 doctor --fix --json 字段说明与示例
- [x] 在 README 增加 reasonCodes/byRule 快速指引
- [x] 文档变更自检（无需代码回归）
- **Status:** complete

## Key Questions
1. 第一版是否先只支持 macOS launchd + Linux systemd user？
2. 命令形态先做 `gateway-service` 还是直接 `gateway install`？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先实现 service 基础模块再接 CLI | 小步迭代、降低回归风险 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
|       | 1       |            |
