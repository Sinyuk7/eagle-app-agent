## ADDED Requirements

### Requirement: Chat protocol analysis
The system SHALL support a `chat` protocol that posts one image-analysis request to `{base_url}/chat/completions` using Chat Completions message and image content shapes.

#### Scenario: Chat request succeeds
- **WHEN** a configured chat endpoint returns a valid assistant message
- **THEN** the extracted content is normalized into `MoodtagAnalysis`

#### Scenario: Chat payload contract
- **WHEN** a chat request is built
- **THEN** it contains `model`, `store:false`, `temperature`, `top_p`, `max_tokens`, system/user messages, one `image_url` data URL, and optional `response_format.type=json_object` without Responses-only keys

#### Scenario: Chat endpoint rejects the request
- **WHEN** the endpoint returns an HTTP or malformed-response error
- **THEN** the system reports the protocol request failure without switching endpoint or protocol

#### Scenario: Chat content variants
- **WHEN** `message.content` is a string or ordered text-part list
- **THEN** both forms extract in order; refusal, missing content, and malformed choices raise `CoreError` before normalization

### Requirement: Responses protocol analysis
The system SHALL support a `responses` protocol that posts one image-analysis request to `{base_url}/responses` using Responses input item and image content shapes.

#### Scenario: Responses request succeeds
- **WHEN** a configured responses endpoint returns ordered `output_text` content parts
- **THEN** the parts are joined in order and normalized into `MoodtagAnalysis`

#### Scenario: Responses payload contract
- **WHEN** a Responses request is built
- **THEN** it contains `model`, `store:false`, `temperature`, `top_p`, `max_output_tokens`, `input` with `input_text` and `input_image` parts, and optional `text.format.type=json_object`; it uses no `messages` or `response_format` keys

#### Scenario: Responses output contains no text
- **WHEN** the response has no usable `output_text` or contains a refusal
- **THEN** the system raises a clear core error and does not write Eagle metadata

#### Scenario: Responses mixed output
- **WHEN** `output` contains reasoning, non-text parts, and multiple nested `output_text` parts
- **THEN** only ordered `output_text` parts are joined; refusal or absence of usable text raises `CoreError`

#### Scenario: Responses text order is stable
- **WHEN** multiple usable `output_text` parts are present
- **THEN** they are joined with a single newline in original array order before JSON parsing

### Requirement: Shared analysis contract
Both protocol adapters SHALL reuse the existing prompts, taxonomy validation, retry count, and `MoodtagAnalysis` normalization after protocol-specific text extraction.

#### Scenario: Same taxonomy across protocols
- **WHEN** equivalent chat and responses requests return the same JSON content
- **THEN** both produce equivalent normalized tags and annotation fields

#### Scenario: Retry does not change protocol
- **WHEN** a retryable response fails
- **THEN** each retry uses the same adapter, endpoint, and protocol, with no second endpoint request

#### Scenario: Retry error matrix
- **WHEN** network, HTTP 429, or HTTP 5xx failure occurs
- **THEN** the same request is attempted up to `retries + 1` times; HTTP 401/403, refusal, malformed response, and normalization errors stop immediately and never write Eagle metadata

### Requirement: Protocol selection is explicit
The system SHALL accept only `chat` or `responses` as protocol values and SHALL not infer protocol or provider from the endpoint hostname.

#### Scenario: Invalid protocol
- **WHEN** configuration contains another protocol value
- **THEN** validation fails before Eagle access or model requests

### Requirement: Live protocol E2E matrix
The project SHALL provide a secret-safe live E2E matrix that exercises one Responses endpoint and one Chat Completions endpoint against the same explicitly confirmed disposable Eagle folder.

#### Scenario: Responses live profile
- **WHEN** the matrix runs the `responses-gpt-5.6-luna` profile
- **THEN** it uses protocol `responses`, model `gpt-5.6-luna`, and normalized `/v1/responses` endpoint behavior

#### Scenario: Chat live profile
- **WHEN** the matrix runs the `chat-qwen3.5-122b-a10b` profile
- **THEN** it uses protocol `chat`, model `qwen3.5-122b-a10b`, and normalized `/v1/chat/completions` endpoint behavior

#### Scenario: Each profile starts clean
- **WHEN** either live profile starts
- **THEN** the runner requires an exact folder-ID confirmation, clears tags and annotations in that folder, writes a partial batch, resumes remaining items, and verifies a final repeat skips every processed item

#### Scenario: Live credentials remain ephemeral
- **WHEN** the live matrix receives both API keys
- **THEN** it reads them from distinct environment variables, passes only the selected key to the child process as `MOODTAG_API_KEY`, and excludes both values from arguments, reports, stdout, and stderr
