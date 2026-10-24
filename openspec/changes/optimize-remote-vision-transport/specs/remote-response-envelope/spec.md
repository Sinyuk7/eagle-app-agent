## ADDED Requirements

### Requirement: Transport metadata is available without breaking body callers

The transport layer SHALL provide an `HTTPResponse` containing decoded data, HTTP status, and filtered headers. Existing `http_request()` callers SHALL continue receiving only decoded response data.

#### Scenario: Legacy HTTP caller

- **WHEN** existing code calls `http_request()`
- **THEN** it SHALL receive the same decoded body shape as before

#### Scenario: Metadata HTTP caller

- **WHEN** Remote provider code calls `http_request_with_metadata()`
- **THEN** it SHALL receive decoded data, HTTP status, and normalized whitelisted headers

### Requirement: Response metadata is preserved in a generic Envelope

The Remote provider SHALL expose `ResponseEnvelope[MoodtagAnalysis]` containing the existing business result and `ResponseMetadata`. Metadata SHALL preserve protocol, model, response ID, client request ID, provider status, HTTP status, original usage, elapsed time, and whitelisted diagnostic headers.

#### Scenario: Envelope success

- **WHEN** a Remote request completes with a valid provider response
- **THEN** `analyze_envelope()` SHALL return the parsed `MoodtagAnalysis` in `.data` and all available response metadata in `.metadata`

#### Scenario: Legacy analysis caller

- **WHEN** existing code calls `analyze()`
- **THEN** it SHALL receive `MoodtagAnalysis` directly and SHALL not need to know about the Envelope

#### Scenario: Usage is absent

- **WHEN** a provider response has no usage object
- **THEN** the Envelope SHALL preserve an empty or explicitly unavailable usage value and SHALL NOT report zero usage

### Requirement: Response headers are normalized and filtered

The provider SHALL lowercase header names and retain only request ID, Retry-After, rate-limit, and supported processing-time headers. It SHALL NOT persist complete headers or sensitive request data.

#### Scenario: Whitelisted headers

- **WHEN** an HTTP response contains request, retry, rate-limit, and processing-time headers
- **THEN** the Envelope diagnostics SHALL include those headers using lowercase names

#### Scenario: Sensitive headers

- **WHEN** an HTTP response or request context contains Authorization, image data, Prompt text, or other sensitive values
- **THEN** those values SHALL NOT be included in persisted response metadata

### Requirement: Provider business status is validated before analysis writeback

The Remote provider SHALL validate protocol business status before parsing the Moodtag JSON and SHALL only return a successful analysis when the provider indicates completion.

#### Scenario: Completed Responses result

- **WHEN** a Responses response has HTTP success and `status=completed`
- **THEN** the provider SHALL parse the output and may return a successful Envelope

#### Scenario: Incomplete Responses result

- **WHEN** a Responses response has `status=incomplete`
- **THEN** the provider SHALL fail the analysis with bounded `incomplete_details` diagnostics and SHALL NOT write the result to Eagle

#### Scenario: Failed or refused Responses result

- **WHEN** a Responses response has `status=failed` or a refusal
- **THEN** the provider SHALL fail the analysis with provider diagnostics and SHALL NOT write the result to Eagle

#### Scenario: Chat non-completed result

- **WHEN** a Chat Completions response has a non-success `finish_reason`, including `length` or content filtering
- **THEN** the provider SHALL fail the analysis before writing business output

### Requirement: Submission state is retained per ProviderAttempt

Each Remote attempt SHALL record one of `not_sent`, `unknown`, or `response_received`. Supported official OpenAI endpoints SHALL receive a unique `X-Client-Request-Id`, and the same ID SHALL be recorded for diagnostics without being treated as an idempotency key.

#### Scenario: Validation before transport

- **WHEN** request validation fails before an HTTP POST is sent
- **THEN** the attempt SHALL record `not_sent`

#### Scenario: HTTP response received

- **WHEN** the server returns an HTTP response, including a rejected response
- **THEN** the attempt SHALL record `response_received`

#### Scenario: Response is lost after submission

- **WHEN** transport loses the response after submission status is unknown
- **THEN** the attempt SHALL record `unknown` and the final error SHALL retain that diagnostic
