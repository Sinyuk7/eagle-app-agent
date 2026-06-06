# Moodtag Handoff

This document is for external modules, upper-layer agents, or future skills that
need to operate on Eagle folders through the public CLI only.

The boundary is strict:

- Use the `moodtag ...` command only.
- Do not read project source code.
- Do not rely on repo paths, internal scripts, prompts, or implementation
  details.
- Do not install dependencies, create virtual environments, or run `uv`,
  `python`, or package-manager commands unless a maintainer explicitly asks for
  environment setup.

If `moodtag` is unavailable in `PATH`, treat that as an environment problem and
stop. Report that the CLI is not installed or not exposed in the current shell.
Do not try to repair the environment from inside an external module.

## External Contract

An external caller only needs to know:

- which Eagle folder to operate on
- whether the action is read-only or write

`<eagle-folder>` may be an Eagle folder id, exact folder name, or folder path.
If the name is ambiguous, use the folder id.

## Allowed Commands

### 1. Health Check

```sh
moodtag status --board '<eagle-folder>'
```

Read-only. Use this before write operations. It reports folder progress such as
processed and pending item counts.

### 2. Dry Run

```sh
moodtag tag --board '<eagle-folder>'
```

Read-only. It calls the configured model and shows what would be processed, but
does not modify Eagle metadata.

### 3. Main Write Operation

```sh
moodtag tag --board '<eagle-folder>' --write
```

Write mode. Processes pending items and overwrites each processed item's Eagle
`tags` and `annotation` with Moodtag output.

Optional scoped write:

```sh
moodtag tag --board '<eagle-folder>' --write --limit N
```

Use this only when a partial batch is explicitly needed.

### 4. Force Reprocess

```sh
moodtag tag --board '<eagle-folder>' --write --force
```

Write mode. Reprocesses items that already have Moodtag output.

Use this only when the caller explicitly wants a full overwrite.

### 5. Export Folder Context

```sh
moodtag export-context --board '<eagle-folder>' [--output context.md]
```

Read-only. Exports the current Eagle folder into compact Markdown context. It
does not call the model and does not write to Eagle.

Use this when another agent needs the folder content as context.

## Not Part Of The External Contract

External modules should not use or depend on:

- `moodtag brief`
- `moodtag reset`
- `moodtag config`
- `--mock-vl`
- provider/model/base-url flags
- internal validation or E2E scripts
- any direct `python ...` entry point

These exist for maintainers, local development, testing, or controlled manual
operations, not for normal upper-layer integration.

## Output Expectations

Moodtag writes Eagle annotation as a fixed field block:

```text
Brief: ...

Elements: ...

Use: ...

Key: ...

Camera: ...

LightColor: ...
```

Callers must treat this as tool-owned output. Do not construct it manually, and
do not depend on internal prompt or model contract details.

Eagle top-level `tags` are also tool-owned output.

## Failure Handling

Stop and report instead of improvising when:

- `moodtag` command is missing
- Eagle folder cannot be resolved unambiguously
- required environment configuration is unavailable
- the task would require direct source access or internal script usage

The correct escalation is: ask a maintainer to expose a working `moodtag`
environment or to extend the public CLI contract.
