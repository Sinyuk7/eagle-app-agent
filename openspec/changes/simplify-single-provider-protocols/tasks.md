## 1. Configuration Contract

- [x] 1.1 Define single-provider `protocol`, `base_url`, and `model` schema; clean config has no vendor endpoint/model default.
- [x] 1.2 Update `moodtag/config.py` schema, serialization, precedence, and public status view to keep only non-secret single-provider fields.
- [x] 1.3 Limit runtime to `MOODTAG_API_KEY`, protocol-neutral URL handling, and protocol-neutral errors.
- [x] 1.4 Standardize runtime credential lookup on `MOODTAG_API_KEY` while preserving shell-over-user-`.env` precedence and secret redaction.
- [x] 1.5 Keep configuration schema and credential lookup limited to the new single-endpoint fields and `MOODTAG_API_KEY`.
- [x] 1.6 Validate absolute `http`/`https` URLs, reject userinfo/query/fragment, and normalize root/`/v1`/full endpoint forms per protocol.
- [x] 1.7 Define precedence as shell > user `.env` > CWD `.env` > JSON for supported environment overrides; set `.env` owner-only permissions.

## 2. Protocol Adapters

- [x] 2.1 Refactor the core model boundary to carry one endpoint and explicit `chat` or `responses` protocol.
- [x] 2.2 Implement Chat Completions request construction for `/chat/completions`, including multimodal `messages`, image data URL, model settings, and supported JSON formatting.
- [x] 2.3 Implement Responses request construction for `/responses`, including `input`, `input_text`, `input_image`, stateless request options, and Responses structured output formatting.
- [x] 2.4 Extend response extraction for ordered Chat message content and Responses `output_text` parts, including clear refusal/missing-text errors before normalization.
- [x] 2.4a Replace vendor-specific `VL` error wording with protocol-neutral model response errors.
- [x] 2.5 Preserve shared prompt rendering, taxonomy reconciliation, retry behavior, attempt telemetry, and `MoodtagAnalysis` output across both adapters.
- [x] 2.6 Make retry policy single-endpoint: retry only network/429/5xx, stop on auth and validation/refusal errors, remove cooldown state.

## 3. CLI Setup and Commands

- [x] 3.1 Add `moodtag config setup` interactive flow with protocol selection, base URL, model, hidden key prompt, redacted summary, confirmation, cancellation safety, and atomic persistence.
- [x] 3.2 Add `moodtag config auth` key-only setup using `MOODTAG_API_KEY` and avoid accepting secrets as command-line arguments.
- [x] 3.3 Update `moodtag config set`, `config show`, parser defaults, and effective configuration validation for the single-provider schema.
- [x] 3.4 Run guided setup before model probing when required, preserve the existing Eagle summary and final write confirmation, and provide actionable non-interactive errors.
- [x] 3.5 Remove endpoint-chain output and update run logs to identify only the configured endpoint and protocol without secrets.
- [x] 3.6 Ensure setup/auth non-TTY paths never prompt; preserve shell-key precedence and keep non-model commands usable without endpoint setup.
- [x] 3.7 Remove model endpoint flags from operational commands; expose only non-secret `config set` options and reject secret CLI arguments.

## 4. Tests

- [x] 4.1 Replace old configuration tests with single-provider config, precedence, validation, and secret-safety coverage.
- [x] 4.2 Add local HTTP fixture tests for Chat request paths, multimodal payloads, JSON output, and normalized responses.
- [x] 4.3 Add local HTTP fixture tests for Responses request paths, input image content, structured output settings, ordered output extraction, and refusal/missing-text errors.
- [x] 4.4 Test first-run setup, cancellation, confirmation, `.env` persistence, `config auth`, and non-interactive setup errors.
- [x] 4.5 Verify retry/error behavior, guided tagging safety, dry-run/write flows, and concurrency with one configured endpoint.
- [x] 4.6 Add secret redaction tests using non-`sk-*` keys and persistence rollback tests for partial file-write failure.
- [x] 4.7 Verify exact Chat/Responses payload fields, JSON-mode omission, newline ordering, refusal handling, and concurrent per-item telemetry isolation.
- [x] 4.8 Add a destructive-gated live E2E matrix for the fixed Responses and Chat profiles, resetting the confirmed Eagle folder before each profile and asserting partial/resume/repeat behavior.

## 5. Documentation and Verification

- [x] 5.1 Update README, `.env.example`, contributor docs, and live scripts to document one endpoint, `MOODTAG_API_KEY`, `chat`/`responses`, and setup commands.
- [x] 5.2 Remove obsolete vendor-specific references from user-facing text and tests.
- [x] 5.3 Document clean next-version setup and the absence of endpoint defaults.
- [x] 5.4 Run formatting/lint checks and the complete test suite; verify every OpenSpec scenario against the implemented behavior and run `openspec status --change simplify-single-provider-protocols --json`.
- [x] 5.5 Document the two-profile live E2E command, exact reset scope, runtime-only credential variables, and generated reports without committing secrets.
