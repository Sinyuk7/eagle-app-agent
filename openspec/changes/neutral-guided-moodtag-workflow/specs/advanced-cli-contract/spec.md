## ADDED Requirements

### Requirement: Advanced automation controls remain available
The advanced tag command SHALL retain explicit write, force, limit, board-size, dry-run, and JSON controls for Agent and script use.

#### Scenario: Agent invokes explicit write mode
- **WHEN** an automation invokes the advanced tag command with explicit write controls
- **THEN** the command SHALL perform the documented non-interactive operation and preserve its machine-readable result contract

#### Scenario: Agent invokes dry-run mode
- **WHEN** an automation omits explicit write mode or requests a dry run
- **THEN** the command SHALL analyze without Eagle updates and report the result without requiring the guided policy menu

### Requirement: Ordinary help hides implementation controls
The primary command help and README SHALL describe the task flow and link to advanced reference material instead of teaching internal flags.

#### Scenario: User reads primary help
- **WHEN** a user requests help for the ordinary folder command
- **THEN** the output SHALL explain folder scan, policy choices, model source selection, and metadata behavior without presenting endpoint, sampling, or benchmark details

### Requirement: Interactive and machine output remain separated
Menus, progress, and human diagnostics SHALL use stderr, while JSON mode SHALL emit only one final result to stdout.

#### Scenario: JSON automation runs
- **WHEN** an advanced command runs with JSON output
- **THEN** stdout SHALL contain only the final JSON object
