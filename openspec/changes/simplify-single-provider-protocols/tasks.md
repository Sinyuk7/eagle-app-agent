## 1. Configuration Contract

- [ ] 1.1 Replace DashScope/primary/fallback constants with single-provider `protocol`, `base_url`, and `model` defaults and validation.
- [ ] 1.2 Update `moodtag/config.py` schema, serialization, precedence, and public status view to keep only non-secret single-provider fields.
- [ ] 1.3 Remove `DASHSCOPE_API_KEY`, `VL_API_KEY`, vendor URL detection, fallback fields, provider-state cooldown persistence, and provider-specific error messages.
- [ ] 1.4 Standardize runtime credential lookup on `MOODTAG_API_KEY` while preserving shell-over-user-`.env` precedence and secret redaction.

## 2. Protocol Adapters

- [ ] 2.1 Refactor the core provider boundary to carry one endpoint and explicit `chat` or `responses` protocol without primary/fallback endpoint construction.
- [ ] 2.2 Implement Chat Completions request construction for `/chat/completions`, including multimodal `messages`, image data URL, model settings, and supported JSON formatting.
- [ ] 2.3 Implement Responses request construction for `/responses`, including `input`, `input_text`, `input_image`, stateless request options, and Responses structured output formatting.
- [ ] 2.4 Extend response extraction for ordered Chat message content and Responses `output_text` parts, including clear refusal/missing-text errors before normalization.
- [ ] 2.5 Preserve shared prompt rendering, taxonomy reconciliation, retry behavior, attempt telemetry, and `MoodtagAnalysis` output across both adapters.

## 3. CLI Setup and Commands

- [ ] 3.1 Add `moodtag config setup` interactive flow with protocol selection, base URL, model, hidden key prompt, redacted summary, confirmation, cancellation safety, and atomic persistence.
- [ ] 3.2 Add `moodtag config auth` key-only setup using `MOODTAG_API_KEY` and avoid accepting secrets as command-line arguments.
- [ ] 3.3 Update `moodtag config set`, `config show`, parser defaults, and effective configuration validation for the single-provider schema.
- [ ] 3.4 Run guided setup before model probing when required, preserve the existing Eagle summary and final write confirmation, and provide actionable non-interactive errors.
- [ ] 3.5 Remove provider plan/fallback output and update run logs to identify only the configured endpoint and protocol without secrets.

## 4. Tests

- [ ] 4.1 Replace legacy DashScope/fallback configuration tests with single-provider config, precedence, validation, and secret-safety coverage.
- [ ] 4.2 Add local HTTP fixture tests for Chat request paths, multimodal payloads, JSON output, and normalized responses.
- [ ] 4.3 Add local HTTP fixture tests for Responses request paths, input image content, structured output settings, ordered output extraction, and refusal/missing-text errors.
- [ ] 4.4 Test first-run setup, cancellation, confirmation, `.env` persistence, `config auth`, and non-interactive setup errors.
- [ ] 4.5 Verify retry/error behavior, guided tagging safety, dry-run/write flows, and concurrency with one configured endpoint.

## 5. Documentation and Verification

- [ ] 5.1 Update README, `.env.example`, contributor docs, and live scripts to document one endpoint, `MOODTAG_API_KEY`, `chat`/`responses`, and setup commands.
- [ ] 5.2 Remove DashScope, fallback, and vendor-specific references from user-facing text and tests.
- [ ] 5.3 Run formatting/lint checks and the complete test suite; verify OpenSpec scenarios against the implemented behavior.
