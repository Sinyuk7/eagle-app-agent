## ADDED Requirements

### Requirement: Reproducible prompt and parameter evaluation
The project SHALL maintain a fixed, locally evaluated image benchmark with human-authored reference facts, acceptable variants, disallowed inferences, and taxonomy labels.

#### Scenario: Run a baseline evaluation
- **WHEN** the evaluator runs the benchmark for a prompt/schema/parameter revision
- **THEN** it records model and runtime identity, exact configuration revisions, structural validation, semantic metrics, taxonomy metrics, and latency without storing image bytes, secrets, prompt contents, raw responses, or full source paths

### Requirement: Controlled prompt and sampling experiments
Prompt, output template/schema, taxonomy, and model sampling changes SHALL be compared against a frozen baseline with one factor changed at a time before combination experiments.

#### Scenario: Compare prompt variants
- **WHEN** an experiment changes system prompt, profile user prompt, output field definition, or taxonomy guidance
- **THEN** it compares the same image set and model settings and reports defect categories and quality deltas

#### Scenario: Compare Qwen and Ollama parameter guidance
- **WHEN** an experiment evaluates sampling or thinking settings
- **THEN** it includes the official Qwen instruct recommendation, Ollama structured-output low-temperature baseline, and the selected runtime's reported defaults as separately labeled arms

### Requirement: Quality-driven prompt release
A prompt/schema/taxonomy/parameter revision SHALL become the default only after benchmark review demonstrates improvement without unacceptable regression in other dimensions.

#### Scenario: Candidate improves one dimension and regresses another
- **WHEN** a candidate improves tag accuracy but increases unsupported claims or materially worsens latency
- **THEN** the evaluator reports the tradeoff and the candidate is not silently promoted as an overall improvement

#### Scenario: Provider or model version changes
- **WHEN** Ollama, model digest, runner, prompt, schema, or taxonomy changes
- **THEN** the benchmark can rerun the same local image IDs and compare the new result to the stored baseline
