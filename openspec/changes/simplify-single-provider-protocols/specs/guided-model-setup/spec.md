## ADDED Requirements

### Requirement: Interactive first-run setup
The system SHALL offer a single interactive setup flow when a model command is run in a TTY with incomplete endpoint configuration or a missing key.

#### Scenario: First run in a terminal
- **WHEN** the user invokes the guided board command without complete setup
- **THEN** the CLI asks for protocol, base URL, model, and hidden API key, with `responses` as the default protocol

#### Scenario: Setup is cancelled
- **WHEN** the user cancels or submits an empty required value
- **THEN** no configuration or credential file is changed and the command exits cleanly

### Requirement: Confirmed setup persistence
The system SHALL display a redacted configuration summary and require confirmation before persisting setup values.

#### Scenario: User confirms setup
- **WHEN** the summary is accepted
- **THEN** non-secret fields are persisted to JSON and the key is persisted to `.env`, then the original guided flow resumes

#### Scenario: User rejects setup
- **WHEN** the summary is rejected
- **THEN** no new values are persisted and the user can rerun setup

### Requirement: Non-interactive setup error
The system SHALL not prompt for input when stdin is not a TTY.

#### Scenario: CI or redirected input lacks setup
- **WHEN** a model command lacks required configuration in a non-interactive environment
- **THEN** it exits with an actionable message naming `moodtag config setup` and `MOODTAG_API_KEY`

### Requirement: Safe guided tagging order
The guided board flow SHALL complete setup before model probing and SHALL retain the existing final confirmation before writing Eagle metadata.

#### Scenario: Setup and board confirmation succeed
- **WHEN** setup is saved and the board summary is accepted
- **THEN** the first image is probed, then tagging proceeds according to the existing write/dry-run behavior
