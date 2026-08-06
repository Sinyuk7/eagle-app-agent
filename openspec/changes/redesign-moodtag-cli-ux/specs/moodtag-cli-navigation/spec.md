## ADDED Requirements

### Requirement: TTY main menu
The system SHALL show a numbered main menu when `moodtag` is started without arguments in an interactive TTY.

#### Scenario: Open menu
- **WHEN** the user runs `moodtag` with no arguments and stdin/stdout are TTYs
- **THEN** the CLI SHALL show options for tagging, selecting profile, configuring the model service, and quitting

#### Scenario: Non-interactive no-argument run
- **WHEN** the user runs `moodtag` with no arguments and stdin is not a TTY
- **THEN** the CLI SHALL exit without prompting and print an actionable command hint

### Requirement: Direct board routing
The system SHALL route a recognized board URL, ID, name, or path candidate directly to guided tagging without showing the main menu.

#### Scenario: Board URL
- **WHEN** the first user argument is an Eagle folder URL containing a supported folder identifier
- **THEN** the CLI SHALL enter board resolution and guided tagging directly

#### Scenario: Board identifier
- **WHEN** the first user argument is a board identifier or a valid board name/path candidate
- **THEN** the CLI SHALL enter board resolution and guided tagging directly

#### Scenario: Reserved command
- **WHEN** the first user argument is a known command such as `status`, `tag`, `config`, or `help`
- **THEN** the CLI SHALL preserve the existing argparse command path

### Requirement: Menu subflow navigation
The system SHALL allow menu subflows to complete, cancel, or return without implicitly starting another task.

#### Scenario: Return after profile selection
- **WHEN** the user selects and saves a profile
- **THEN** the CLI SHALL return to the main menu with the selected profile visible

#### Scenario: Cancel subflow
- **WHEN** the user enters `b`, `q`, or cancels a menu subflow
- **THEN** the CLI SHALL leave Eagle metadata unchanged and return to the documented parent state

### Requirement: Catalog model-service setup
The system SHALL configure the model service through catalog selections, service URL input, and a hidden API key input.

#### Scenario: Select a model service
- **WHEN** the user selects model-service configuration from the main menu
- **THEN** the CLI SHALL offer Chat Completions and Responses categories, then list only models loaded from the selected category

#### Scenario: Confirm model service
- **WHEN** the user confirms a selected model, valid URL, and API key state
- **THEN** the CLI SHALL persist the model-service configuration and return to the main menu without contacting Eagle or the model

### Requirement: Board ambiguity recovery
The system SHALL provide a recoverable board selection path when a name or path matches multiple boards.

#### Scenario: Ambiguous board
- **WHEN** Eagle returns multiple matching boards
- **THEN** the CLI SHALL list selectable candidates and allow retry, back, or quit without a traceback
