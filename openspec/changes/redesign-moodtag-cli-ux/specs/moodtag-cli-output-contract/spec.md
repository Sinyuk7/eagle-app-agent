## ADDED Requirements

### Requirement: stdout and stderr separation
The system SHALL write human-facing UI, progress, verbose records, diagnostics, and errors to stderr, reserving stdout for machine-readable data.

#### Scenario: Interactive tagging
- **WHEN** a user runs a normal tagging workflow
- **THEN** the home state, confirmation, spinner, progress, and completion UI SHALL be written to stderr

#### Scenario: JSON pipeline
- **WHEN** a user requests `--json`
- **THEN** stdout SHALL contain only one final structured JSON document without ANSI escape sequences or human UI text

### Requirement: Defined output levels
The system SHALL support `-q`, default, `-v`, and `-vv` output levels with stable information boundaries.

#### Scenario: Quiet mode
- **WHEN** a user passes `-q`
- **THEN** the CLI SHALL suppress workflow UI and item records, emitting only final summary and errors

#### Scenario: Verbose modes
- **WHEN** a user passes `-v` or `-vv`
- **THEN** `-v` SHALL include item outcomes and `-vv` SHALL additionally include endpoint, model, retry, HTTP category, and timing diagnostics

### Requirement: Sensitive output exclusion
The system SHALL never output secrets or request content at any output level.

#### Scenario: Maximum verbosity
- **WHEN** a user passes `-vv`
- **THEN** output SHALL omit API keys, authorization headers, prompts, image data, and raw model responses

### Requirement: Terminal-safe rendering
The system SHALL use animation and color only on a capable TTY and SHALL respect explicit plain-output signals.

#### Scenario: Animated TTY
- **WHEN** stderr is a capable TTY and color is enabled
- **THEN** preparation and write waits SHALL use yaspin and known-total progress SHALL use alive-progress

#### Scenario: Plain output
- **WHEN** stderr is non-TTY, `TERM=dumb`, `NO_COLOR=1`, or `--plain` is set
- **THEN** the CLI SHALL emit stable line-oriented stderr output without ANSI escape sequences, spinner frames, or progress animation
