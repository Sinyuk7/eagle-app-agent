## Why

Moodtag currently repeats output-format instructions and field semantics across four profile prompts even though Remote Chat, Responses, and Ollama already share a structured JSON Schema contract. This duplication increases maintenance cost and makes prompt behavior harder to reason about, while the Schema itself lacks useful field descriptions.

## What Changes

- Add concise, meaningful descriptions to the shared default/editorial JSON Schemas.
- Keep `default` and `editorial` as the only prompt profiles; do not create provider- or model-specific prompts.
- Remove repeated JSON templates, key-order requirements, Markdown/raw-JSON instructions, and redundant structural field explanations from the four prompt resources.
- Preserve concise semantic rules for visible evidence, metadata boundaries, searchable elements, brand evidence, commercial format, and `suggest_title`.
- Keep Remote Chat, Responses, and Ollama on their provider-specific structured-output transports using the shared Schema.
- **BREAKING** Remove all No Response Format CLI options, environment variables, constructor controls, conditional branches, and related tests; do not provide JSON Object or prompt-only fallback.
- Keep `suggest_title` required as a string; an empty string means preserve the existing title, and missing or incorrectly typed values remain invalid.
- Preserve explicit prompt-cache separation between stable instructions and per-image metadata.

## Capabilities

### New Capabilities

- `schema-prompt-contract`: Defines the shared structured-output contract and the responsibilities of Schema, profile prompts, runtime context, and provider adapters.

### Modified Capabilities

- None.

## Impact

Affected areas include `moodtag_core/schema.py`, `contract.py`, `prompts.py`, the four prompt resource files, Remote and Ollama provider request construction, CLI configuration, and tests/fixtures covering response-format options and provider payloads. GPT-6.1 Remote API is the primary manual smoke-test target. No new benchmark or evaluation infrastructure is introduced.
