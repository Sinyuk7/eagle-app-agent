## Context

The current model layer already shares image encoding, prompts, HTTP transport, retries, response normalization, and `MoodtagAnalysis`, but it models more than one endpoint slot and assumes Chat Completions. The confirmed product constraint is simpler: one active endpoint, one key in `.env`, and a user-selected protocol.

The existing configuration JSON is non-secret and already has a user-scoped path. The existing `.env` loader/writer can safely own `MOODTAG_API_KEY`. The main guided command already resolves a board before asking for write confirmation, so model setup can be inserted before the model probe without changing Eagle write safety.

The target boundary is intentionally clean for the next version: `VisionClient` owns one protocol-aware endpoint, and the CLI owns one non-secret JSON config plus one `MOODTAG_API_KEY` credential. No compatibility layer is required.

## Goals / Non-Goals

**Goals:**

- Represent exactly one active endpoint with `protocol`, `base_url`, `model`, and existing Eagle settings.
- Make a clean install incomplete rather than silently selecting a vendor endpoint or model.
- Support the OpenAI wire protocols `chat` and `responses` through separate request/response adapters.
- Keep prompts, image preparation, retries, logging, taxonomy reconciliation, and `MoodtagAnalysis` shared.
- Provide one smooth interactive setup path for first run and explicit reconfiguration.
- Keep the key only in `.env` as `MOODTAG_API_KEY`, with shell environment taking precedence.
- Make protocol-specific URL and payload construction testable without vendor detection.

**Non-Goals:**

- Endpoint lists, routing, cooldown persistence, key rotation, or endpoint health registries.
- Vendor-specific classes or hostname recognition for OpenAI, n1n, or any other service.
- OpenAI SDK dependency; use the existing standard-library HTTP boundary.
- OpenAI stateful conversations, tools, streaming, or Responses features beyond one image analysis request.

## Decisions

### 1. One active endpoint

Canonical JSON contains only `protocol`, `base_url`, `model`, and existing non-model settings such as `eagle_api`:

```json
{"protocol":"responses","base_url":"https://service.example/v1","model":"vision-model","eagle_api":"http://localhost:41595"}
```

`protocol` accepts only `chat` or `responses`. No endpoint or model default is applied. Operational model commands do not accept endpoint/key flags; `moodtag config set --protocol ... --base-url ... --model ...` is the non-interactive path. Non-secret `MOODTAG_PROTOCOL`, `MOODTAG_BASE_URL`, `MOODTAG_MODEL`, and `MOODTAG_EAGLE_API` environment values override JSON. Credential precedence is inherited shell environment > user `~/.config/moodtag/.env` > current-working-directory `.env`; `MOODTAG_API_KEY` is the only credential name.

`moodtag config set` validates supplied fields and updates them without inventing a second endpoint. `moodtag config setup` replaces the complete model tuple after confirmation.

Alternative rejected: an endpoint registry. It adds routing and state complexity that the single-endpoint product requirement explicitly rejects.

### 2. Protocol adapters behind one analysis contract

Introduce a small adapter boundary selected by `protocol`:

```text
ProviderConfig -> ChatCompletionsAdapter | ResponsesAdapter
             -> one endpoint, retried up to `retries + 1` attempts
             -> HTTP JSON response
             -> extracted text
             -> parse_analysis_response / normalize_analysis_json
             -> MoodtagAnalysis
```

The Chat adapter posts to `{base_url}/chat/completions` with `model`, `store: false`, `temperature`, `top_p`, `max_tokens`, a system message, and a user message containing text plus an `image_url` data URL. When JSON mode is enabled it sends `response_format: {"type":"json_object"}`; disabled mode omits it.

The Responses adapter posts to `{base_url}/responses` with `model`, `store: false`, `temperature`, `top_p`, `max_output_tokens`, and `input` items containing the system prompt and a user message whose content parts are `input_text` and `input_image` (`image_url` data URL). When JSON mode is enabled it sends `text.format: {"type":"json_object"}`; disabled mode omits that field. Fixtures must assert exact paths and body keys.

Alternative rejected: one payload builder with conditional keys. It would obscure materially different request and response shapes and make future protocol changes riskier.

### 3. Normalize Responses output centrally

The response layer will extract Chat text from `choices[0].message.content` (string or ordered text parts) and Responses text from every `output[*].content[*]` part whose type is `output_text`, preserving order and ignoring reasoning/non-text items. Refusal, malformed shape, or missing text becomes a typed `CoreError` before JSON parsing. No top-level shortcut may hide a malformed Responses output.

### 4. One credential variable

All setup and runtime key lookup use `MOODTAG_API_KEY`. `config show` reports only `set`/`unset`. API keys are never accepted as command-line options, serialized into config JSON, written to run logs, or included in exception text. Redaction must scrub the actual configured key regardless of prefix or format, not only `sk-*`. Existing shell values override `.env`; consequently `config auth` changes the persisted key but cannot override an inherited shell key in the same process.

### 5. Interactive setup is explicit and resumable

`moodtag <board>` checks model configuration only when a model call is needed. If setup is incomplete and stdin is a TTY, it asks for protocol (default `responses`), base URL, model, then a hidden API key prompt. It validates all values, displays a redacted summary, and asks for confirmation before writing config and `.env` (the credential file is owner-readable/writable only). Writes use temporary files plus replace and restore prior file contents on a second-file failure. Cancellation leaves existing files unchanged. Non-interactive execution reports the exact command needed instead of prompting. Non-model commands remain usable without endpoint setup.

`moodtag config setup` runs the same flow without touching Eagle. `moodtag config auth` changes only the `.env` key. After first-run setup, the guided board flow continues to its existing board summary and final write confirmation.

### 6. Stable endpoint URL normalization

Keep root/`/v1`/full endpoint normalization, but make it protocol-aware: Chat appends `/chat/completions`; Responses appends `/responses`. Accept only absolute `http`/`https` URLs without userinfo, query, or fragment; reject empty, malformed, or conflicting endpoint paths before Eagle access.

### 7. Retry and telemetry contract

Retries target the same endpoint and protocol only. Retry network errors, HTTP 429, and HTTP 5xx with existing backoff; do not retry 401/403 or validation/refusal errors. Run logs may record protocol, host/path, model, attempt count, status, source strategy, and timings (including existing per-item `timings_ms` and `source_strategy` telemetry), but must not record request headers, request bodies, image data URLs, or keys. Every record and user-facing error must scrub the actual key.

## Risks / Trade-offs

- [Configuration contract] Clean installs require explicit endpoint setup before model calls.
- [Endpoint compatibility] A user-selected service may not implement the selected protocol or optional JSON mode → surface the provider's HTTP error clearly; protocol selection remains user-controlled.
- [Responses output variation] Responses can include reasoning and non-text output items → extract only ordered `output_text` parts and fail clearly when none exist.
- [Secret leakage] New errors or logs could expose arbitrary key formats → redact the configured key value before recording exceptions and never log request headers.
- [Interactive interruption] Setup may be cancelled midway → collect values in memory and write only after final confirmation.

## Rollout Plan

1. Ship the one-endpoint config schema and protocol adapters together.
2. Require `moodtag config setup` (or equivalent environment values) before model commands.
3. Update guided flow, docs, examples, and tests to the clean contract.
4. Validate the full test suite before release; no provider/fallback migration path is shipped.

Rollback is a code rollback. Configuration is disposable next-version state and can be recreated with `moodtag config setup`.

## Open Questions

- Whether `moodtag config setup` should probe the endpoint immediately or defer validation to the first board image. Recommended: defer to the existing first-image probe so setup remains fast and does not send an unexpected request.
