# eagle-app-agent

`moodtag` is a local CLI for Eagle moodboard tagging.

The workflow is folder-first:

1. Create a folder in Eagle.
2. Drag moodboard images into that folder.
3. Run `moodtag` against the Eagle folder.
4. Overwrite Eagle tags and annotation with controlled tags plus natural-language fields.
5. Generate a brief only when needed.

The tool does not create staging image folders, sidecar caches, or default report files.

## Setup

```sh
uv venv .venv --python /Users/sinyuk/.local/share/mise/installs/python/3.14.5/bin/python3
uv pip install -r requirements.txt --python .venv/bin/python
cp .env.example .env
```

Edit `.env` with the local Eagle API address and model credentials. `moodtag`
loads `.env` automatically without overriding variables already exported in the
shell.

Key settings:

| Variable | Default | Purpose |
|---|---|---|
| `MOODTAG_EAGLE_API` | `http://localhost:41595` | Eagle desktop Web API URL. |
| `MOODTAG_BASE_URL` | `https://hk.n1n.ai/v1` | OpenAI-compatible vision API base URL. |
| `MOODTAG_FALLBACK_BASE_URL` | `https://api.n1n.ai/v1` | Optional fallback base URL for retryable provider failures. |
| `MOODTAG_MODEL` | `Qwen3.5-122B-A10B` | Vision/chat model name. |
| `MOODTAG_API_KEY` | empty | Vision API key. Required unless `--mock-vl` is used. |
| `VL_API_KEY` | empty | Backward-compatible fallback API key. |
| `MOODTAG_TAXONOMY` | `taxonomy/default.json` | Tag taxonomy JSON file. |
| `MOODTAG_IMAGE_EDGE` | `1024` | Preview image long edge sent to the model. |
| `MOODTAG_TEMPERATURE` | `0.6` | Model temperature. |
| `MOODTAG_TOP_P` | `0.85` | Model top-p. |
| `MOODTAG_MAX_TOKENS` | `1028` | Max output tokens. |
| `MOODTAG_NO_RESPONSE_FORMAT` | `false` | `false` sends JSON Mode: `response_format={"type":"json_object"}`. Set `true` only for providers that reject JSON Mode. |

```sh
MOODTAG_API_KEY=...
MOODTAG_MODEL=Qwen3.5-122B-A10B
```

CLI flags such as `--eagle-api`, `--base-url`, `--fallback-base-url`, `--model`,
`--taxonomy`, `--image-edge`, `--max-tags`, `--retries`, `--temperature`,
`--top-p`, and `--max-tokens` override the environment defaults for a single
run. JSON Mode is on by default for the reference Qwen provider contract; pass
`--no-response-format` only when testing a provider that does not support it.

## Usage

```sh
.venv/bin/python moodtag.py status --board '明日方舟 - 小红书'
.venv/bin/python moodtag.py tag --board '明日方舟 - 小红书' --mock-vl
.venv/bin/python moodtag.py tag --board '明日方舟 - 小红书' --write
.venv/bin/python moodtag.py brief --board '明日方舟 - 小红书'
.venv/bin/python moodtag.py reset --board '明日方舟 - 小红书'
```

`tag` is a dry run unless `--write` is passed.
`tag --write` overwrites each processed item's Eagle tags and annotation with
the model contract output. It does not merge existing Eagle metadata.
`reset --write` clears both annotation and tags for the target folder.

Generated annotations do not use a wrapper marker. They are rendered as a fixed
natural-language field block:

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
`Brief` is a one-sentence visible-content description. `Elements` is a
semicolon-separated list of visible static objects for full-text search, not an
Eagle tag list.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests
```

The committed tests use a fake Eagle client and mock vision model. They do not
write to a real Eagle library and do not call a real model API.

Read-only real smoke checks:

```sh
.venv/bin/python moodtag.py status --board '<folder-id-or-name>'
.venv/bin/python moodtag.py tag --board '<folder-id-or-name>' --mock-vl --limit 1
.venv/bin/python moodtag.py tag --board '<folder-id-or-name>' --limit 1
```

The last command calls the configured vision API but is still a dry run. Only add
`--write` when using a disposable Eagle test folder or when the write is
intentional.

## Real E2E

The E2E suite uses the real local Eagle Web API. Prefer creating an Eagle folder
named `__moodtag_e2e__` first, or pass `--board '<folder-id-or-name>'`. The
suite imports temporary images, exercises the CLI, verifies Eagle metadata, and
moves test items to trash during cleanup.

The model side is a local OpenAI-compatible stub server by default. This keeps
the regression suite stable and avoids repeatedly calling the external model
gateway while still verifying the same `/v1/chat/completions` request shape.

```sh
.venv/bin/python scripts/e2e_moodtag.py
.venv/bin/python scripts/e2e_moodtag.py --board '__moodtag_e2e__'
```

Covered E2E cases:

- core write flow: import item, tag with `--write`, verify status/brief/reset
- core dry run: analyze without writing Eagle metadata
- boundary short-circuit: invalid args fail before Eagle/model access
- retry: one transient model failure succeeds after retry
- severe result guard: empty model output fails and does not write metadata

Reports are written to `e2e-results/` and are ignored by git.

For a real model plus real Eagle batch check, use a folder with 10-20 images.
The live batch script performs one preflight model call, writes a partial batch
to simulate interruption, resumes the remaining items, then runs the same batch
again to verify repeat execution skips already processed items.

```sh
MOODTAG_API_KEY=... .venv/bin/python scripts/e2e_live_batch.py --board '明日方舟 - 小红书'
```

The live script uses the same provider contract as the CLI: `Qwen3.5-122B-A10B`,
`https://hk.n1n.ai/v1` with `https://api.n1n.ai/v1` fallback, image part before
text part, `temperature=0.6`, `top_p=0.85`, `max_tokens=1028`, and JSON
response format unless `--no-response-format` is passed.
