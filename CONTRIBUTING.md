# Contributing

This document is for maintainers and contributors working on
`eagle-app-agent`. The user-facing CLI guide is `README.md`.

The package name is `eagle-app-agent`; the installed command is `moodtag`.

## Project Layout

| Path | Purpose |
|---|---|
| `moodtag/` | CLI entry point, Eagle API integration, config handling, command behavior. |
| `moodtag_core/` | Shared prompt, response, annotation, provider, taxonomy, and contract logic. |
| `moodtag_core/resources/` | Bundled prompts and profile taxonomies. |
| `scripts/` | Real Eagle E2E and support scripts. |
| `tests/` | Unit tests with fake Eagle and mocked model behavior. |
| `.env.example` | Local environment template. |

## Build

新发布产物标准构建命令：

```sh
uv build --no-sources
```

产物写入 `dist/`：

- `dist/eagle_app_agent-0.1.5-py3-none-any.whl`
- `dist/eagle_app_agent-0.1.5.tar.gz`

完整发布前检查脚本：

```sh
scripts/release_check.sh
```

它会清理旧产物、构建 wheel/sdist、运行 `twine check` 和 wheel CLI smoke。当前快速本地构建也可用 `uv build`。

---

macOS 安装包由 [build_installer.sh](/Users/sinyuk/Documents/github/eagle-app-agent/packaging/macos/build_installer.sh) 构建：

```sh
OUTPUT_DIR="$PWD/dist/macos" packaging/macos/build_installer.sh
```

流程：

1. PyInstaller 将 `moodtag` 冻结为 arm64 单文件可执行程序。
2. `pkgbuild` 打成 `.pkg`，安装到：
   - `/usr/local/libexec/moodtag/moodtag`
   - `/usr/local/bin/moodtag` 软链接
3. `hdiutil` 将 `.pkg` 和 README 打成 `.dmg`。

产物：

```text
dist/macos/Moodtag-0.1.5-macos-arm64.pkg
dist/macos/Moodtag-0.1.5-macos-arm64.dmg
```

完整发布检查可运行：

```sh
scripts/release_check.sh
```

在 Apple Silicon macOS 上，它会自动调用 installer 构建和 smoke check。

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

End-user happy path is now `moodtag <board-url-or-id>`. Maintainers should keep
that guided flow short: resolve board, show summary, confirm, then write.

Configure the catalog-backed model service with `moodtag config model`:

```sh
moodtag config model
```

Keep API keys in the environment or in a local `.env` file:

```sh
export MOODTAG_API_KEY=...
```

`moodtag` loads `~/.config/moodtag/.env` first, then the current working
directory `.env`, without overriding variables that are already exported in the
shell. Use `.env.example` as the template for local values.

Show the effective saved defaults:

```sh
moodtag config
```

Configuration precedence is inherited shell environment > user
`~/.config/moodtag/.env` > current-directory `.env` > JSON config. The model
tuple has no built-in endpoint/model default. `moodtag config show` prints the
derived protocol, endpoint, model, `env_file` path, and key readiness without
printing secrets. Use `moodtag config model` for interactive setup.

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `MOODTAG_EAGLE_API` | `http://localhost:41595` | Eagle desktop Web API URL. |
| `MOODTAG_API_KEY` | empty | Single model API key. |
| `MOODTAG_IMAGE_EDGE` | `768` | Preview image long edge sent to the model. |
| `MOODTAG_CONCURRENCY` | `4` | Number of image analysis requests to run in parallel. |
| `MOODTAG_MAX_TAGS` | `15` | Maximum Eagle tags written per item. |
| `MOODTAG_RETRIES` | `2` | Retry count for model calls. |
| `MOODTAG_TEMPERATURE` | `0.6` | Model temperature. |
| `MOODTAG_TOP_P` | `0.85` | Model top-p. |
| `MOODTAG_MAX_TOKENS` | `1028` | Max output tokens. Values below 1028 are rejected. |
| `MOODTAG_LOG_DIR` | `~/.cache/moodtag/runs` | JSONL run log directory for `moodtag tag`. |
| `MOODTAG_LOG_KEEP` | `50` | Number of newest `moodtag-*.jsonl` run logs to keep. |
| `MOODTAG_NO_RESPONSE_FORMAT` | `false` | `false` sends JSON Mode. Set `true` only for providers that reject JSON Mode. |

Useful single-run flags include `--eagle-api`, `--profile`, `--image-edge`, `--concurrency`,
`--max-tags`, `--limit`, `--retries`, `--temperature`, `--top-p`, `--max-tokens`,
`--response-format`, and `--no-response-format`.

`--profile` selects one bundled prompt contract and its matching bundled taxonomy.
`default` uses the general-purpose taxonomy; `editorial` uses the commercial portrait
taxonomy. Taxonomy is not a runtime override because prompt contract and allowed tags
must remain aligned.

## Model Endpoint Guidance

Maintainers should prefer Qwen3.5-class vision-capable models, or stronger
models for the configured Moodtag endpoint. There is no built-in model default;
choose a vision-capable model supported by your service.

```text
your-vision-model
```

`moodtag tag` sends every request to one configured endpoint. Retryable failures
retry that same endpoint; there is no endpoint routing or cooldown state. Runtime
telemetry records protocol, endpoint host/path, model, attempts, timings, and
source strategy, never credentials or request payloads.

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
- on Apple Silicon macOS, builds `Moodtag-<version>-macos-arm64.pkg` and `.dmg`,
  then starts the command from the package payload without a Python install

Generated `build/`, `dist/`, and `*.egg-info/` outputs are ignored by git and
must not be committed.

## Publishing

The release workflow publishes wheel + sdist and builds macOS installer artifacts
on an Apple Silicon runner, then attaches the verified `.pkg` and `.dmg` to the
matching GitHub Release:

```sh
uv tool install eagle-app-agent
```

`packaging/macos/build_installer.sh` freezes `moodtag` with PyInstaller, installs
the binary at `/usr/local/libexec/moodtag/moodtag`, and exposes it through
`/usr/local/bin/moodtag`. The workflow's installer smoke check installs the `.pkg`
on a clean runner, then verifies `moodtag --help` using a `PATH` that has no
developer-tool directory.

The generated `.pkg` and `.dmg` are arm64 artifacts for M1-M5 Macs. An unsigned
installer can still be opened after the user approves it in macOS Privacy &
Security, but signing and notarization remove that extra Gatekeeper step. Treat
them as release-quality improvements, not install prerequisites.

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
moodtag tag --board '<folder-id-or-name>' --mock-model --limit 1
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
MOODTAG_API_KEY=... uv run python scripts/e2e_live_batch.py \
  --board '<folder-id-or-name>' \
  --protocol responses \
  --base-url https://model-service.example/v1 \
  --model vision-model
```

The model contract is:

- one configured protocol: `chat` or `responses`
- one configured base URL and model
- image plus prompt content in protocol-specific wire shape
- `temperature=0.6`
- `top_p=0.85`
- `max_tokens=1028` (`max_output_tokens` for Responses)
- JSON response format unless `--no-response-format` is passed

### Fixed protocol matrix

`scripts/e2e_protocol_matrix.py` exercises both deployed protocol shapes against
the disposable Eagle folder `MSHGWFME8L6SJ`:

- Responses: `gpt-5.6-luna` through `https://sub2.de5.net/v1/responses`
- Chat Completions: `qwen3.5-122b-a10b` through `https://llm-api.net/v1/chat/completions`

API keys are runtime-only. Do not add them to source files, command arguments,
reports, or committed `.env` files. Set the two matrix-specific variables in the
current shell, then run:

```sh
export MOODTAG_E2E_RESPONSES_API_KEY='...'
export MOODTAG_E2E_CHAT_API_KEY='...'

uv run python scripts/e2e_protocol_matrix.py --plan
uv run python scripts/e2e_protocol_matrix.py \
  --confirm-reset MSHGWFME8L6SJ
```

This is destructive. Before each profile, the matrix runs `reset --write` and
clears all Eagle tags and annotations in the confirmed folder. With the current
five-item test folder, each profile writes two items, resumes the remaining
three, then repeats the full run and asserts all five items are skipped. The
second Chat profile remains written after the matrix completes.

Each child report records the public protocol, normalized endpoint, model,
state timeline, and run counts. The matrix rejects any report containing either
configured credential value.

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

Generated annotations intentionally do not use a wrapper marker. Every profile
writes these fixed natural-language fields:

```text
Brief: ...

Elements: ...

Use: ...

Key: ...

Camera: ...

LightColor: ...
```

The `editorial` profile can additionally write evidence metadata when present:
`VisibleText`, `BrandEvidence`, `ProductCategories`, and
`CommercialFormatConfidence`. The default profile keeps the six-field contract.
Existing six-field annotations remain valid.

`tags` and `use_intents` are written only as Eagle tags, not into annotation
text. `Elements` is a semicolon-separated visible-object field for full-text
search, not an Eagle tag list.
