## Context

The current workflow is implemented as nested functions in `moodtag/cli.py`. It already supports home navigation, direct board routing, folder/selection/library scopes, named model profiles, and a shared tagging executor. The refactor should reduce prompts without creating a new TUI or changing provider behavior.

## Goals / Non-Goals

**Goals:**

- Make the guided flow state-aware and preserve its in-memory `argparse.Namespace` while model setup runs.
- Make the default action safe and obvious, while requiring explicit confirmation for regeneration.
- Validate expensive library scope queries before downloading all item metadata when the Eagle API exposes a count.
- Keep interactive and non-interactive entry points on the same scan, strategy, confirm, analyze, and write semantics.

**Non-Goals:**

- No new image source, settings area, provider, protocol, prompt, taxonomy, or metadata behavior.
- No automatic browser launch, model download, or remote fallback.

## Decisions

1. `_command_guided_tag_v2` remains the workflow coordinator. It computes item status first and only calls `choose()` when there are at least two meaningful strategies.
2. `_setup_prompt` accepts the active configuration and returns saved values without a second save confirmation. The caller persists once and resumes the same namespace.
3. Remote model protocol is derived from `protocol_for_model(model)` after catalog selection. Users still enter endpoint and hidden API key.
4. Home reads configuration only. Ollama readiness is checked when tagging starts, not during menu rendering.
5. Scope resolution may perform a count-first request for whole-library queries. If the count exceeds the configured limit, it returns a recoverable error before item pagination.
6. Existing numeric menus and `b`/`q` shortcuts remain supported; menu wording and branch count change without introducing a full-screen renderer.

## Risks / Trade-offs

- [Eagle deployments omit a total count] → retain the existing bounded pagination path and enforce the limit while collecting items.
- [Auto-saving setup could surprise users] → show a redacted configuration summary and save only after all required fields validate.
- [A resumed task may hold stale Eagle state] → resolve and snapshot scope before setup; setup never re-queries or changes the selected items.
- [Home no longer reports live Ollama health] → report actionable health errors during preparation and keep explicit `config show` diagnostics.

## Migration Plan

Implement behind the existing guided flow, update focused tests, run the full suite, and retain the old command paths for automation. No configuration migration is required.
