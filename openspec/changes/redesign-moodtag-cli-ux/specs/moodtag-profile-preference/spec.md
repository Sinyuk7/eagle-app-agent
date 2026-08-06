## ADDED Requirements

### Requirement: Persist selected profile
The system SHALL persist the last confirmed profile as a non-secret user configuration value.

#### Scenario: Save profile
- **WHEN** the user selects a valid profile and confirms the choice
- **THEN** the CLI SHALL write that profile to user configuration and use it on later model commands

#### Scenario: Missing profile
- **WHEN** no persisted profile exists
- **THEN** the CLI SHALL use `editorial`

### Requirement: Profile precedence
The system SHALL apply a one-run CLI profile override without changing the persisted profile.

#### Scenario: Explicit override
- **WHEN** the user supplies `--profile editorial`
- **THEN** the current run SHALL use `editorial` while the persisted profile remains unchanged

### Requirement: Profile validation
The system SHALL reject unknown profiles before starting Eagle writes or model requests.

#### Scenario: Unknown profile
- **WHEN** the selected or configured profile is not available
- **THEN** the CLI SHALL show available profiles and leave the previous persisted profile unchanged
