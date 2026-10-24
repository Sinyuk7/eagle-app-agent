## Context

The analysis pipeline currently passes a prepared image and taxonomy into provider `analyze()` methods. Eagle items already carry `name`, while source URL needs to be retained from the item payload. Prompt rendering currently produces profile-specific static user text. The shared `MoodtagAnalysis` and JSON schemas define profile output; annotation serialization deliberately uses a fixed field list. Eagle's current metadata write uses V1 `/api/item/update`, which does not support changing item names, while V2 `/api/v2/item/update` supports `name`, `tags`, and `annotation`.

The change is intentionally narrow: one model invocation per image, both profiles use the new strict field, only the update endpoint moves to V2, and no unrelated provider, CLI, taxonomy, or Eagle API redesign is included.

## Goals / Non-Goals

**Goals:**
- Supply per-item name and optional source URL in user prompt context for every provider.
- Establish a strict `suggest_title` response contract in both profiles, where empty means preserve and non-empty means a replacement title without extension.
- Let metadata help contextual interpretation while maintaining visual evidence boundaries.
- Safely apply valid rename suggestions with the existing metadata write, preserving extension and user edits made during analysis.
- Keep suggestion and source metadata out of annotation text.

**Non-Goals:**
- Fetching or scraping source URLs, changing taxonomy, introducing evidence scores, adding CLI flags, or adding a second model call.
- Migrating `item_info` or other Eagle API endpoints to V2.
- Adding legacy-response fallback for missing `suggest_title`.
- Renaming already-completed items independently of the existing skip/force analysis flow.

## Decisions

### Pass item metadata through the existing analysis call

Extend the per-item analysis path and provider `analyze()` contract with the original name and optional URL, then render a small dynamic metadata block in the user message alongside the image. Keep stable evidence hierarchy and output instructions in each profile's system/user prompt resources; metadata values belong only in the per-image user input. Omit an absent URL. Treat title and URL as untrusted context, do not fetch links, and bound/sanitize context before sending it to providers, including removing URL query credentials or sensitive query data.

Alternative: put dynamic values in system prompts. Rejected because they vary per image and are context, not durable model policy.

### Make `suggest_title` a required shared output field

Add `suggest_title` to both profile JSON templates and schemas and to `MoodtagAnalysis`; validate it as a string with no fallback for a missing value. Empty string is valid and means preserve the current title. Update mocks, fixtures, and tests to emit the field. Keep it outside `ANNOTATION_FIELDS` and annotation labels so it cannot appear in Eagle descriptions.

Alternative: default missing responses to empty for backward compatibility. Rejected because this is an intentional output-contract upgrade and the user explicitly wants strict validation.

### Keep contextual and visual evidence distinct

Refine only the relevant prompt rules. Image content remains primary; metadata may inform contextual interpretation and support `probable` commercial format confidence when consistent with the image. `visible_text` and `brand_evidence` remain pixel-grounded, and `confirmed` format confidence requires clear visual evidence. Remove or revise conflicting repetitions rather than appending a contradictory rule. The general non-empty analytical-field rule must explicitly exempt `suggest_title`, whose empty string is meaningful.

Alternative: make all fields strictly visual-only. Rejected because it discards useful title/source context. Alternative: accept metadata as proof. Rejected because it would turn contextual claims into unsupported visual evidence.

### Rename conditionally in the existing V2 metadata update

Carry the analyzed original name, extension, and suggestion to the existing write boundary. Re-read latest item metadata as today. Include a sanitized suggested title plus the original extension as `name` only if the suggestion is non-empty and valid and the latest name still equals the analyzed name; otherwise omit `name` but continue valid tag and annotation writes. Use `/api/v2/item/update` for this write and include only fields intended for update. Do not claim transaction-level atomicity beyond the API's single-request behavior.

Alternative: make a separate rename request. Rejected because it can leave name and analysis metadata partially updated and adds a request. Alternative: migrate every Eagle endpoint. Rejected as unrelated scope.

Title validation should be conservative and narrow: trim surrounding whitespace, reject control characters and path separators/unsupported filename characters, enforce a practical maximum length, and reject empty-after-cleanup values. It should not scan the library for duplicate names or invent a collision policy.

## Risks / Trade-offs

- Metadata can bias the model or contain prompt-like text → label it as unverified data, bound it, keep image evidence primary, and never let it establish visible text or brand evidence.
- URL query strings may contain secrets → remove sensitive query parameters or omit the URL when it cannot be safely reduced.
- V2 response behavior may differ from V1 → verify the actual success/error response in focused tests and preserve the CLI's existing error handling.
- A model can suggest a poor or unsafe title → validate locally; skip only the rename while preserving valid tag/annotation writes.
- Eagle may not provide transaction guarantees → perform name, tags, and annotation in one V2 request and report API failures normally.

## Migration Plan

No stored-data migration is required. Update prompt/schema fixtures and mocks as part of the strict contract change. Existing six-field annotations remain unchanged. Deploy the V2 update endpoint change with tests for rename and non-rename requests; rollback consists of reverting the code change (renames already applied in Eagle remain ordinary user metadata and are not automatically reversed).

## Open Questions

None. The Eagle V2 `name` and `ext` separation and V2 update support are established by the supplied API review; implementation should still verify request/response behavior against the repository's expected Eagle API version (4.0 Build 21 or later).
