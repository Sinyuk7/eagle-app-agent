## ADDED Requirements

### Requirement: Ollama native vision analysis
The system SHALL analyze images through the configured local Ollama service using the native chat API, native image input, and a JSON Schema derived from the Moodtag output contract.

#### Scenario: Analyze with a discovered vision model
- **WHEN** the user selects an installed Ollama model whose capabilities include vision
- **THEN** the system sends the image and rendered Moodtag profile prompts to the native chat endpoint and validates both the schema and Moodtag business contract

#### Scenario: Tags response omits capabilities
- **WHEN** `/api/tags` lists an installed model without a capabilities field
- **THEN** setup calls `/api/show` and uses its capabilities; it MUST NOT infer vision support from the model name

#### Scenario: Selected model lacks vision capability
- **WHEN** the selected Ollama model does not advertise vision support
- **THEN** setup MUST reject it for image annotation and explain that a vision-capable model is required

#### Scenario: Ollama unavailable
- **WHEN** the local Ollama endpoint cannot be reached for an analysis task
- **THEN** on supported macOS the CLI attempts to launch the installed Ollama.app once and waits for readiness within a bounded timeout; if unavailable afterward, it reports actionable service/model setup steps and MUST NOT silently route the image to a remote provider

#### Scenario: Ollama is already running
- **WHEN** the local Ollama API is reachable at task preflight
- **THEN** the CLI reuses the running service without launching another instance

#### Scenario: Ollama app is missing or startup times out
- **WHEN** macOS cannot find or launch Ollama.app, or its API does not become ready before the timeout
- **THEN** the CLI fails with manual installation/start instructions and does not install Ollama, pull a model, close another process, or switch providers

#### Scenario: Service becomes ready
- **WHEN** Ollama.app starts successfully and the API becomes ready
- **THEN** the CLI continues the original task, validates the selected model, and lets Ollama load the model on the first inference request

### Requirement: Local-only image flow
The system SHALL distinguish a loopback HTTP endpoint from confirmed local inference and preserve the declared image destination throughout analysis.

#### Scenario: Use local provider
- **WHEN** an analysis uses an Ollama endpoint configured as local
- **THEN** the endpoint is loopback, the selected model is not identified as cloud/remote, available remote-host signals are checked, and only then may the execution summary identify local processing

#### Scenario: Loopback service runs a cloud-backed model
- **WHEN** localhost Ollama identifies the selected model as remote/cloud or response metadata identifies a remote model/host
- **THEN** the system rejects local-only mode and MUST NOT label the request as local processing

#### Scenario: Locality cannot be confirmed
- **WHEN** model locality is unknown from available service metadata
- **THEN** the system MUST NOT claim local-only processing and asks the user to configure a verifiable local model

#### Scenario: Optional server-side cloud disablement
- **WHEN** the user needs additional protection against Ollama cloud routing
- **THEN** setup may explain Ollama's `OLLAMA_NO_CLOUD=1` or `disable_ollama_cloud` setting, while clearly stating Moodtag cannot enforce or verify that server configuration

#### Scenario: Provider request fails
- **WHEN** a local request fails or returns invalid output
- **THEN** retries remain on the same local provider and no remote fallback occurs

### Requirement: Model/runtime-aware request controls
The system SHALL expose and record supported thinking and sampling options for Ollama requests instead of relying on undocumented defaults.

#### Scenario: Inspect selected model capabilities
- **WHEN** setup probes an Ollama model
- **THEN** it reads supported capabilities and model-defined thinking options from `/api/show`, while runner may remain unknown until runtime inspection

#### Scenario: Execute with named parameter preset
- **WHEN** analysis starts with an Ollama preset
- **THEN** all benchmarked request parameters are sent explicitly and the evaluation record identifies model digest, Ollama version, runner or unknown, preset, model context capacity, requested `num_ctx`, `num_predict`, `prompt_eval_count`, and stage/end-to-end timings

#### Scenario: Complex schema compatibility evaluation
- **WHEN** a release candidate changes Ollama, MLX runner, model digest, or Moodtag schema
- **THEN** the opt-in live evaluation repeats the final nested schema with supported thinking modes, low-information images, output limits, timeout cases, and premature/blank response checks
