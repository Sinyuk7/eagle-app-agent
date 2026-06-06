# Contributing

This document is for maintainers and contributors working on
`eagle-app-agent`. For normal CLI usage, start with `README.md`. For external
agents that must treat `moodtag` as a black-box command, use `HANDOFF.md`.

## Project Layout

| Path | Purpose |
|---|---|
| `moodtag/` | CLI entry point, Eagle API integration, config handling, command behavior. |
| `moodtag_core/` | Shared prompt, response, annotation, provider, taxonomy, and contract logic. |
| `moodtag_core/resources/` | Bundled prompts and default taxonomy. |
| `scripts/` | Real Eagle E2E and support scripts. |
| `tests/` | Unit tests with fake Eagle and mocked model behavior. |
| `.env.example` | Local environment template. |

The package name is `eagle-app-agent`; the installed command is `moodtag`.

## Development Setup

Create a local virtual environment, install the project in editable mode, and
install development tools:

```sh
uv venv .venv --python /Users/sinyuk/.local/share/mise/installs/python/3.14.5/bin/python3
uv sync --dev
```

If that exact Python path is not available, use any Python `>=3.11`.

For a user-level editable CLI install:

```sh
uv tool install --editable /Users/sinyuk/Documents/github/eagle-app-agent
```

Keep secrets out of committed files, shell history, and skill or agent
instructions. `moodtag config` stores only non-secret defaults. Use exported
environment variables or a local ignored `.env` for API keys.

## Local Hooks

Install the local git hooks:

```sh
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

The pre-commit hook runs fast local checks:

```sh
uv run pre-commit run --all-files
```

Covered checks:

- Ruff formatting
- Ruff lint with safe fixes
- Python bytecode compilation for `moodtag`, `moodtag_core`, `scripts`, and
  `tests`

The pre-push hook additionally runs the local release check:

```sh
uv run pre-commit run --hook-stage pre-push --all-files
```

## Release Check

Run the full local release gate before tagging or publishing:

```sh
scripts/release_check.sh
```

The release check:

- runs the committed unit tests
- removes stale `dist/` and `build/` outputs
- builds the source distribution and wheel with `uv build --no-sources`
- validates the distributions with `twine check`
- installs the built wheel in a temporary uv environment and verifies
  `moodtag --help`

Generated `build/`, `dist/`, and `*.egg-info/` outputs are ignored by git and
must not be committed.

## Unit Tests

Run the committed unit tests:

```sh
uv run python -m unittest discover -s tests
```

The unit tests use a fake Eagle client and mock vision behavior. They do not
write to a real Eagle library and do not call a real model API.

## Read-Only Smoke Checks

These commands are safe against a real Eagle library because they do not write
metadata:

```sh
moodtag status --board '<folder-id-or-name>'
moodtag tag --board '<folder-id-or-name>' --mock-vl --limit 1
MOODTAG_API_KEY=... moodtag tag --board '<folder-id-or-name>' --limit 1
```

The last command calls the configured vision API but remains a dry run. Add
`--write` only when using a disposable Eagle test folder or when the write is
intentional.

## Real Eagle E2E

The E2E suite uses the real local Eagle Web API and a local
OpenAI-compatible model stub. It imports temporary images, exercises the CLI,
verifies Eagle metadata, and moves test items to trash during cleanup.

Prefer creating an Eagle folder named `__moodtag_e2e__` first, or pass an
explicit board:

```sh
python scripts/e2e_moodtag.py
python scripts/e2e_moodtag.py --board '__moodtag_e2e__'
```

Covered E2E cases:

- core write flow: import item, tag with `--write`, verify status/brief/reset
- core dry run: analyze without writing Eagle metadata
- force overwrite
- boundary short-circuit: invalid args fail before Eagle/model access
- retry: one transient model failure succeeds after retry
- severe result guard: empty model output fails and does not write metadata

Reports are written to `e2e-results/` and are ignored by git.

## Live Batch E2E

For a real model plus real Eagle batch check, use a folder with 10-20 images.
The live batch script performs one preflight model call, writes a partial batch
to simulate interruption, resumes remaining items, then runs the batch again to
verify repeat execution skips already processed items.

```sh
MOODTAG_API_KEY=... python scripts/e2e_live_batch.py --board '<folder-id-or-name>'
```

The default provider contract is:

- model: `Qwen3.5-122B-A10B`
- primary base URL: `https://hk.n1n.ai/v1`
- fallback base URL: `https://api.n1n.ai/v1`
- image part before text part
- `temperature=0.6`
- `top_p=0.85`
- `max_tokens=1028`
- JSON response format unless `--no-response-format` is passed

## Implementation Notes

`tag --write` overwrites each processed item's Eagle `tags` and `annotation`.
It does not merge with existing metadata. Tests and manual checks should use
disposable Eagle folders unless the overwrite is intentional.

Generated annotations intentionally do not use a wrapper marker. They are fixed
natural-language fields:

```text
Brief: ...

Elements: ...

Use: ...

Key: ...

Camera: ...

LightColor: ...
```

`tags` and `use_intents` are written only as Eagle tags, not into annotation
text. `Elements` is a semicolon-separated visible-object field for full-text
search, not an Eagle tag list.
