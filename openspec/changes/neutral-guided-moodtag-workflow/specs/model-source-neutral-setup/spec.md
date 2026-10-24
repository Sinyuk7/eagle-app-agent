## ADDED Requirements

### Requirement: Remote API and local Ollama are equal first-class sources
The first model setup SHALL present Remote API and local Ollama with equal capability status and symmetric trade-off descriptions.

#### Scenario: No valid model configuration exists
- **WHEN** the user selects a processing policy and no valid saved or explicit model configuration exists
- **THEN** the source menu SHALL offer Remote API and local Ollama without calling either source a preferred, fallback, or safer default

#### Scenario: A valid configuration exists
- **WHEN** a valid local or remote configuration is already available
- **THEN** the command SHALL use it without reopening source selection

### Requirement: Remote setup collects only remote requirements
Remote setup SHALL collect endpoint, model, and API key when required by the selected service and SHALL persist the configuration only after explicit user confirmation.

#### Scenario: User selects Remote API
- **WHEN** the user chooses Remote API
- **THEN** setup SHALL explain possible service charges and remote image transfer, validate the endpoint and model, and store the confirmed configuration

### Requirement: Ollama readiness requires an installed vision model
Local setup SHALL distinguish a reachable Ollama service from an installed vision-capable model.

#### Scenario: Ollama has no vision model
- **WHEN** the Ollama service is reachable but discovery finds no installed model advertising vision capability
- **THEN** setup SHALL explain that a compatible model must be installed and SHALL NOT download a model or silently switch to Remote API

#### Scenario: Local request fails
- **WHEN** an Ollama analysis request fails
- **THEN** the command SHALL report the local failure and SHALL NOT send the image to a remote provider automatically

### Requirement: Both sources use the same task capabilities
The system SHALL provide image analysis, tag generation, annotation writeback, and batch processing through the same task contract for both sources.

#### Scenario: User selects either source
- **WHEN** a valid Remote API or Ollama configuration is selected
- **THEN** the policy-selected images SHALL enter the same analysis and writeback pipeline without source-specific feature removal
