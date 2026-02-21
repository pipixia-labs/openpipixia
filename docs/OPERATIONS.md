# openheron 运行与操作指南

## 安装

```bash
cd openheron
pip install -e .
```

## 初始化（推荐）

```bash
openheron onboard
```

初始化后会生成：

- `~/.openheron/config.json`
- `~/.openheron/workspace`

## 运行方式

### 单轮调用

```bash
python -m openheron.cli -m "Describe what you can do"
```

可显式指定会话标识：

```bash
python -m openheron.cli -m "Describe what you can do" --user-id local --session-id demo001
```

### ADK CLI 模式

```bash
adk run openheron
```

### Wrapper CLI

```bash
openheron run
```

### 常用工具命令

```bash
openheron skills
openheron doctor
openheron provider list
openheron provider status
openheron provider status --json
openheron provider login github-copilot
openheron provider login openai-codex
openheron provider login codex
openheron channels login
openheron channels bridge start
openheron channels bridge status
openheron channels bridge stop
```

## Gateway 模式

### 本地通道

```bash
python -m openheron.cli gateway-local
```

### 多通道模式（含 Feishu）

```bash
openheron gateway --channels local,feishu --interactive-local
```

也可通过环境变量指定默认通道：

```bash
export OPENHERON_CHANNELS=feishu
openheron gateway
```

## WhatsApp Bridge

`openheron` 使用本地 Node.js Bridge（Baileys + WebSocket）完成 WhatsApp 登录和消息收发。

```bash
# 前台扫码登录
openheron channels login

# 后台 bridge 生命周期
openheron channels bridge start
openheron channels bridge status
openheron channels bridge stop
```

快速自检：

```bash
scripts/whatsapp_bridge_e2e.sh full
scripts/whatsapp_bridge_e2e.sh smoke
```

## Cron 调度

`openheron` 的 cron 是进程内调度器，不写系统 crontab。只有网关运行时任务才会执行。

- 存储文件：`OPENHERON_WORKSPACE/.openheron/cron_jobs.json`
- 支持调度：`every`、`cron`（可配 `tz`）、`at`

常用命令：

```bash
openheron cron list
openheron cron add --name weather --message "check weather and summarize" --every 300
openheron cron add --name daily --message "daily report" --cron "0 9 * * 1-5" --tz Asia/Shanghai
openheron cron add --name reminder --message "remind me to review PR" --at 2026-02-19T09:30:00
openheron cron add --name push --message "send update" --every 600 --deliver --channel feishu --to ou_xxx
openheron cron run <job_id>
openheron cron enable <job_id>
openheron cron enable <job_id> --disable
openheron cron remove <job_id>
openheron cron status
```

## 测试

```bash
source .venv/bin/activate
pytest -q
```

## 示例

```bash
python -m openheron.cli -m "search for the latest research progress today, and create a PPT for me."
python -m openheron.cli -m "download all PDF files from this page: https://bbs.kangaroo.study/forum.php?mod=viewthread&tid=467"
```
