## ADDED Requirements

### Requirement: Catalog-driven remote setup
Interactive remote setup SHALL select a model from the catalog and derive its protocol without asking the user to choose Chat or Responses.

#### Scenario: Configure remote model
- **WHEN** the user selects Remote API and chooses a catalog model
- **THEN** the CLI SHALL request endpoint and hidden API key input using the model's derived protocol

### Requirement: Resume after setup
The workflow SHALL save valid model setup and return to the pending tagging task.

#### Scenario: Setup from tagging flow
- **WHEN** tagging reaches model readiness with no valid configuration and setup succeeds
- **THEN** the CLI SHALL preserve the resolved scope and strategy and continue to final confirmation

#### Scenario: Setup cancellation
- **WHEN** the user cancels model setup
- **THEN** the CLI SHALL leave configuration and Eagle metadata unchanged and return to the parent task
