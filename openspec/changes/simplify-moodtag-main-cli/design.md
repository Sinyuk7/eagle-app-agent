## Context

Current `moodtag` behavior is optimized for a maintainer-oriented CLI surface:

- Installation guidance is developer-first and currently points users to `uv tool install`.
- The primary tagging flow is split across `status`, `tag`, and `tag --write`.
- Users must currently understand `--board`, recursive scope, and write semantics before they can complete a first successful run.
- The repository has no existing OpenSpec capability specs, so this change defines new product capabilities rather than modifying an established contract.

The target audience for this change is non-technical macOS users who can open Terminal and run a command, but should not be expected to install developer tooling first or reason through multiple command modes before tagging a folder.

## Goals / Non-Goals

**Goals:**
- Make `moodtag <board-url-or-id>` the default happy path for tagging.
- Accept both Eagle folder URLs and folder IDs in the primary flow.
- Add a human-readable preflight summary and explicit confirmation before write.
- Auto-enter setup on first run when API key is missing, and persist the key in `~/.config/moodtag/.env`.
- Preserve `--help` and `config` as required support surfaces.
- Define a macOS-first installer path that can become the documented primary installation route.
- Keep existing advanced commands available for maintainers and power users.

**Non-Goals:**
- Redesign the underlying tagging model, provider chain, taxonomy, or annotation format.
- Replace the CLI with a GUI or native macOS app.
- Remove existing advanced commands in this change.
- Finalize release signing, notarization, or App Store distribution strategy beyond what is needed for a direct macOS installer path.

## Decisions

### 1. Use implicit main-flow routing for bare board input

Decision:
- Treat a bare positional board argument as the primary tagging entry point.
- Preserve existing subcommands for advanced and backward-compatible usage.

Rationale:
- This delivers the desired one-command mental model without deleting existing operational surfaces.
- It allows docs and help text to lead with the end-user flow while keeping current commands available for automation and maintenance.

Alternatives considered:
- Add a new `run` or `start` subcommand.
  - Rejected because it still requires users to learn a command verb before the actual task.
- Replace the existing CLI entirely.
  - Rejected because it would create unnecessary migration risk for maintainers.

### 2. Make the primary flow guided and confirmation-based

Decision:
- The main flow will resolve the board, compute scope, show a summary, and wait for explicit user confirmation before writing.
- No Eagle metadata write will occur before confirmation in the primary flow.

Rationale:
- The current dry-run then rerun pattern is safe but cognitively heavy for non-technical users.
- A single command followed by an explicit confirmation preserves safety while removing the need to remember a second command.

Alternatives considered:
- Keep the current dry-run plus `--write` rerun as the only path.
  - Rejected because it keeps the core interaction too procedural for the target audience.
- Auto-write immediately after parsing input.
  - Rejected because it increases accidental overwrite risk.

### 2b. Auto-run setup when key is missing

Decision:
- In the guided main flow, if no usable API key exists, prompt for the key and store it in `~/.config/moodtag/.env`.
- The stored key should become the new default for subsequent runs without requiring the user to learn environment syntax.

Rationale:
- This keeps first run inside the CLI instead of bouncing the user into shell-variable setup.
- The env file path matches the repo’s current config-loading behavior and minimizes new storage concepts.

Alternatives considered:
- Force the user to edit `.env` manually.
  - Rejected because it pushes the simplest setup step into developer territory.
- Store secrets in a separate JSON config file.
  - Rejected because the project already treats `.env` as the natural secret boundary.

### 3. Keep help and config as advanced support surfaces

Decision:
- `--help` remains globally available.
- `config` remains available for non-secret defaults, but is not part of the first-run happy path.
- Help output should present the single-command main flow first and list advanced commands second.

Rationale:
- Users still need discoverability and a place to troubleshoot configuration.
- Power users and maintainers need stable operational commands that do not interfere with the simplified primary flow.

Alternatives considered:
- Remove `config` and rely only on environment variables.
  - Rejected because it would make advanced setup harder, not easier.
- Hide advanced commands completely from help.
  - Rejected because it would reduce discoverability for legitimate secondary workflows.

### 4. Choose a macOS installer as the primary distribution path

Decision:
- Define a direct macOS installer artifact (`.pkg` as the preferred target, with `.dmg` as an optional wrapper or future addition) as the user-facing installation path.
- Keep `uv` and other developer-centric install methods documented as secondary paths.

Rationale:
- A direct installer best matches the target audience expectation: download, open, install, run.
- It avoids assuming prior installation of `uv`, Python, Homebrew, or Node.js.

Alternatives considered:
- Keep `uv tool install` as the primary path.
  - Rejected because it assumes prior tooling that many end users will not have.
- Make Homebrew the primary path.
  - Rejected because it is common among technical Mac users, but still not universal among non-technical users.

### 5. Preserve current tagging engine and advanced workflow internals

Decision:
- Reuse the existing board resolution, scope loading, tagging, and write logic where possible.
- Limit the change to entrypoint UX, confirmation flow, help/docs, and packaging/distribution concerns.

Rationale:
- The highest value is in simplifying entry and installation, not replacing the core processing engine.
- Reuse reduces regression risk and keeps the implementation focused.

Alternatives considered:
- Rewrite the tagging flow around a brand-new command layer.
  - Rejected because it would expand the change surface without clear user benefit.

## Risks / Trade-offs

- [Interactive flow may reduce scriptability] → Mitigation: keep existing advanced subcommands and explicit non-interactive paths for automation.
- [Auto-setup may surprise advanced users] → Mitigation: limit automatic setup to the guided main flow, not explicit advanced subcommands.
- [Installer packaging adds release complexity] → Mitigation: stage packaging work behind a dedicated build/release task and keep developer install paths available as fallback.
- [Bare positional routing can create parser ambiguity] → Mitigation: reserve known subcommand names first, then treat any remaining first positional argument as board input.
- [Users may still target the wrong board or too large a scope] → Mitigation: preflight summary must show resolved board path, item count, recursive scope, and overwrite risk before confirmation.
- [Two installation audiences can fragment documentation] → Mitigation: clearly separate end-user installation from contributor/developer installation in docs.

## Migration Plan

1. Introduce the primary bare-argument tagging flow while preserving existing subcommands.
2. Update help text and README to promote the one-command path and demote developer-first installation instructions.
3. Add macOS installer packaging and release validation alongside the existing Python package release flow.
4. Ship the simplified CLI UX and installer path in parallel with existing advanced workflows.

Rollback:
- Remove the primary installer from docs and release assets if packaging quality is not ready.
- Keep advanced commands and developer install paths intact throughout rollout.
- Disable bare-argument routing if parser regressions surface during validation.

## Open Questions

- Should the first end-user release ship `.pkg` only, or both `.pkg` and `.dmg`?
- Should the guided confirmation prompt use simple `y/N`, a full-word confirmation, or both?
- Should the primary flow keep a visible escape hatch to the current `tag --write` semantics for advanced users, or leave that path documented but not advertised?
