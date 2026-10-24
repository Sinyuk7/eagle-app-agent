## Context

Moodtag currently uses a single Remote `VisionClient` path for Chat Completions and Responses. Request construction, transport, response parsing, retry bookkeeping, and business normalization are separated only partially. The current path sends generic sampling/output parameters, defaults to JSON Object mode, returns only `MoodtagAnalysis`, and loses successful response metadata such as usage, provider status, response ID, request ID, and useful response headers.

The reference implementation in `ComfyUI-Sinyuk-Nodes/sinyuk_nodes/features/llm` provides useful separation for request construction, image preparation, HTTP client behavior, and response extraction. Moodtag will reuse those request and parameter patterns while retaining its current synchronous HTTP implementation, provider catalog, worker pool, prompt source, taxonomy validation, and Eagle writeback contract.

## Goals / Non-Goals

**Goals:**

- Send strict structured outputs for every supported Remote model.
- Apply the agreed GPT-6.1 Sol request defaults and capability-gated prompt caching.
- Preserve useful transport and provider metadata through a generic Response Envelope.
- Validate provider business status before parsing or writing analysis results.
- Make retry behavior honor Retry-After and distinguish unknown submission state.
- Set Remote default concurrency to 10 while preserving CLI overrides and Ollama behavior.
- Add focused tests for payloads, metadata, status, retry, and bounded concurrency.

**Non-Goals:**

- Do not change `MoodtagAnalysis`, Prompt, Taxonomy, annotation format, or Eagle metadata-safe writeback.
- Do not introduce a required OpenAI SDK, new database, request recovery service, or public configuration flags.
- Do not use `previous_response_id`, streaming, Batch API, automatic provider fallback, or adaptive concurrency.
- Do not assume strict schema or prompt-cache extensions for custom endpoints beyond the declared catalog capability.
- Do not retain complete raw HTTP headers, prompts, images, authorization values, or raw response bodies in diagnostics.

## Decisions

### 1. Capability-aware Remote request policy

The model catalog gains an `explicit_prompt_cache` capability. GPT-5.6+ and GPT-6.1 Sol entries that are known to support explicit caching set it to true; other models and custom endpoints do not receive the extension.

Every supported Remote model uses strict JSON Schema. Responses requests use `text.format`; Chat Completions requests use `response_format`. Providers that reject the required strict schema report incompatibility and do not silently fall back to JSON Object mode.

For GPT-6.1 Sol Responses requests, the default payload sends `reasoning.effort=low`, `store=false`, `detail=auto`, and no `temperature`, `top_p`, or `max_output_tokens`. The implementation may keep internal policy values, but omitted fields remain omitted from the wire payload.

When `explicit_prompt_cache` is true, the stable Developer prompt and taxonomy form the cacheable prefix, with explicit mode, a 30-minute TTL, and one breakpoint at the end of the stable prefix. Per-image content remains in a separate User message. No response-session chaining is used.

### 2. Three-layer response handling

Transport adds `HTTPResponse(data, status, headers)`. Existing `http_request()` continues returning only the decoded body; `http_request_with_metadata()` exposes the transport envelope to Remote provider code.

Provider metadata lives in a separate `ResponseMetadata` and generic `ResponseEnvelope[T]`. Metadata includes protocol, model, response ID, client request ID, provider status, HTTP status, original usage mapping, elapsed time, and a normalized whitelist of useful headers.

`analyze()` remains the compatibility method returning `MoodtagAnalysis`. It delegates to `analyze_envelope()` and returns `.data`. The response body is parsed exactly once.

### 3. Header and secret policy

Response headers are normalized to lowercase and filtered to a fixed whitelist: request IDs, Retry-After, rate-limit remaining/reset values, and supported processing-time signals. Success and failure diagnostics may carry this filtered set. Authorization headers, complete headers, image data, prompts, and raw bodies are excluded from persisted diagnostics.

For supported official OpenAI endpoints, the client sends a unique `X-Client-Request-Id` and records the same value. It is a trace identifier only and is never treated as an idempotency key.

### 4. Provider status and submission state

Responses business status is checked before business JSON parsing. Only `completed` responses may produce a successful analysis. `incomplete` includes `incomplete_details` in diagnostics; `failed` includes the provider error; refusal is treated as a failed analysis. Chat Completions checks `finish_reason`, including `length` and content-filter outcomes.

`ProviderAttempt` gains submission state with `not_sent`, `unknown`, and `response_received`. An HTTP rejection is `response_received`; a transport loss after submission is `unknown`; validation before sending is `not_sent`. Final errors retain the relevant attempt diagnostics.

### 5. Retry and concurrency

Remote retry decisions remain bounded and task-local. Authentication, quota/billing, permanent validation, and other permanent request errors are not retried. HTTP 429 and transient 5xx failures prefer a valid Retry-After value; otherwise they use exponential backoff with jitter. Unknown-submission transport failures are not blindly replayed because a remote generation may already exist.

The existing `ThreadPoolExecutor` and bounded Future scheduling remain in place. Remote default concurrency becomes 10, the CLI `--concurrency` override remains authoritative, the first-item serial validation remains, and Ollama defaults are unchanged. Image preprocessing and queued work remain bounded by the existing worker design.

### 6. Usage and summary

The original provider usage object is retained in `ResponseMetadata.usage`. A later summary layer may normalize input, output, reasoning, cached, and cache-write token fields and calculate estimated cost only when a known price is configured. Missing usage or price is represented as unavailable, never as zero. Default CLI output stays concise; detailed metadata is available through existing JSON/diagnostic paths.

## Risks / Trade-offs

- [Some Compatible Providers reject strict JSON Schema] → Report explicit incompatibility and keep the provider from silently changing output guarantees.
- [Prompt-cache extension is unsupported by custom endpoints] → Gate both cache options and breakpoint on the catalog capability.
- [A lost response may represent a completed remote POST] → Record `unknown` submission state and do not automatically replay it.
- [Provider status fields vary between protocols] → Normalize only the known Responses and Chat fields before business parsing.
- [Usage schemas vary across providers] → Preserve the original usage mapping and normalize only in reporting.
- [Additional metadata increases runtime object size] → Keep only whitelisted headers and bounded diagnostic strings.

## Migration Plan

1. Add capability metadata and request policy helpers without changing existing public analysis calls.
2. Add transport metadata and Envelope types; keep compatibility wrappers returning body and `MoodtagAnalysis`.
3. Update Remote payload construction and status validation, then add focused regression tests.
4. Integrate Retry-After/backoff and submission-state diagnostics.
5. Change only the Remote default concurrency and verify the first-item validation path and Ollama defaults.
6. Roll back by disabling the new Remote policy and Envelope path; the existing `analyze()` and domain contracts remain usable throughout.

## Open Questions

None. The decisions in the change request are final for this proposal.
