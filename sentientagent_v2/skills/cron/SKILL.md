---
name: cron
description: Schedule reminders and recurring tasks.
---

# Cron

Use the `cron` tool to schedule reminders or recurring tasks.

## Three Modes

1. **Reminder** - message is sent directly to user
2. **Task** - message is a task description, agent executes and sends result
3. **One-time** - runs once at a specific time, then auto-deletes

## Examples

Fixed reminder:
```
cron(action="add", message="Time to take a break!", every_seconds=1200)
```

Dynamic task (agent executes each time):
```
cron(action="add", message="Check HKUDS/nanobot GitHub stars and report", every_seconds=600)
```

One-time scheduled task (compute ISO datetime from current time):
```
cron(action="add", message="Remind me about the meeting", at="<ISO datetime>")
```

List/remove:
```
cron(action="list")
cron(action="remove", job_id="abc123")
```

## Time Expressions

| User says | Parameters |
|-----------|------------|
| every 20 minutes | every_seconds: 1200 |
| every hour | every_seconds: 3600 |
| every day at 8am | cron_expr: "0 8 * * *" |
| weekdays at 5pm | cron_expr: "0 17 * * 1-5" |
| at a specific time | at: ISO datetime string (compute from current time) |

## Relative Time Rule (Important)

For requests like "in 20 minutes", "after 2 hours", or "过2分钟/1小时后执行",
the reference point MUST be the **current conversation message time** (the time
this user request is received), NOT gateway startup time.

When converting relative requests to `at`, first get the current time "now",
then compute `at = now + delta`, and pass that absolute ISO datetime to:

```
cron(action="add", message="...", at="<ISO datetime computed from current request time>")
```

Example:
- User says: "2分钟之后，发一个时间到了的消息给我"
- Correct behavior: compute from current request time, then create a one-time
  `at` job based on that computed timestamp.
