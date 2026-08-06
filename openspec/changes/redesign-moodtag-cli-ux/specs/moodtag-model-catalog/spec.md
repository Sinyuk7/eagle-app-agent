## ADDED Requirements

### Requirement: Two fixed model catalogs
The system SHALL load available model choices from separate package resources for Chat Completions and Responses.

#### Scenario: Load bundled catalogs
- **WHEN** Moodtag loads model choices
- **THEN** it SHALL load `chat.json` and `responses.json` from bundled model resources and validate every model ID is non-empty and unique across both files

#### Scenario: Initial catalog contents
- **WHEN** the bundled catalogs are loaded
- **THEN** Chat SHALL contain `qwen3.5-122b-a10b`, and Responses SHALL contain `gpt-5.6-luna` marked recommended and `gpt-5.6-terra`

### Requirement: Derive protocol from model ID
The system SHALL derive the request protocol exclusively from the model catalog entry.

#### Scenario: Chat model
- **WHEN** the effective model is `qwen3.5-122b-a10b`
- **THEN** the system SHALL use the Chat Completions adapter

#### Scenario: Responses model
- **WHEN** the effective model is `gpt-5.6-luna` or `gpt-5.6-terra`
- **THEN** the system SHALL use the Responses adapter

#### Scenario: Unknown model
- **WHEN** saved or supplied configuration names a model absent from both catalogs
- **THEN** the system SHALL not issue a model request and SHALL direct the user to select a supported model

### Requirement: Minimal model-service persistence
The system SHALL persist only the service URL and model ID as non-secret model-service configuration, and the API key as a secret.

#### Scenario: Save configuration
- **WHEN** the user confirms model-service setup
- **THEN** the system SHALL save `base_url` and `model` in user configuration and save `MOODTAG_API_KEY` in the owner-only user credential file

#### Scenario: First-time API key
- **WHEN** no saved API key exists during model-service setup
- **THEN** the CLI SHALL require a non-empty hidden API key before allowing confirmation

#### Scenario: Retain existing API key
- **WHEN** a saved API key exists during model-service setup and the user leaves the hidden key input empty
- **THEN** the CLI SHALL retain the saved key and update only the confirmed non-secret model-service values

#### Scenario: Display configuration
- **WHEN** the user views configuration
- **THEN** the system SHALL show the derived protocol, URL, model ID, and API-key readiness without showing the key value or internal variable name

### Requirement: Remove deprecated provider configuration
The system SHALL remove protocol and free-form model configuration from the user-facing model-service contract.

#### Scenario: Removed fields
- **WHEN** a user configures a model service
- **THEN** the CLI SHALL not accept, prompt for, save, or document `protocol`, `MOODTAG_PROTOCOL`, `MOODTAG_BASE_URL`, or `MOODTAG_MODEL`

#### Scenario: Clean beta contract
- **WHEN** Moodtag reads model-service configuration
- **THEN** it SHALL recognize only the current URL, model ID, and API-key contract and SHALL not implement legacy provider compatibility or configuration conversion
