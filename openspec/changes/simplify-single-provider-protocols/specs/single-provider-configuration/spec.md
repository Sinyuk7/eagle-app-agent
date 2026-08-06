## ADDED Requirements

### Requirement: Single active model endpoint
The system SHALL maintain exactly one active model endpoint with `protocol`, `base_url`, and `model` fields, plus existing non-model settings such as the Eagle API URL.

#### Scenario: Clean configuration has no vendor default
- **WHEN** no endpoint fields exist
- **THEN** `config show` reports them as incomplete and no model request is attempted with a vendor-supplied default

#### Scenario: Complete configuration is loaded
- **WHEN** configuration contains valid `protocol`, `base_url`, and `model`
- **THEN** model commands use those values without vendor-specific inference

#### Scenario: Invalid protocol is rejected before side effects
- **WHEN** `protocol` is not `chat` or `responses`
- **THEN** validation fails before Eagle access, file reads, or model requests

#### Scenario: Old endpoint slots are not supported
- **WHEN** a config file contains old provider or fallback fields
- **THEN** those fields are ignored by the new schema, no endpoint or credential is inferred from them, and model commands require a fresh `moodtag config setup`

#### Scenario: Endpoint URL is normalized and validated
- **WHEN** a complete config uses an absolute `http`/`https` root, `/v1`, or protocol endpoint URL
- **THEN** the selected protocol appends exactly its endpoint path, while userinfo, query, fragment, empty, and malformed URLs are rejected

#### Scenario: Incomplete configuration is loaded
- **WHEN** any required model field is absent
- **THEN** interactive commands offer setup and non-interactive commands report the missing fields and setup command

### Requirement: Single environment credential
The system SHALL read the active endpoint credential from `MOODTAG_API_KEY`, preferring inherited shell environment over user `.env`, and user `.env` over current-working-directory `.env`.

#### Scenario: Credential is present in the shell
- **WHEN** `MOODTAG_API_KEY` exists in the process environment
- **THEN** its value is used and the `.env` value is not loaded over it

#### Scenario: Credential is absent
- **WHEN** no shell or `.env` value exists
- **THEN** API-requiring commands report that `MOODTAG_API_KEY` is missing

### Requirement: Secret-safe persistence and display
The system SHALL never write the API key to JSON configuration, CLI arguments, run logs, or user-facing output.

#### Scenario: Configuration is displayed
- **WHEN** a user runs `moodtag config show`
- **THEN** output reports only `set` or `unset` for the credential

#### Scenario: Arbitrary secret format is redacted
- **WHEN** the configured key appears in an HTTP error, retry record, or CLI error
- **THEN** the exact key value is absent from every log and user-facing message

#### Scenario: Setup is confirmed
- **WHEN** a user confirms interactive setup
- **THEN** the key is written only to the configured `.env` file and the non-secret fields are written to JSON

### Requirement: Replaceable configuration commands
The system SHALL provide `moodtag config set`, `moodtag config setup`, and `moodtag config auth` for replacing non-secret settings, the complete endpoint, and only the credential respectively.

#### Scenario: Non-interactive config set syntax
- **WHEN** `moodtag config set` receives `--protocol`, `--base-url`, `--model`, or `--eagle-api`
- **THEN** it validates supplied values, updates only supplied non-secret fields, and accepts no API-key argument

#### Scenario: Partial config update remains actionable
- **WHEN** `config set` leaves the model tuple incomplete
- **THEN** it persists the non-secret update but model commands continue to require setup; no vendor default fills missing fields

#### Scenario: User switches protocol or endpoint
- **WHEN** `moodtag config set` receives protocol, base URL, or model values
- **THEN** the supplied values replace the active configuration without creating a second endpoint

#### Scenario: User changes only the key
- **WHEN** `moodtag config auth` completes successfully
- **THEN** only `MOODTAG_API_KEY` in `.env` is replaced

#### Scenario: Setup and auth reject secret CLI arguments
- **WHEN** a secret is supplied as an option to `config set`, `config setup`, or `config auth`
- **THEN** argument parsing rejects it and no secret is persisted or echoed

#### Scenario: Shell precedence is explicit
- **WHEN** inherited `MOODTAG_API_KEY` and a different `.env` key both exist
- **THEN** runtime uses the inherited value, while `config auth` updates only persisted `.env`

### Requirement: Single-endpoint retry and telemetry
The system SHALL retry only the configured endpoint and SHALL not persist endpoint-chain state.

#### Scenario: Retryable failure
- **WHEN** the endpoint returns 429/5xx or a network error
- **THEN** the same protocol/URL is retried up to `retries + 1` attempts with no second endpoint

#### Scenario: Non-model commands remain available
- **WHEN** endpoint configuration is missing or invalid
- **THEN** `status`, `brief`, `export-context`, and `reset` can run unless their own Eagle requirements fail

#### Scenario: Telemetry has no endpoint chain
- **WHEN** a model run emits stdout or JSONL telemetry
- **THEN** it identifies protocol and sanitized endpoint/model, preserves per-item timings/source strategy, and contains no endpoint-chain state, cooldown, header, body, image data URL, or key
