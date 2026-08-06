# Moodtag Interaction Flows

This document fixes the visible workflow before implementation. The UI is state-first: show what is ready and the next meaningful action, not a command reference.

## Home

```text
Moodtag

欢迎回来。

AI 已配置
当前 Profile：Editorial

────────────────────────

① 开始打标签
② 更换 Profile
③ 配置 AI
q 退出
```

- Hide provider, endpoint, model ID, log path, and advanced flags.
- `①` opens board input. `②` returns to Home after persistence. `③` returns to Home after confirmed save or cancellation.
- Missing model setup changes only the readiness line to `AI 需要配置`; starting tagging routes to configuration before model probing.

## Tagging Confirmation

```text
Moodtag

将分析：

✓ 人像 / 春季

42 张图片
36 张需要分析
6 张已经完成

使用 Editorial Profile
AI 已配置

开始？[y/N]
```

- Describe the action, not the system internals.
- Confirm before any Eagle metadata write.
- After acceptance, replace the active region so processing owns the screen focus.

## Preparation

```text
… 准备中
```

- yaspin represents short unknown-duration waits.
- Internal operations remain hidden at default verbosity.
- A successful readiness check settles to a single completed line before analysis begins.

## Analysis

```text
正在分析

█████████───────────  12 / 36

最近完成：
✓ IMG001
✓ IMG002
! IMG003 已跳过
```

- alive-progress owns the active terminal region, including ETA and FPS when width permits.
- Keep two or three latest outcomes only.
- Completion order, not source index, drives visible activity.

## Write

```text
正在写入

████████████────────  21 / 34
```

- Enter only after analysis phase has produced valid results.
- Cancellation reports any completed writes; it never promises rollback.

## Complete

```text
完成

✓ 已完成 34
! 已跳过 6
× 失败 2

→ 使用 -v 查看图片结果
```

## Detail and Pipe Modes

```text
-q    final summary and errors
default workflow UI
-v    per-item records
-vv   endpoint/model/retry/timing diagnostics, never secrets or content
```

All visible UI is stderr. `--json` writes one final JSON result to stdout and may safely be piped to `jq`.
