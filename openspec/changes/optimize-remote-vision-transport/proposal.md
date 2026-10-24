## Why

Moodtag’s remote vision path currently sends a generic payload, discards successful response metadata, treats HTTP success as sufficient evidence of model success, and uses retry/concurrency defaults that do not reflect the agreed GPT-6.1 Sol workload. This makes structured output less reliable and leaves token usage, request identifiers, rate-limit signals, and uncertain submissions unavailable for diagnostics.

## What Changes

- Add a capability-aware remote payload policy for supported Remote models:
  - Strict JSON Schema for Responses and Chat Completions.
  - GPT-5.6+ and GPT-6.1 Sol explicit prompt-cache options with a 30-minute TTL and a cache breakpoint.
  - GPT-6.1 Sol Responses defaults of low reasoning effort, auto image detail, no sampling parameters, no default output-token cap, and `store=false`.
- Preserve the existing Moodtag prompt, taxonomy, `MoodtagAnalysis`, and Eagle writeback contracts.
- Add transport metadata handling with a compatibility-preserving `HTTPResponse`, `ResponseMetadata`, and generic `ResponseEnvelope`.
- Keep `analyze()` returning `MoodtagAnalysis); add `analyze_envelope()` for callers that need usage and diagnostics.
- Preserve a whitelist of normalized response headers, including request IDs, retry timing, rate-limit values, and supported processing-time signals.
- Validate Responses business status and Chat completion status before parsing or writing a result.
- Track submission state (`not_sent`, `unknown`, `response_received`) in `ProviderAttempt`, including a client request ID for supported official endpoints.
- Improve retry behavior with Retry-After, bounded exponential backoff, jitter, and permanent-error handling without cross-provider fallback.
- Set Remote’s default concurrency to 10 while preserving the existing CLI override, first-item validation, worker pool, and independent Ollama defaults.
- Add focused regression tests for payloads, schema strictness, metadata, status handling, retry decisions, and bounded concurrency.

## Capabilities

### New Capabilities

- `remote-vision-request-policy`: Defines Remote payload construction, strict structured outputs, model capabilities, prompt caching, image detail, and GPT-6.1 Sol defaults.
- `remote-response-envelope`: Defines transport metadata, provider response status validation, submission diagnostics, usage preservation, and compatibility accessors.
- `remote-execution-policy`: Defines Remote retry, concurrency, first-item validation, and bounded worker behavior.

### Modified Capabilities

<!-- No existing spec-level requirements are changed; this change adds Remote provider capabilities while preserving the existing domain and writeback contracts. -->

## Impact

Primary code areas are `moodtag_core/remote.py`, `moodtag_core/common.py`, `moodtag_core/catalog.py`, `moodtag_core/response.py`, `moodtag/cli.py`, and focused provider/workflow tests. The implementation continues using the current HTTP library and worker pool, adds no required OpenAI SDK, database, or public user configuration parameters, and does not change `MoodtagAnalysis`, Taxonomy, or Eagle metadata-safe writeback.
