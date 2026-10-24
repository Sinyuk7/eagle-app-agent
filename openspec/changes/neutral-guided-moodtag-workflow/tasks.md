## 1. Board-first guided workflow

- [x] 1.1 Refactor the ordinary folder command to connect to Eagle and load board scope before calling model setup.
- [x] 1.2 Add stable board statistics for total images, existing Moodtag descriptions, pending processable images, unsupported media, and child-folder count.
- [x] 1.3 Add the policy menu with skip-existing, overwrite-existing, and exit; make empty input select skip-existing.
- [x] 1.4 Ensure exit performs no provider initialization, credential prompt, model request, or Eagle update.
- [x] 1.5 Rename overwrite UI to regenerate AI description and tags, while documenting additive tag semantics.
- [x] 1.6 Route policy-selected items through the common analysis and writeback path, including cancellation and final counts.
- [x] 1.7 Add tests for summary-before-setup ordering, Enter default, skip/overwrite behavior, exit no-op, and interruption.

## 2. Model-source-neutral setup

- [x] 2.1 Replace local-first setup copy and ordering with a symmetric Remote API/Ollama source menu.
- [x] 2.2 Reuse valid saved local or remote configuration without reopening setup; persist new configuration only after explicit confirmation.
- [x] 2.3 Validate Remote API endpoint/model/key requirements and clearly state possible cost and remote image transfer.
- [x] 2.4 Validate Ollama service reachability and installed vision capability separately; never auto-download models or fall back silently to Remote API.
- [x] 2.5 Re-evaluate the Ollama concurrency guard so product behavior and documentation do not claim local-only serial processing; retain only verified provider limits.
- [x] 2.6 Add model-source parity tests covering both sources, no-config setup, existing config reuse, missing Ollama model, and local failure without fallback.

## 3. Metadata-safe Eagle writeback

- [x] 3.1 Change Eagle update adapter to accept optional tags and annotation fields and omit fields not being changed.
- [x] 3.2 Add stable de-duplicating merge of existing tags and generated AI tags.
- [x] 3.3 Use replace_analysis_annotation for generated notes so manual annotation content survives first write and regeneration.
- [x] 3.4 Change reset to remove only Moodtag annotation content and never send tags=[]; hide destructive legacy behavior from ordinary help.
- [x] 3.5 Add a missing/valid/malformed status classifier with explicit bounded Moodtag markers and safe legacy parsing.
- [x] 3.6 Refresh item_info immediately before every write, recheck skip status, and handle concurrent user edits safely.
- [x] 3.7 Add regression tests for manual tags, manual notes, existing Moodtag blocks, first generation, regeneration, malformed legacy blocks, latest metadata refresh, and reset.

## 4. Complete Eagle scanning and advanced CLI contract

- [x] 4.1 Implement V2/V1 pagination using total, offset, limit, and data metadata; deduplicate only after complete collection.
- [x] 4.2 Add tests for 1000, 1001, and over-limit folder sizes, and reject unverifiable/truncated scans.

## 5. Advanced CLI and output contract

- [x] 5.1 Preserve advanced tag controls for write, force, limit, max-board-items, dry-run, concurrency, and JSON automation.
- [x] 5.2 Separate ordinary folder help from advanced tag help; remove internal flags from the ordinary product explanation.
- [x] 5.3 Keep guided menus, progress, and diagnostics on stderr and JSON results only on stdout.
- [x] 5.4 Add non-TTY guidance that points automation to the advanced command without guessing a write policy.
- [x] 5.5 Add tests for TTY/non-TTY behavior, stdout/stderr separation, JSON output, and advanced compatibility.

## 6. Documentation information architecture

- [x] 6.1 Rewrite README around installation, Eagle folder selection, policy choices, model-source trade-offs, generated descriptions, and existing metadata safety.
- [x] 6.2 Remove local-first, Ollama-primary, fallback, and absolute cost/performance claims from README and user-facing help.
- [x] 6.3 Add docs/getting-started.md and docs/model-setup.md for beginner workflow and source configuration details.
- [x] 6.4 Add docs/cli-reference.md for advanced flags and automation, docs/architecture.md for internals, and docs/benchmarks.md for measured performance.
- [x] 6.5 Move moodboard layout and body-design material into docs/moodboard.md and link to it from README.
- [x] 6.6 Correct macOS Gatekeeper instructions and keep the ordinary installation path limited to the GitHub install command.
- [x] 6.7 Add documentation smoke checks for forbidden local-first wording and accidental sampling/endpoint/benchmark leakage in README.

## 7. Verification and rollout

- [x] 7.1 Run targeted guided-flow, model-source, metadata-safety, provider-parity, and output-contract tests.
- [x] 7.2 Run the full project test suite and update tests whose expectations intentionally change.
- [x] 7.3 Review logs and errors for API key, prompt, image, endpoint, cost, data-flow, and fallback disclosure accuracy.
- [x] 7.4 Publish the change only after metadata-safe writeback and reset tests pass with representative manual Eagle metadata.
