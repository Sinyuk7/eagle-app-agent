## ADDED Requirements

### Requirement: Local-first model recommendation
The system SHALL present Ollama local inference as the primary recommendation for new users while keeping cloud and custom OpenAI-compatible providers available as explicit alternatives.

#### Scenario: New user opens model setup
- **WHEN** no model source is configured
- **THEN** the local Ollama choice is presented first with service/model readiness and no API-key requirement

#### Scenario: Existing user upgrades
- **WHEN** an existing user has a configured remote endpoint
- **THEN** the upgrade preserves that endpoint and does not silently change where images are sent

### Requirement: User-visible image destination
The system SHALL show whether images remain on the local machine or are sent to a remote service before analysis begins.

#### Scenario: Select cloud source
- **WHEN** a user selects a cloud or remote custom provider
- **THEN** setup and run confirmation state that image data will be sent to that remote endpoint

#### Scenario: Local service unavailable
- **WHEN** a local source is selected but Ollama is unavailable
- **THEN** the user receives local troubleshooting guidance and must explicitly select another source before remote processing can occur
