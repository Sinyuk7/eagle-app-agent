## Context

The current provider layer already shares image encoding, prompts, HTTP transport, retries, response normalization, and `MoodtagAnalysis`, but it models two vendor-specific slots (`primary` and `fallback`) and assumes Chat Completions. CLI setup also infers credential names from URL hosts. The confirmed product constraint is simpler: one active endpoint, one key in `.env`, and a user-selected protocol.

The existing configuration JSON is non-secret and already has a user-scoped path. The existing `.env` loader/writer can safely own `MOODTAG_API_KEY`. The main guided command already resolves a board before asking for write confirmation, so model setup can be inserted before the model probe without changing Eagle write safety.

## Goals / Non-Goals

**Goals:**

- Represent exactly one active endpoint with `protocol`, `base_url`, `model`, and existing Eagle settings.
- Support the OpenAI wire protocols `chat` and `responses` through separate request/response adapters.
- Keep prompts, image preparation, retries, logging, taxonomy reconciliation, and `MoodtagAnalysis` shared.
- Provide one smooth interactive setup path for first run and explicit reconfiguration.
- Keep the key only in `.env` as `MOODTAG_API_KEY`, with shell environment taking precedence.
- Make protocol-specific URL and payload construction testable without vendor detection.

**Non-Goals:**

- Provider lists, fallback routing, cooldown persistence, key rotation, or provider health registries.
- Vendor-specific classes or hostname recognition for OpenAI, n1n, or any other service.
- OpenAI SDK dependency; use the existing standard-library HTTP boundary.
- OpenAI stateful conversations, tools, streaming, or Responses features beyond one image analysis request.

## Decisions

### 1. One active endpoint, not provider slots

Replace `base_url`/`fallback_base_url` and corresponding model fields with `protocol`, `base_url`, and `model`. The configured endpoint is the complete runtime model configuration. `moodtag config set` updates only supplied fields; `moodtag config setup` replaces the complete model configuration after confirmation.

Alternative rejected: a `providers[]` registry or retaining fallback slots. Both add routing and state complexity that the single-provider product requirement explicitly rejects.

### 2. Protocol adapters behind one analysis contract

Introduce a small adapter boundary selected by `protocol`:

```text
ProviderConfig -> ChatCompletionsAdapter | ResponsesAdapter
             -> HTTP JSON response
             -> extracted text
             -> parse_analysis_response / normalize_analysis_json
             -> MoodtagAnalysis
```

The Chat adapter posts to `{base_url}/chat/completions` with `messages`, `image_url`, and `response_format` when enabled. The Responses adapter posts to `{base_url}/responses` with `input`, `input_text`, `input_image`, and Responses `text.format` JSON mode when enabled. Both adapters send `store: false` for a stateless tagging request and both return the same internal text/JSON contract.

Alternative rejected: one payload builder with conditional keys. It would obscure materially different request and response shapes and make future protocol changes riskier.

### 3. Normalize Responses output centrally

The response layer will extract Chat text from `choices[0].message.content` and Responses text from all `output` message content parts of type `output_text`, preserving order. Refusal or missing text becomes a typed core error. JSON parsing and taxonomy validation remain after extraction and are shared.

### 4. One credential variable

All setup and runtime key lookup use `MOODTAG_API_KEY`. `config show` reports only `set`/`unset`. API keys are never accepted as command-line options, serialized into config JSON, written to run logs, or included in exception text. Existing shell values override `.env`, matching current behavior.

### 5. Interactive setup is explicit and resumable

`moodtag <board>` checks model configuration only when a model call is needed. If setup is incomplete and stdin is a TTY, it asks for protocol (default `responses`), base URL, model, then a hidden API key prompt. It displays a redacted summary and asks for confirmation before writing config and `.env`. Cancellation leaves existing files unchanged. Non-interactive execution reports the exact command needed instead of prompting.

`moodtag config setup` runs the same flow without touching Eagle. `moodtag config auth` changes only the `.env` key. After first-run setup, the guided board flow continues to its existing board summary and final write confirmation.

### 6. Stable endpoint URL normalization

Keep root/`/v1`/full endpoint normalization, but make it protocol-aware: Chat appends `/chat/completions`; Responses appends `/responses`. Reject empty or malformed URLs early. Do not infer provider identity from hostnames.

## Risks / Trade-offs

- [Breaking configuration change] Existing DashScope/primary/fallback config will not be interpreted → provide explicit setup instructions and cover clean-config behavior in tests.
- [Endpoint compatibility] A user-selected service may not implement the selected protocol or optional JSON mode → surface the provider's HTTP error clearly; protocol selection remains user-controlled.
- [Responses output variation] Responses can include reasoning and non-text output items → extract only ordered `output_text` parts and fail clearly when none exist.
- [Secret leakage] New errors or logs could expose arbitrary key formats → redact the configured key value before recording exceptions and never log request headers.
- [Interactive interruption] Setup may be cancelled midway → collect values in memory and write only after final confirmation.

## Migration Plan

1. Replace defaults and config schema; remove DashScope/fallback fields and host-specific key lookup.
2. Add protocol adapters and response extraction tests using local HTTP fixtures.
3. Add setup/auth commands and update guided flow, docs, examples, and tests.
4. Run the full test suite and release notes should call out the breaking config/key migration.

Rollback is a code rollback. User config rollback is manual: restore a prior config JSON and provider-specific environment variable only if running an older release.

## Open Questions

- Whether `moodtag config setup` should probe the endpoint immediately or defer validation to the first board image. Recommended: defer to the existing first-image probe so setup remains fast and does not send an unexpected request.
