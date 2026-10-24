## ADDED Requirements

### Requirement: Early library limit guard
The library workflow SHALL check an available total count before fetching the full item list.

#### Scenario: Library within limit
- **WHEN** the reported total is at or below the configured maximum
- **THEN** the workflow SHALL continue with normal filtered item resolution

#### Scenario: Library exceeds limit
- **WHEN** the reported total exceeds the configured maximum
- **THEN** the workflow SHALL stop before full download and ask the user to narrow the scope

### Requirement: Recoverable scope errors
Interactive scope failures SHALL return to the nearest meaningful parent state.

#### Scenario: Empty selection
- **WHEN** Eagle has no selected images
- **THEN** the CLI SHALL report the empty scope and offer back or quit without restarting the process
