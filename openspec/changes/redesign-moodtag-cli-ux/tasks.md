## 1. Safety and Regression Baseline

- [ ] 1.1 Restore coverage removed during single-provider refactor for board resolution, scope limits, write safety, retries, concurrency, run logs, and interruption.
- [ ] 1.2 Convert provider/configuration `CoreError` values into user-facing CLI errors so invalid input never prints a traceback.
- [ ] 1.3 Define stable result records, exit codes, and error fields for human and `--json` execution paths.

## 2. UI Foundation

- [ ] 2.1 Add runtime dependencies `alive-progress` and `yaspin`; verify package, installer, and plain-terminal compatibility.
- [ ] 2.2 Create `moodtag/ui/ansi.py` with TTY, `NO_COLOR`, `TERM=dumb`, `--plain`, width, clear-line, and cursor capability helpers.
- [ ] 2.3 Create `moodtag/ui/printer.py` so all human UI and errors use semantic stderr output instead of scattered `print()` calls.
- [ ] 2.4 Create `moodtag/ui/spinner.py` as a yaspin adapter for unknown-duration preparation and write waits.
- [ ] 2.5 Create `moodtag/ui/progress.py` as an alive-progress adapter for known-total analysis/write progress, recent completion text, ETA, and FPS.
- [ ] 2.6 Create `moodtag/ui/menu.py` for numbered choices, back, quit, invalid input retry, and Ctrl-C handling.
- [ ] 2.7 Add a session coordinator that owns renderer lifecycles and prevents concurrent spinner/progress/line output.

## 3. Workflow-first Navigation

- [ ] 3.1 Route no-argument TTY startup to a status-first Moodtag home screen before argparse.
- [ ] 3.2 Render home state with welcome text, AI readiness, persisted profile, workflow actions, and no provider/model internals by default.
- [ ] 3.3 Preserve known advanced commands, global help, and explicit flags through argparse.
- [ ] 3.4 Add conservative direct-board candidate classification while keeping Eagle resolver authority and recoverable ambiguity selection.
- [ ] 3.5 Return an actionable no-argument error in non-TTY mode without reading stdin or contacting Eagle.
- [ ] 3.6 Implement profile selection workflow, persistence, one-run `--profile` override, and return to the home screen.

## 4. Human Tagging Workflow

- [ ] 4.1 Replace technical preflight text with natural-language “将分析” confirmation showing board, total, selected, completed, profile, AI readiness, and overwrite consequence.
- [ ] 4.2 Remove confirmation as active focus after acceptance; render one current workflow state at a time with line/region fallback.
- [ ] 4.3 Keep first-image model probe before bulk work and surface failures as concise actionable UI.
- [ ] 4.4 Separate execution into preparation, concurrent analysis, write, and completion phases while preserving per-item correctness.
- [ ] 4.5 Show `○` wait, `…` active, `✓` success, `!` warning/skip, `×` failure, and `→` next consistently across all UI.
- [ ] 4.6 Show analysis/write progress with completed/selected, recent 2-3 item outcomes, conservative ETA/FPS, and small-terminal fallback.
- [ ] 4.7 Implement first Ctrl-C cooperative cancellation, second Ctrl-C fast exit, and partial-write/unfinished summaries without tracebacks.

## 5. Output Contract and Detail Levels

- [ ] 5.1 Route UI, progress, verbose records, diagnostics, and errors to stderr; reserve stdout for machine data.
- [ ] 5.2 Implement `--json` final-result output with no ANSI, spinner, progress, or human logs on stdout.
- [ ] 5.3 Implement `-q`, default, `-v`, and `-vv` levels with exact content boundaries and no sensitive output at any level.
- [ ] 5.4 Ensure `-vv` may expose endpoint/model/retry/timing but never keys, headers, prompts, image data, or raw model response.
- [ ] 5.5 Disable animation and ANSI for non-TTY, `NO_COLOR`, `TERM=dumb`, and `--plain`; retain readable line-oriented state.

## 6. Model Catalog and Configuration Workflow

- [ ] 6.1 Add packaged `chat.json` and `responses.json` model resources, package-data declarations, and schema validation.
- [ ] 6.2 Populate Chat with `qwen3.5-122b-a10b`; populate Responses with recommended `gpt-5.6-luna` and `gpt-5.6-terra`.
- [ ] 6.3 Implement catalog loader, unique-ID validation, recommended marker validation, and model-to-protocol derivation.
- [ ] 6.4 Replace free-text protocol/model setup with category selection, catalog model selection, URL entry, hidden key entry/retention, redacted confirmation, and atomic persistence.
- [ ] 6.5 Persist `base_url`, `model`, `profile`, and existing Eagle settings in JSON; persist only the secret key in owner-only `.env`.
- [ ] 6.6 Remove protocol persistence and deprecated provider environment overrides, flags, free-text prompts, documentation, examples, and tests.
- [ ] 6.7 Delete deprecated provider configuration support, environment overrides, commands, tests, examples, and documentation; reject unknown catalog models and mark a temporary API-key override source without exposing secret content.
- [ ] 6.8 Implement `moodtag config`, `config profile`, `config model`, and safe interactive `config reset`; retire `config set/get/unset` user workflows.

## 7. Verification and Documentation

- [ ] 7.1 Add pseudo-TTY tests for home state, menu navigation, spinner/progress transitions, focus replacement, plain fallback, and cancellation.
- [ ] 7.2 Add stdout/stderr and JSON tests for every quiet level, error path, ANSI-disabled state, and pipe safety.
- [ ] 7.3 Add catalog/configuration tests for both resources, mappings, URL validation, key retention, clean beta contract, cleanup, and secret redaction.
- [ ] 7.4 Add phase tests for probe failure, concurrent analysis, streaming recent outcomes, write phase, partial cancellation, and final counts.
- [ ] 7.5 Extend live protocol matrix coverage for every catalog model and verify image input plus structured JSON output.
- [ ] 7.6 Update README, help, `.env.example`, CONTRIBUTING, and installer smoke tests with workflow UI, output contract, quiet levels, catalog setup, and removed settings; document only the current beta contract.
- [ ] 7.7 Run formatting, full tests, TTY/non-TTY smoke tests, package/install checks, live matrix, and `openspec status --change redesign-moodtag-cli-ux --json`.
