## Context

Moodtag has two semantic profiles, each represented by a system and user prompt. The providers already share `moodtag_json_schema(profile)` but transport it through different API envelopes. The current prompts repeat JSON shape and formatting instructions that the structured-output contract can enforce. The runtime also has a schema-disabled branch that is no longer part of the supported product behavior.

## Goals / Non-Goals

**Goals:**

- Make the shared Schema the single machine-readable output contract.
- Keep profile-specific visual-analysis guidance concise and semantically complete.
- Require schema-constrained output for every provider request.
- Preserve cache-safe separation of stable prompt content and per-image metadata.
- Validate the existing GPT-6.1 Remote path with current unit tests and a small manual smoke test.

**Non-Goals:**

- No provider- or model-specific prompt fork.
- No taxonomy architecture change or dynamic Schema enums for taxonomy values.
- No new benchmark, scoring framework, multi-model A/B infrastructure, or unrelated module refactor.
- No JSON Object or prompt-only fallback mode.

## Decisions

1. **Schema owns structure, descriptions own concise field meaning.** Keep the current required fields, `additionalProperties: false`, `elements.minItems`, and Editorial confidence enum. Add short descriptions for fields whose meaning is easy to misinterpret, especially `elements`, `key`, `suggest_title`, and `commercial_format_confidence`. Do not add broad pattern, length, or dynamic enum constraints.

2. **Prompts own visual semantics.** Keep four resources and two profiles. Remove full JSON templates, key-order instructions, raw-JSON/Markdown repetition, and duplicated type explanations. Retain evidence priority, metadata limits, searchable element rules, brand/logo evidence, commercial-format qualification, language style, and title-preservation behavior.

3. **Structured outputs are mandatory.** Remove `--no-response-format`, `--response-format`, `MOODTAG_NO_RESPONSE_FORMAT`, the default constant, constructor switches, and provider conditionals. Remote Chat and Responses continue using their native strict JSON Schema envelopes; Ollama continues using `format` with the shared schema. Unsupported providers fail explicitly.

4. **Per-image context stays after cacheable instructions.** System prompt, profile prompt, taxonomy, and use intents remain in the stable prefix. Original title and sanitized source URL remain in the per-image user message so explicit prompt caching is reusable across images.

5. **Validation remains layered.** Keep provider response parsing and Ollama schema validation. Require `suggest_title` as a string everywhere; empty string is valid and means preserve the existing name. Do not add compatibility defaults for missing fields.

## Risks / Trade-offs

- [Semantic regression from over-compression] → Preserve the current high-value rules in shorter wording and run existing prompt/provider tests plus GPT-6.1 smoke requests.
- [CLI/config breakage] → Remove flags and environment handling together, update help text/tests, and document the breaking change.
- [Provider schema incompatibility] → Keep provider-specific envelopes and assert all three payloads carry the shared schema; surface unsupported structured output as an error.
- [Qwen/Ollama quality may differ] → Keep one shared prompt initially; address model-specific quality only after a concrete future failure.
- [Cache regression] → Add/request-test stable-prefix and per-image-context placement while changing prompt rendering.
