## ADDED Requirements

### Requirement: One-focus workflow UI
The system SHALL present one primary human focus for each workflow state.

#### Scenario: Accepted confirmation
- **WHEN** the user accepts tagging confirmation in a capable TTY
- **THEN** the CLI SHALL replace or clear the active confirmation region before rendering processing feedback

#### Scenario: Plain-terminal fallback
- **WHEN** terminal cursor control is unavailable
- **THEN** the CLI SHALL emit concise line-oriented state transitions without attempting to rewrite prior lines

### Requirement: Human execution phases
The system SHALL present preparation, analysis, write, and completion as the default execution phases.

#### Scenario: Preparation
- **WHEN** the CLI is resolving Eagle state, checking AI readiness, or probing the first image
- **THEN** it SHALL present a user-facing preparation state without internal transport-step names

#### Scenario: Analysis and write
- **WHEN** bulk analysis completes and successful results are ready to persist
- **THEN** the CLI SHALL transition from analysis feedback to write feedback before Eagle metadata updates begin

### Requirement: Streaming analysis feedback
The system SHALL provide active feedback while a known set of images is being analyzed.

#### Scenario: TTY progress
- **WHEN** analysis runs in a capable TTY
- **THEN** the CLI SHALL render alive-progress feedback with completed/selected count and retain the most recent 2-3 completed item outcomes

#### Scenario: Concurrent completion
- **WHEN** a later concurrent item completes before an earlier item
- **THEN** visible progress and recent outcomes SHALL advance on completion without waiting for original item order

### Requirement: Unified status language
The system SHALL use the same symbols and text semantics across home, confirmation, progress, error, and completion output.

#### Scenario: State symbol
- **WHEN** the CLI presents a waiting, active, success, warning/skip, failure, or next action state
- **THEN** it SHALL use respectively `○`, `…`, `✓`, `!`, `×`, or `→` together with descriptive text

### Requirement: Safe cancellation
The system SHALL handle Ctrl-C during menu, setup, analysis, and write phases without a traceback.

#### Scenario: Cancel analysis
- **WHEN** the user presses Ctrl-C once during analysis
- **THEN** the CLI SHALL stop scheduling new work, finish safe in-flight work where possible, and show completed and unprocessed counts

#### Scenario: Force cancellation
- **WHEN** the user presses Ctrl-C again during cancellation
- **THEN** the CLI SHALL exit promptly and report that partial writes may already exist
