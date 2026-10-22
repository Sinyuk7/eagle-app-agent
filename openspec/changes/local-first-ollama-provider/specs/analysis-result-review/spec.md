## ADDED Requirements

### Requirement: Deterministic result assembly
The system SHALL convert validated model output through Moodtag normalization, taxonomy reconciliation, and annotation assembly before any Eagle write.

#### Scenario: Valid structured response
- **WHEN** a provider returns a response that passes schema and business validation
- **THEN** the application creates one normalized Moodtag analysis result and builds Eagle tags/annotation from application rules

#### Scenario: Invalid or incomplete response
- **WHEN** a model response fails schema or business validation
- **THEN** it is rejected or retried within a configured bound and no Eagle write is performed for that item

### Requirement: Review before write in guided workflow
The guided workflow SHALL make generated descriptions and tags reviewable before they are committed to Eagle.

#### Scenario: Preview generated analysis
- **WHEN** analysis completes for the selected scope
- **THEN** the user can inspect and edit or reject generated annotations and tags before confirming the existing Eagle write step
