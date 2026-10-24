## ADDED Requirements

### Requirement: Remote requests use strict structured output

Every supported Remote model SHALL request the existing Moodtag output contract as a strict JSON Schema. Responses requests SHALL use `text.format`; Chat Completions requests SHALL use `response_format`. The provider SHALL report incompatibility when strict schema is rejected and SHALL NOT silently downgrade to JSON Object mode.

#### Scenario: Responses strict schema payload

- **WHEN** a supported Responses model request is built
- **THEN** the payload SHALL contain `text.format.type=json_schema`, a stable schema name, `strict=true`, and the existing Moodtag schema

#### Scenario: Chat strict schema payload

- **WHEN** a supported Chat Completions model request is built
- **THEN** the payload SHALL contain `response_format.type=json_schema`, a stable schema name, `strict=true`, and the existing Moodtag schema

#### Scenario: Strict schema incompatibility

- **WHEN** the provider rejects the strict schema request as unsupported
- **THEN** the Remote client SHALL report an incompatibility error and SHALL NOT retry the request as JSON Object mode

### Requirement: GPT-6.1 Sol uses the agreed low-cost request defaults

The GPT-6.1 Sol Responses payload SHALL set `store=false` and `reasoning.effort=low`, use image detail `auto`, and omit `temperature`, `top_p`, and `max_output_tokens) by default.

#### Scenario: GPT-6.1 Sol payload

- **WHEN** a GPT-6.1 Sol request is built with default Remote settings
- **THEN** the payload SHALL include low reasoning, disabled storage, and auto image detail, and SHALL omit sampling and output-token-limit fields

### Requirement: Explicit prompt caching is capability gated

The model catalog SHALL expose `explicit_prompt_cache`. Only entries with that capability SHALL receive explicit prompt-cache options with a 30-minute TTL and a breakpoint at the end of the stable Developer prompt and taxonomy prefix.

#### Scenario: Catalog-enabled prompt cache

- **WHEN** a Remote model has `explicit_prompt_cache=true`
- **THEN** the request SHALL contain explicit cache mode, a 30-minute TTL, and one breakpoint on the stable Developer prompt prefix

#### Scenario: Custom endpoint without capability

- **WHEN** a model or custom endpoint does not declare `explicit_prompt_cache`
- **THEN** the request SHALL omit prompt-cache options and cache breakpoints

#### Scenario: Image remains outside cache prefix

- **WHEN** a cache-enabled image request is built
- **THEN** the image and per-image user content SHALL be placed after the stable cacheable Developer prefix

### Requirement: Remote payload policy preserves domain inputs

The Remote policy SHALL reuse the existing Prompt, Taxonomy, output schema, and JPEG data-URL image path without modifying `MoodtagAnalysis` or Eagle writeback data.

#### Scenario: Existing taxonomy and prompt

- **WHEN** a Remote analysis request is built
- **THEN** the current profile Prompt and Taxonomy content SHALL be used without reordering or redesigning the business contract
