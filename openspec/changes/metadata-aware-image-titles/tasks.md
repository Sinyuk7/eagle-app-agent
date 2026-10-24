## 1. Analysis context and prompt rules

- [x] 1.1 Carry Eagle item URL alongside name through parsing and per-item analysis; pass both as bounded supplemental context to remote and Ollama providers in the user prompt.
- [x] 1.2 Refine only relevant default and editorial prompt rules for metadata hierarchy, field-specific evidence boundaries, and empty `suggest_title`; remove conflicting duplicate restrictions.
- [x] 1.3 Add prompt/provider tests proving per-item name and optional URL are supplied without URL fetching and both provider paths receive the same context.

## 2. Strict title response contract

- [x] 2.1 Add required `suggest_title` to both profile templates and JSON schemas, shared analysis result, and strict response normalization without a missing-field fallback.
- [x] 2.2 Update mocks, fixtures, and response tests for required string validation, valid empty values, and non-empty extension-free suggestions.
- [x] 2.3 Verify annotation formatting and legacy six-field annotation handling remain unchanged and never serialize suggestion or source metadata.

## 3. Safe Eagle V2 write

- [x] 3.1 Add conservative local title validation and carry the analyzed name, extension, and suggestion to the write boundary.
- [x] 3.2 Change only Eagle metadata update to `/api/v2/item/update`; conditionally include name with preserved extension when suggestion is valid and latest name still matches analyzed name.
- [x] 3.3 Keep tags and annotation writes proceeding when rename is skipped; verify dry run makes no writes and V2 payload omits `name` when not applicable.
- [x] 3.4 Run focused tests and the repository test suite; verify V2 success/error response handling and document any Eagle-version constraint.
