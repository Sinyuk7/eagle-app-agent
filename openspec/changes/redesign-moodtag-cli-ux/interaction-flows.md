# Moodtag Interaction Flows

This document fixes the visible workflow before implementation. The UI is state-first: show what is ready and the next meaningful action, not a command reference.

## Home

```text
Moodtag

Model: Ready
Tagging style (current: Editorial)

→ What would you like to do?
1. Tag a board
2. Choose tagging style
3. Model setup
q. Quit
```

- Hide provider, endpoint, model ID, log path, and advanced flags.
- `①` opens board input. `②` returns to Home after persistence. `③` returns to Home after confirmed save or cancellation.
- Missing model setup changes only the readiness line to `Model: Needs setup`; starting tagging routes to configuration before model probing.

## Tagging Confirmation

```text
Ready to tag "Portrait / Spring"

42 images total · 36 to tag · 6 already tagged
Tagging style: Editorial · Model: Ready
! Existing tags and notes will be replaced.

Start tagging and update Eagle? [y/N]
```

- Describe the action, not the system internals.
- Confirm before any Eagle metadata write.
- After acceptance, replace the active region so processing owns the screen focus.

## Preparation

```text
… Connecting to Eagle and model
```

- yaspin represents short unknown-duration waits.
- Internal operations remain hidden at default verbosity.
- A successful readiness check settles to a single completed line before analysis begins.

## Analysis

```text
Analyzing

█████████───────────  12 / 36

Recent:
✓ IMG001
✓ IMG002
! IMG003 skipped
```

- alive-progress owns the active terminal region, including ETA and FPS when width permits.
- Keep two or three latest outcomes only.
- Completion order, not source index, drives visible activity.

## Write

```text
Updating Eagle

████████████────────  21 / 34
```

- Enter only after analysis phase has produced valid results.
- Cancellation reports any completed writes; it never promises rollback.

## Complete

```text
Complete

✓ 34 updated
! 6 skipped
× 2 failed

→ Use -v for image results
```

## Detail and Pipe Modes

```text
-q    final summary and errors
default workflow UI
-v    per-item records
-vv   endpoint/model/retry/timing diagnostics, never secrets or content
```

All visible UI is stderr. `--json` writes one final JSON result to stdout and may safely be piped to `jq`.
