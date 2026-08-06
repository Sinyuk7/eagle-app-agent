## 1. Primary CLI Flow

- [x] 1.1 Add bare board input routing so `moodtag <board-url-or-id>` enters the tagging flow.
- [x] 1.2 Normalize Eagle folder URL and ID input, then echo the resolved board path before execution.
- [x] 1.3 Add a preflight summary that shows target board, item count, scope, and overwrite risk.
- [x] 1.4 Add an explicit confirmation gate before any write to Eagle, while keeping advanced non-interactive paths available.
- [x] 1.5 Auto-enter setup in the guided main flow when API key is missing and persist it to `~/.config/moodtag/.env`.

## 2. Help and Advanced Surfaces

- [x] 2.1 Rework help output so the primary tagging flow appears before advanced commands.
- [x] 2.2 Keep `status`, `brief`, `export-context`, `reset`, and `config` available as secondary commands.
- [x] 2.3 Update README and runtime guidance to explain primary vs advanced paths and the first-run experience.

## 3. macOS Distribution

- [x] 3.1 Define the macOS installer build path for the primary user-facing release artifact.
- [x] 3.2 Ensure the installed package exposes `moodtag` on PATH without requiring Python, `uv`, or `npm`.
- [x] 3.3 Add release smoke checks for a fresh macOS install and `moodtag --help`.

## 4. Verification

- [x] 4.1 Add or adjust CLI tests for URL/ID parsing, summary display, and confirmation behavior.
- [x] 4.2 Add or adjust tests that verify help and config remain discoverable after the CLI simplification.
- [x] 4.3 Add packaging or release validation coverage for the installer path and documented install instructions.
