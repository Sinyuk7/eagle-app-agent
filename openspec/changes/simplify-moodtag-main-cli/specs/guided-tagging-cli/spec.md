## ADDED Requirements

### Requirement: Single-command main flow
The system MUST support the primary tagging flow through a single command that accepts either an Eagle board URL or an Eagle board ID.

#### Scenario: Accept board URL
- **WHEN** a user runs the main command with an Eagle folder URL
- **THEN** the system SHALL resolve the target board from that URL and continue the tagging flow

#### Scenario: Accept board ID
- **WHEN** a user runs the main command with an Eagle folder ID
- **THEN** the system SHALL resolve the target board from that ID and continue the tagging flow

### Requirement: Pre-execution summary
The system MUST show a concise summary before any write action begins, including target board, item count, scope, and overwrite risk.

#### Scenario: Summary before execution
- **WHEN** the user starts the main tagging flow
- **THEN** the system SHALL display the resolved board, planned item scope, and whether metadata will be overwritten

### Requirement: Explicit confirmation before write
The system MUST require explicit user confirmation before writing changes to Eagle.

#### Scenario: Abort on no confirmation
- **WHEN** the user does not confirm the write step
- **THEN** the system SHALL not modify Eagle metadata

#### Scenario: Proceed on confirmation
- **WHEN** the user confirms the write step
- **THEN** the system SHALL write the planned metadata changes to Eagle

### Requirement: Auto setup on missing key
The system MUST automatically guide the user through setup when the guided main flow does not find a usable API key.

#### Scenario: Prompt for key
- **WHEN** the user starts the guided main flow and no usable API key is available
- **THEN** the system SHALL prompt for setup before continuing

#### Scenario: Persist key locally
- **WHEN** the user completes setup in the guided main flow
- **THEN** the system SHALL persist the API key in `~/.config/moodtag/.env`

### Requirement: Keep help and config support
The system MUST retain help and config entry points as necessary supporting commands for the main flow.

#### Scenario: Access help
- **WHEN** the user requests help
- **THEN** the system SHALL provide command usage guidance

#### Scenario: Access config
- **WHEN** the user requests configuration management
- **THEN** the system SHALL allow viewing and editing non-secret defaults
