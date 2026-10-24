## 1. Guided flow

- [x] 1.1 Refactor strategy selection to skip single-option prompts and distinguish malformed/unsupported items.
- [x] 1.2 Make regeneration confirmation explicit and retain one final execution confirmation.
- [x] 1.3 Simplify folder ambiguity and empty-selection recovery while preserving `b`/`q` shortcuts.

## 2. Model setup

- [x] 2.1 Remove the Remote API protocol prompt and derive protocol from the selected catalog model.
- [x] 2.2 Add defaults for existing endpoint and Ollama URL, reuse existing API keys when valid, and save without duplicate confirmation.
- [x] 2.3 Resume the active tagging namespace after setup or cancellation without returning to the home menu.

## 3. Scope and home behavior

- [x] 3.1 Add count-first whole-library guard with bounded-pagination fallback.
- [x] 3.2 Remove active Ollama health probing from home rendering.
- [x] 3.3 Update non-interactive hints and documentation for all supported entry points.

## 4. Verification

- [x] 4.1 Update focused workflow and setup tests for the new branches.
- [x] 4.2 Run the full test suite and lint checks.
