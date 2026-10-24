## 1. Remote model capability and request policy

- [x] 1.1 Extend the model catalog entry format and loader with `explicit_prompt_cache`, defaulting missing values to false.
- [x] 1.2 Mark supported GPT-5.6+ and GPT-6.1 Sol catalog entries with `explicit_prompt_cache=true`; keep custom and unsupported entries disabled.
- [x] 1.3 Add Remote request policy helpers for protocol-specific strict JSON Schema payloads and stable schema naming.
- [x] 1.4 Update Responses payload construction for GPT-6.1 Sol low reasoning, `store=false`, auto image detail, and omitted sampling/output-limit fields.
- [x] 1.5 Move stable Prompt and Taxonomy content into a Developer cache prefix and add capability-gated explicit 30-minute cache options and breakpoint.
- [x] 1.6 Preserve the existing Chat and Responses image data-URL path, profile prompt, taxonomy input, and business schema.
- [x] 1.7 Add payload regression tests for Responses, Chat, strict schema, GPT-6.1 Sol defaults, cache-enabled models, and custom endpoints.

## 2. Transport metadata and Response Envelope

- [x] 2.1 Add `HTTPResponse` and `http_request_with_metadata()` while preserving `http_request()` body-only behavior.
- [x] 2.2 Implement lowercase header normalization and a whitelist for request IDs, Retry-After, rate limits, and supported processing-time values.
- [x] 2.3 Add generic `ResponseMetadata` and `ResponseEnvelope[T]` types in a provider-facing module without changing `MoodtagAnalysis`.
- [x] 2.4 Extract Responses ID, provider status, usage, request ID, HTTP status, elapsed time, and filtered headers into metadata.
- [x] 2.5 Add `analyze_envelope()` and make the compatibility `analyze()` return `analyze_envelope().data` after one parse.
- [x] 2.6 Add focused tests proving legacy callers still receive `MoodtagAnalysis` and Envelope callers receive usage and diagnostics.

## 3. Business status and submission diagnostics

- [x] 3.1 Add Responses status validation for completed, incomplete, failed, and refusal before Moodtag JSON parsing.
- [x] 3.2 Add Chat `finish_reason` validation for length, content filtering, and other non-success outcomes.
- [x] 3.3 Extend `ProviderAttempt` with `submission_state` and optional client request ID.
- [x] 3.4 Generate and send `X-Client-Request-Id` only for supported official OpenAI endpoints, while treating it strictly as a trace ID.
- [x] 3.5 Ensure validation failures, HTTP rejections, lost responses, and final errors retain bounded attempt diagnostics without secrets, prompts, images, or raw headers.
- [x] 3.6 Add regression tests for completed, incomplete, failed, refusal, non-success finish reasons, not-sent, response-received, and unknown submission states.

## 4. Retry and Remote concurrency

- [x] 4.1 Classify retryable 429 and transient 5xx responses separately from authentication, quota/billing, schema, and permanent request errors.
- [x] 4.2 Implement valid Retry-After handling with bounded exponential backoff and jitter when the header is absent or invalid.
- [x] 4.3 Prevent automatic replay of attempts whose submission state is unknown and preserve the existing bounded retry limit.
- [x] 4.4 Change the Remote default concurrency to 10 while preserving CLI `--concurrency`, first-item serial validation, and bounded Future scheduling.
- [x] 4.5 Verify Ollama concurrency defaults remain independent from the Remote default.
- [x] 4.6 Add focused retry and concurrency tests, including Retry-After, no-retry permanent errors, unknown submission, first-item failure, and maximum worker count.

## 5. Usage and runtime reporting

- [x] 5.1 Preserve original provider usage objects and add normalization helpers for input, output, total, reasoning, cached, and cache-write tokens.
- [x] 5.2 Extend detailed JSON/diagnostic output with Envelope metadata while keeping default CLI summaries concise.
- [x] 5.3 Add estimated cost reporting only when a configured model price is known; represent missing usage or price as unavailable.
- [x] 5.4 Add tests for usage aggregation, missing usage, missing price, and sensitive-data exclusion.

## 6. Verification and documentation

- [x] 6.1 Document the Remote payload policy, capability-gated caching, strict schema behavior, and no silent JSON fallback.
- [x] 6.2 Document Envelope access, status validation, submission states, and the distinction between response ID and client request ID.
- [x] 6.3 Document Remote default concurrency 10, CLI override behavior, Retry-After handling, and Ollama independence.
- [x] 6.4 Run focused provider, response, retry, and concurrency tests, then run the complete test suite and lint checks.
