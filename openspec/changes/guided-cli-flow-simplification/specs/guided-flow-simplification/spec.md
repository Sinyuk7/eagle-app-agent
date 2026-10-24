## ADDED Requirements

### Requirement: State-aware strategy selection
The guided workflow SHALL skip a processing-strategy prompt when exactly one safe strategy is available.

#### Scenario: All images pending
- **WHEN** every supported image is pending analysis
- **THEN** the workflow SHALL proceed directly to model readiness and final confirmation

#### Scenario: Partial completion
- **WHEN** both pending and already analyzed images exist
- **THEN** the workflow SHALL offer pending-only and regenerate-all strategies

#### Scenario: All images analyzed
- **WHEN** no image is pending and all existing analyses are valid
- **THEN** the workflow SHALL require an explicit regenerate-all choice before processing

### Requirement: Single execution confirmation
The workflow SHALL present one confirmation immediately before analysis and writing.

#### Scenario: Normal analysis
- **WHEN** pending images are selected
- **THEN** Enter SHALL accept the normal start default

#### Scenario: Regeneration
- **WHEN** all images are selected for regeneration
- **THEN** the confirmation SHALL identify regeneration and require an explicit affirmative response
