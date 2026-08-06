## ADDED Requirements

### Requirement: Chat protocol analysis
The system SHALL support a `chat` protocol that posts one image-analysis request to `{base_url}/chat/completions` using Chat Completions message and image content shapes.

#### Scenario: Chat request succeeds
- **WHEN** a configured chat endpoint returns a valid assistant message
- **THEN** the extracted content is normalized into `MoodtagAnalysis`

#### Scenario: Chat endpoint rejects the request
- **WHEN** the endpoint returns an HTTP or malformed-response error
- **THEN** the system reports the protocol request failure without trying a second provider

### Requirement: Responses protocol analysis
The system SHALL support a `responses` protocol that posts one image-analysis request to `{base_url}/responses` using Responses input item and image content shapes.

#### Scenario: Responses request succeeds
- **WHEN** a configured responses endpoint returns ordered `output_text` content parts
- **THEN** the parts are joined in order and normalized into `MoodtagAnalysis`

#### Scenario: Responses output contains no text
- **WHEN** the response has no usable `output_text` or contains a refusal
- **THEN** the system raises a clear core error and does not write Eagle metadata

### Requirement: Shared analysis contract
Both protocol adapters SHALL reuse the existing prompts, taxonomy validation, retry count, and `MoodtagAnalysis` normalization after protocol-specific text extraction.

#### Scenario: Same taxonomy across protocols
- **WHEN** equivalent chat and responses requests return the same JSON content
- **THEN** both produce equivalent normalized tags and annotation fields

### Requirement: Protocol selection is explicit
The system SHALL accept only `chat` or `responses` as protocol values and SHALL not infer protocol or provider from the endpoint hostname.

#### Scenario: Invalid protocol
- **WHEN** configuration contains another protocol value
- **THEN** validation fails before Eagle access or model requests
