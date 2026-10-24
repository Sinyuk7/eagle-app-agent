## 1. Shared Schema

- [x] 1.1 Add readable `default.json` and `editorial.json` Schema resources with concise descriptions, preserving the existing required fields, `additionalProperties: false`, `elements.minItems`, and Editorial confidence enum; load them through `moodtag_json_schema()`.
- [x] 1.2 Add or update schema tests for descriptions, profile-specific fields, required `suggest_title`, and rejection of missing or non-string title values.

## 2. Prompt Resources

- [x] 2.1 Rewrite the default system and user prompt resources to remove the JSON template, key-order instruction, and redundant raw-JSON/format rules while preserving visual analysis and searchable-field semantics.
- [x] 2.2 Rewrite the Editorial system and user prompt resources with concise evidence rules for visible facts, metadata, brands, commercial formats, and title preservation.
- [x] 2.3 Update prompt rendering tests to assert required semantic guidance remains and removed structural duplication is absent.

## 3. Mandatory Structured Outputs

- [x] 3.1 Remove No Response Format CLI flags, environment variable handling, default constant, help text, and provider constructor controls.
- [x] 3.2 Remove Remote Chat/Responses conditional Schema branches so both protocols always send their strict native Schema envelope.
- [x] 3.3 Update Ollama and Remote tests, mocks, and fixtures to cover mandatory shared Schema payloads and explicit unsupported-provider errors.
- [x] 3.4 Remove obsolete no-response-format tests and update documentation or snapshots that reference the deleted mode.

## 4. Cache-Safe Runtime Context

- [x] 4.1 Preserve stable-prefix versus per-image metadata separation for explicit Remote prompt caching while updating prompt assembly.
- [x] 4.2 Add a focused request-construction assertion that title and source URL do not enter the cacheable prefix.

## 5. Verification

- [x] 5.1 Run the affected unit tests for schemas, prompts, provider protocols, metadata safety, and CLI behavior.
- [x] 5.2 Run a small GPT-6.1 Remote smoke test with representative images and verify structured parsing, semantic fields, tags, and `suggest_title` behavior.
- [x] 5.3 Confirm the final diff stays within Prompt, Schema, response-format removal, tests, and required documentation updates.
