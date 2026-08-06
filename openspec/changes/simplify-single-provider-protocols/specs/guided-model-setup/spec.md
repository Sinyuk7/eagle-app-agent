## ADDED Requirements

### Requirement: Interactive first-run setup
The system SHALL offer a single interactive setup flow when a model command is run in a TTY with incomplete endpoint configuration or a missing key.

#### Scenario: First run in a terminal
- **WHEN** the user invokes the guided board command without complete setup
- **THEN** the CLI asks for protocol, base URL, model, and hidden API key, with `responses` as the default protocol

#### Scenario: Explicit setup command
- **WHEN** the user runs `moodtag config setup` in a TTY
- **THEN** the same prompts run without contacting Eagle and without sending a model request

#### Scenario: Setup is cancelled
- **WHEN** the user cancels or submits an empty required value
- **THEN** no configuration or credential file is changed and the command exits cleanly with status 0

#### Scenario: Non-TTY setup command
- **WHEN** setup or auth needs input while stdin is not a TTY
- **THEN** the command exits with an actionable non-interactive message and does not prompt or partially write

### Requirement: Confirmed setup persistence
The system SHALL display a redacted configuration summary and require confirmation before persisting setup values.

#### Scenario: User confirms setup
- **WHEN** the summary is accepted
- **THEN** non-secret fields are persisted to JSON and the key is persisted to `.env`, then the original guided flow resumes

#### Scenario: Persistence failure
- **WHEN** either config or `.env` replacement fails after confirmation
- **THEN** prior file contents are restored and the command reports failure without running Eagle or the model

#### Scenario: Credential file permissions
- **WHEN** setup or auth creates or replaces `.env`
- **THEN** the file is owner-readable/writable only and the confirmation summary never shows the key value or prefix

#### Scenario: User rejects setup
- **WHEN** the summary is rejected
- **THEN** no new values are persisted and the user can rerun setup

#### Scenario: Key-only replacement
- **WHEN** the user runs `moodtag config auth` and confirms a hidden key prompt
- **THEN** only `MOODTAG_API_KEY` in `.env` changes; inherited shell value remains authoritative

### Requirement: Non-interactive setup error
The system SHALL not prompt for input when stdin is not a TTY.

#### Scenario: CI or redirected input lacks setup
- **WHEN** a model command lacks required configuration in a non-interactive environment
- **THEN** it exits with an actionable message naming `moodtag config setup` and `MOODTAG_API_KEY`

#### Scenario: Non-model commands bypass setup
- **WHEN** endpoint or key is missing
- **THEN** `status`, `brief`, `export-context`, `reset`, `config show`, and `--mock-model` flows remain usable without prompting for model setup

### Requirement: Safe guided tagging order
The guided board flow SHALL complete setup before model probing and SHALL retain the existing final confirmation before writing Eagle metadata.

#### Scenario: Setup and board confirmation succeed
- **WHEN** setup is saved and the board summary is accepted
- **THEN** the first image is probed, then tagging proceeds according to the existing write/dry-run behavior

#### Scenario: Setup precedes Eagle write safety
- **WHEN** guided setup succeeds
- **THEN** setup completes before model probing, board summary and final write confirmation remain, and setup cancellation causes no Eagle metadata writes
