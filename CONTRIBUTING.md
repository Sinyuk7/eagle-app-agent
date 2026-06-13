# Contributing

This document is for maintainers and contributors working on
`eagle-app-agent`. The user-facing CLI guide is `README.md`.

The package name is `eagle-app-agent`; the installed command is `moodtag`.

## Project Layout

| Path | Purpose |
|---|---|
| `moodtag/` | CLI entry point, Eagle API integration, config handling, command behavior. |
| `moodtag_core/` | Shared prompt, response, annotation, provider, taxonomy, and contract logic. |
| `moodtag_core/resources/` | Bundled prompts and default taxonomy. |
| `moodboard/` | `moodboard` CLI entry point. |
| `moodboard_core/` | Moodboard HTML generation, validation, and bundled templates. |
| `scripts/` | Real Eagle E2E and support scripts. |
| `tests/` | Unit tests with fake Eagle and mocked model behavior. |
| `.env.example` | Local environment template. |

## Development Setup

Create a local virtual environment, install the project in editable mode, and
install development tools:

```sh
uv venv .venv --python /Users/sinyuk/.local/share/mise/installs/python/3.14.5/bin/python3
uv sync --dev
```

If that exact Python path is not available, use any Python `>=3.11`.

For a user-level editable CLI install from this checkout:

```sh
uv tool install --editable .
```

Confirm that the command is visible in the shell:

```sh
moodtag --help
```

Keep secrets out of committed files, shell history, and skill or agent
instructions. `moodtag config` stores only non-secret defaults. Use exported
environment variables or a local ignored `.env` for API keys.

## Runtime Configuration

Store non-secret defaults with `moodtag config`:

```sh
moodtag config set --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --fallback-base-url https://api.n1n.ai/v1 \
  --model qwen3.5-122b-a10b \
  --fallback-model qwen3.5-122b-a10b
```

Keep API keys in the environment or in a local `.env` file:

```sh
export DASHSCOPE_API_KEY=...
export MOODTAG_API_KEY=... # optional relay fallback
```

`moodtag` loads `.env` from the current working directory without overriding
variables that are already exported in the shell. Use `.env.example` as the
template for local values.

Show the effective saved defaults:

```sh
moodtag config show
```

Configuration precedence is:

1. CLI flags
2. Environment variables and current-directory `.env`
3. User config
4. Built-in defaults

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `MOODTAG_EAGLE_API` | `http://localhost:41595` | Eagle desktop Web API URL. |
| `MOODTAG_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Primary OpenAI-compatible vision API base URL. |
| `MOODTAG_FALLBACK_BASE_URL` | `https://api.n1n.ai/v1` | Optional relay fallback base URL for retryable provider failures. |
| `MOODTAG_MODEL` | `qwen3.5-122b-a10b` | Primary vision/chat model name. |
| `MOODTAG_FALLBACK_MODEL` | `qwen3.5-122b-a10b` | Optional relay fallback model name. |
| `DASHSCOPE_API_KEY` | empty | Primary Alibaba Cloud DashScope API key. |
| `MOODTAG_API_KEY` | empty | Optional relay fallback API key. |
| `VL_API_KEY` | empty | Backward-compatible fallback API key. |
| `MOODTAG_TAXONOMY` | bundled default | Optional custom tag taxonomy JSON file. |
| `MOODTAG_IMAGE_EDGE` | `768` | Preview image long edge sent to the model. |
| `MOODTAG_CONCURRENCY` | `4` | Number of image analysis requests to run in parallel. |
| `MOODTAG_MAX_TAGS` | `15` | Maximum Eagle tags written per item. |
| `MOODTAG_RETRIES` | `2` | Retry count for model calls. |
| `MOODTAG_TEMPERATURE` | `0.6` | Model temperature. |
| `MOODTAG_TOP_P` | `0.85` | Model top-p. |
| `MOODTAG_MAX_TOKENS` | `1028` | Max output tokens. Values below 1028 are rejected. |
| `MOODTAG_NO_RESPONSE_FORMAT` | `false` | `false` sends JSON Mode. Set `true` only for providers that reject JSON Mode. |

Useful single-run flags include `--eagle-api`, `--base-url`,
`--fallback-base-url`, `--model`, `--taxonomy`, `--image-edge`, `--concurrency`,
`--max-tags`, `--limit`, `--retries`, `--temperature`, `--top-p`, `--max-tokens`,
`--response-format`, and `--no-response-format`.

## Provider Guidance

Maintainers should prefer Qwen3.5-class vision-capable models, or stronger
models, for the configured Moodtag provider chain. The current recommended
default for both primary and fallback routes is:

```text
qwen3.5-122b-a10b
```

The primary provider uses `DASHSCOPE_API_KEY`. On network errors, HTTP 5xx,
HTTP 429, or recognizable quota/billing throttling failures, `moodtag` falls
back to `MOODTAG_FALLBACK_BASE_URL` with `MOODTAG_API_KEY`/`VL_API_KEY`. After a
primary fallback-class failure, the primary provider is skipped for 1800 seconds
using a local cache entry under the user cache directory.

Avoid using speed-first small/flash models such as `qwen3-vl-flash` as the
default write-path model unless a maintainer has revalidated them against real
Eagle folders. In live testing, `qwen3-vl-flash` could return malformed or
unfinished JSON despite JSON mode, which prevents safe tag/annotation writes.
It may still be useful for explicit experiments, dry runs, or cost-sensitive
manual testing.

## Maintainer Commands

Build a brief from existing Eagle metadata:

```sh
moodtag brief --board '<folder-id-or-name>'
```

Clear Moodtag-owned annotations and tags:

```sh
moodtag reset --board '<folder-id-or-name>' --write
```

Use `reset --write` only against disposable folders or when clearing all tags
and annotations is intentional.

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
- Python bytecode compilation for `moodtag`, `moodtag_core`, `moodboard`,
  `moodboard_core`, `scripts`, and `tests`

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

## Publishing

The preferred user install path is PyPI:

```sh
uv tool install eagle-app-agent
```

Source installs are only for pre-release testing or development:

```sh
uv tool install git+https://github.com/Sinyuk7/eagle-app-agent.git
uv tool install --editable .
```

The repository is configured for GitHub Actions publishing through PyPI Trusted
Publishing. Set up the PyPI project `eagle-app-agent`, add a trusted publisher
for this repository's `Publish` workflow, and bind it to the `pypi`
environment.

Release steps:

1. Update `version` in `pyproject.toml`.
2. Run `scripts/release_check.sh`.
3. Commit the release changes.
4. Create and push a matching tag, for example `v0.1.2`.
5. Let the `Publish` workflow build, validate, smoke test, and run
   `uv publish --trusted-publishing always`.

Use TestPyPI first if changing the packaging or trusted-publishing setup.

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

The E2E suite uses the real local Eagle Web API and a local OpenAI-compatible
model stub. It imports temporary images, exercises the CLI, verifies Eagle
metadata, and moves test items to trash during cleanup.

Prefer creating an Eagle folder named `__moodtag_e2e__` first, or pass an
explicit board:

```sh
uv run python scripts/e2e_moodtag.py
uv run python scripts/e2e_moodtag.py --board '__moodtag_e2e__'
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
MOODTAG_API_KEY=... uv run python scripts/e2e_live_batch.py --board '<folder-id-or-name>'
```

The default provider contract is:

- model: `qwen3.5-122b-a10b`
- primary base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- fallback base URL: `https://api.n1n.ai/v1`
- image part before text part
- `temperature=0.6`
- `top_p=0.85`
- `max_tokens=1028`
- JSON response format unless `--no-response-format` is passed

## Implementation Notes

`<eagle-folder>` can be an Eagle folder id, exact folder name, or folder path.
If a name is ambiguous, use the Eagle folder id. For user-facing workflows,
prefer asking users to copy the Eagle folder link and pass the `id=` value from
that link.

`tag` is a dry run unless `--write` is passed.

`tag --write` overwrites each processed item's Eagle `tags` and `annotation`.
It does not merge with existing metadata. Tests and manual checks should use
disposable Eagle folders unless the overwrite is intentional.

`tag --write --force` reprocesses items that already have Moodtag output. Use it
only when intentionally doing a full overwrite.

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
