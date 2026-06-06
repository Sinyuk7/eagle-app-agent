# Moodtag Handoff

This document is for upper-layer agents or future Codex skills that call this
repo. Treat provider/model/API configuration as internal repo setup. A caller
should only care about the Eagle folder to operate on and whether the command is
read-only or writes Eagle metadata.

## Caller-Facing Entry Points

Run commands from the repo root.

```sh
python moodtag.py status --board '<eagle-folder>'
```

Read-only health check. Use this before write operations. It prints item count,
processed count, and pending count. Add `--verbose` only when the caller needs
item ids and item names.

```sh
python moodtag.py tag --board '<eagle-folder>'
```

Read-only dry run. Calls the configured vision model and prints what would be
processed, but does not update Eagle. Useful for a quick smoke check.

```sh
python moodtag.py tag --board '<eagle-folder>' --write
```

Main write operation. Processes pending items and overwrites each processed
item's Eagle `tags` and `annotation` with Moodtag output.

```sh
python moodtag.py tag --board '<eagle-folder>' --write --force
```

Reprocesses already annotated items and overwrites existing Moodtag output. Use
this after prompt/contract changes.

```sh
python moodtag.py tag --board '<eagle-folder>' --write --limit N
```

Partial write for interruption/resume workflows. A later full `tag --write`
continues remaining pending items and skips already processed ones.

```sh
python moodtag.py reset --board '<eagle-folder>' --write
```

Destructive test/reset command. Clears both Eagle `annotation` and `tags` for
every item in the folder. Upper-layer agents should only call this for an
explicit reset task or a disposable test folder.

`<eagle-folder>` can be an Eagle folder id, exact folder name, or folder path.
If names are ambiguous, use the folder id.

## Current Annotation Output

Moodtag writes Eagle annotation as:

```text
Brief: ...

Elements: 元素1；元素2；元素3。

Use: ...

Key: ...

Camera: ...

LightColor: ...
```

Field intent:

- `Brief`: one factual visible-content sentence, answering "what is in the image".
- `Elements`: visible static objects for full-text search, not Eagle tags.
- `Use`: natural-language future use intent.
- `Key`: why the image is worth saving.
- `Camera`: shot size, angle, lens feel, composition.
- `LightColor`: lighting and color as one creative system.

Eagle top-level `tags` are controlled taxonomy tags plus mapped use-intent tags.
Callers should not parse or construct model JSON themselves.

## Validation Scripts

These are for maintainers, not normal upper-layer calls:

```sh
python scripts/e2e_moodtag.py
python scripts/e2e_live_batch.py --board '<eagle-folder>' --preflight-only
```

`scripts/e2e_live_batch.py --reset-first` is destructive because it clears the
target folder before running the live batch.

## Export Context For Other Agents

Use this read-only script when another agent needs the current folder as context:

```sh
python scripts/export_moodboard_context.py --board '<eagle-folder>' [--output context.md]
```

It extracts the current Eagle folder into compact Markdown. It does not call the
model and does not write to Eagle.

Caller-facing inputs:

- `--board` required: Eagle folder id, name, or path.
- `--output` optional: write Markdown to a file; stdout if omitted.
- `--include-pending` optional: include items without complete Moodtag
  annotation; default should mark or skip pending items clearly.

Output shape:

```md
# Moodboard Context: <folder path>

Items: <n>

## 1. <item name>
ID: <eagle id>
Tags: tag1, tag2, tag3
Brief: ...
Elements: ...
Use: ...
Key: ...
Camera: ...
LightColor: ...
```

Acceptance criteria:

- Read-only: no model requests, no Eagle update calls.
- Includes Eagle tags plus the six Moodtag annotation fields.
- Stable item order matches Eagle list order.
- Concise enough to paste into another agent as context.

`moodtag.py brief` still exists as an internal lightweight summary command, but
upper-layer agents should prefer `scripts/export_moodboard_context.py` because it
exports full annotation plus tags.
