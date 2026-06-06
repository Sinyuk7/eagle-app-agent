# eagle-app-agent

`eagle-app-agent` provides the `moodtag` CLI, a local tool for tagging Eagle
moodboard folders.

The workflow is folder-first:

1. Create a folder in Eagle.
2. Drag moodboard images into that folder.
3. Run `moodtag` against the Eagle folder.
4. Review the dry-run output.
5. Add `--write` only when you want to overwrite Eagle metadata.

`moodtag` does not create staging image folders, sidecar caches, or default
report files. It talks to the local Eagle desktop Web API and to an
OpenAI-compatible vision API.

## Install

Install the CLI from this checkout:

```sh
uv tool install --editable /Users/sinyuk/Documents/github/eagle-app-agent
```

Confirm that the command is visible in your shell:

```sh
moodtag --help
```

## Configure

Store non-secret defaults with `moodtag config`:

```sh
moodtag config set --base-url https://hk.n1n.ai/v1 \
  --fallback-base-url https://api.n1n.ai/v1 \
  --model Qwen3.5-122B-A10B
```

Keep API keys in the environment or in a local `.env` file:

```sh
export MOODTAG_API_KEY=...
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

## Common Usage

Check a folder before doing any model or write work:

```sh
moodtag status --board '<eagle-folder>'
```

Run a read-only analysis:

```sh
moodtag tag --board '<eagle-folder>'
```

Write tags and annotation back to Eagle:

```sh
MOODTAG_API_KEY=... moodtag tag --board '<eagle-folder>' --write
```

Process only a small batch:

```sh
moodtag tag --board '<eagle-folder>' --write --limit 5
```

Export processed folder context as Markdown:

```sh
moodtag export-context --board '<eagle-folder>' --output context.md
```

Build a brief from existing Eagle metadata:

```sh
moodtag brief --board '<eagle-folder>'
```

Clear Moodtag-owned annotations and tags:

```sh
moodtag reset --board '<eagle-folder>' --write
```

`<eagle-folder>` can be an Eagle folder id, exact folder name, or folder path.
If a name is ambiguous, use the Eagle folder id.

## Write Behavior

`tag` is a dry run unless `--write` is passed.

`tag --write` overwrites each processed item's Eagle `tags` and `annotation`
with Moodtag output. It does not merge with existing Eagle metadata.

`tag --write --force` reprocesses items that already have Moodtag output. Use it
only when you intentionally want a full overwrite.

`reset --write` clears both annotation and tags for the target folder.

Generated annotation is written as a fixed field block:

```text
Brief: ...

Elements: ...

Use: ...

Key: ...

Camera: ...

LightColor: ...
```

`tags` and `use_intents` from the model response are written only as Eagle tags,
never inside annotation text.

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `MOODTAG_EAGLE_API` | `http://localhost:41595` | Eagle desktop Web API URL. |
| `MOODTAG_BASE_URL` | `https://hk.n1n.ai/v1` | OpenAI-compatible vision API base URL. |
| `MOODTAG_FALLBACK_BASE_URL` | `https://api.n1n.ai/v1` | Optional fallback base URL for retryable provider failures. |
| `MOODTAG_MODEL` | `Qwen3.5-122B-A10B` | Vision/chat model name. |
| `MOODTAG_API_KEY` | empty | Vision API key. Required unless `--mock-vl` is used. |
| `VL_API_KEY` | empty | Backward-compatible fallback API key. |
| `MOODTAG_TAXONOMY` | bundled default | Optional custom tag taxonomy JSON file. |
| `MOODTAG_IMAGE_EDGE` | `1024` | Preview image long edge sent to the model. |
| `MOODTAG_MAX_TAGS` | `15` | Maximum Eagle tags written per item. |
| `MOODTAG_RETRIES` | `2` | Retry count for model calls. |
| `MOODTAG_TEMPERATURE` | `0.6` | Model temperature. |
| `MOODTAG_TOP_P` | `0.85` | Model top-p. |
| `MOODTAG_MAX_TOKENS` | `1028` | Max output tokens. |
| `MOODTAG_NO_RESPONSE_FORMAT` | `false` | `false` sends JSON Mode. Set `true` only for providers that reject JSON Mode. |

Useful single-run flags include `--eagle-api`, `--base-url`,
`--fallback-base-url`, `--model`, `--taxonomy`, `--image-edge`, `--max-tags`,
`--limit`, `--retries`, `--temperature`, `--top-p`, `--max-tokens`,
`--response-format`, and `--no-response-format`.

## More Documentation

- `HANDOFF.md`: strict public CLI contract for external agents or upper-layer
  modules.
- `CONTRIBUTING.md`: local development, tests, and E2E checks for maintainers.
