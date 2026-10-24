## ADDED Requirements

### Requirement: Shared schema contract
Moodtag SHALL expose one profile-aware JSON Schema contract shared by Remote Chat, Remote Responses, and Ollama providers.

#### Scenario: Provider payloads use the shared schema
- **WHEN** a request is built for any supported provider and either `default` or `editorial` profile
- **THEN** the provider payload contains the schema generated for that profile using its native structured-output transport

#### Scenario: Schema descriptions explain semantic fields
- **WHEN** the schema is generated
- **THEN** fields including `elements`, `key`, `suggest_title`, and Editorial `commercial_format_confidence` contain concise descriptions that explain their intended meaning

### Requirement: Profile prompts preserve analysis semantics without duplicate structure instructions
The four profile prompt resources SHALL retain visual evidence, metadata, searchability, brand, commercial-format, and title-preservation rules while removing duplicated JSON templates, key-order requirements, and redundant format/type instructions.

#### Scenario: Default profile prompt is concise
- **WHEN** the default profile prompt is rendered
- **THEN** it provides the analysis task, semantic field guidance, taxonomy, and use intents without embedding the complete JSON template or repeating schema-enforced formatting rules

#### Scenario: Editorial evidence rules remain explicit
- **WHEN** the editorial profile prompt is rendered
- **THEN** it distinguishes pixel-visible facts from metadata context and preserves rules for brand evidence, commercial format confidence, visible text, searchable elements, and `suggest_title`

### Requirement: Schema-constrained output is mandatory
Moodtag SHALL require structured Schema output for every supported provider request and SHALL NOT expose a JSON Object or prompt-only fallback mode.

#### Scenario: Legacy response-format controls are removed
- **WHEN** CLI help, environment configuration, or provider construction is inspected
- **THEN** No Response Format flags, environment variables, constants, switches, and conditional branches are absent

#### Scenario: Unsupported structured output fails explicitly
- **WHEN** a provider cannot accept its native Schema transport
- **THEN** the request fails with an explicit error and does not silently downgrade to JSON Object or prompt-only parsing

### Requirement: Per-image metadata remains cache-safe
Original title and sanitized source URL SHALL be supplied as per-image supplemental context after stable cacheable prompt instructions.

#### Scenario: Explicit prompt cache request
- **WHEN** a Remote request uses explicit prompt caching
- **THEN** system/profile instructions and taxonomy remain in the stable prefix while title, source URL, and image are placed in the per-image user message

### Requirement: Suggest title remains strict
`suggest_title` SHALL be required and typed as a string for both profiles; an empty string SHALL mean that the existing title is preserved.

#### Scenario: Invalid title field is rejected
- **WHEN** a response omits `suggest_title` or supplies a non-string value
- **THEN** response validation fails clearly rather than silently supplying a default
