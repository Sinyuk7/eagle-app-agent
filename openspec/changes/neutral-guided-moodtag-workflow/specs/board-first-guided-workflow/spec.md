## ADDED Requirements

### Requirement: The main command scans the board before model setup
The guided folder command SHALL load the Eagle scope and display processing statistics before initializing a model provider or requesting credentials.

#### Scenario: Folder contains mixed metadata states
- **WHEN** the command loads a folder containing pending images, existing Moodtag descriptions, and unsupported media
- **THEN** it SHALL display total, existing, pending, and unsupported counts before any model setup or image request

#### Scenario: User exits from the summary
- **WHEN** the user selects exit from the policy menu
- **THEN** the command SHALL make no provider request, credential request, or Eagle update

### Requirement: The policy menu has an Enter default
The guided command SHALL offer skip-existing, overwrite-existing, and exit, with skip-existing as the first and default choice.

#### Scenario: User presses Enter
- **WHEN** the user submits an empty response at the policy menu
- **THEN** the command SHALL select skip-existing without an additional yes/no confirmation

#### Scenario: User selects overwrite
- **WHEN** the user selects overwrite-existing
- **THEN** pending and already described processable images SHALL be selected for the common analysis and writeback pipeline

### Requirement: Guided results are written through the common pipeline
The guided command SHALL use the existing analysis, validation, cancellation, and Eagle write pipeline after policy selection.

#### Scenario: Policy selection starts processing
- **WHEN** the user selects a non-exit policy and model setup succeeds
- **THEN** successful results SHALL be written and the final summary SHALL report selected, changed, skipped, failed, and cancelled counts

### Requirement: Folder scanning is complete before statistics
The Eagle folder scan SHALL paginate through all available item pages, deduplicate the full result, and apply max-board-items limits only after complete collection.

#### Scenario: Folder crosses one page boundary
- **WHEN** a folder contains 1001 items and the API returns paginated pages
- **THEN** the scan SHALL collect all 1001 items before displaying statistics

#### Scenario: Folder exceeds the configured limit
- **WHEN** complete collection exceeds max-board-items
- **THEN** the command SHALL fail with an explicit size error and SHALL NOT present the result as a complete smaller scan
