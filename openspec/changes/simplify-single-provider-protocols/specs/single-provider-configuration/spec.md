## ADDED Requirements

### Requirement: Single active model endpoint
The system SHALL maintain exactly one active model endpoint with `protocol`, `base_url`, and `model` fields, plus existing non-model settings such as the Eagle API URL.

#### Scenario: Complete configuration is loaded
- **WHEN** configuration contains valid `protocol`, `base_url`, and `model`
- **THEN** model commands use those values without vendor-specific inference

#### Scenario: Incomplete configuration is loaded
- **WHEN** any required model field is absent
- **THEN** interactive commands offer setup and non-interactive commands report the missing fields and setup command

### Requirement: Single environment credential
The system SHALL read the active endpoint credential from `MOODTAG_API_KEY`, preferring an inherited shell value over the user `.env` file.

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

#### Scenario: Setup is confirmed
- **WHEN** a user confirms interactive setup
- **THEN** the key is written only to the configured `.env` file and the non-secret fields are written to JSON

### Requirement: Replaceable configuration commands
The system SHALL provide `moodtag config set`, `moodtag config setup`, and `moodtag config auth` for replacing non-secret settings, the complete endpoint, and only the credential respectively.

#### Scenario: User switches protocol or endpoint
- **WHEN** `moodtag config set` receives protocol, base URL, or model values
- **THEN** the supplied values replace the active configuration without creating a second provider

#### Scenario: User changes only the key
- **WHEN** `moodtag config auth` completes successfully
- **THEN** only `MOODTAG_API_KEY` in `.env` is replaced
