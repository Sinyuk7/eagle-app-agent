## Why

The guided CLI already has the right entry points and image sources, but it asks users to make decisions that are already implied by the current state. Repeated confirmations and context loss after setup or recoverable errors make routine tagging slower and less safe.

## What Changes

- Keep the two existing entry styles and three image sources.
- Remove the Remote API protocol choice from ordinary model setup; derive it from the model catalog.
- Simplify folder ambiguity, current-selection, and library-size recovery paths.
- Skip processing-strategy prompts when only one safe strategy exists.
- Save model setup immediately and return to the active tagging task with its scope preserved.
- Use one final confirmation before model work, with stronger confirmation for full regeneration.
- Preserve task context across recoverable connection/setup errors.
- Avoid active Ollama health probes on the home screen.

## Capabilities

### New Capabilities
- `guided-flow-simplification`: State-aware guided navigation and reduced decision points.
- `model-setup-continuation`: Model setup that resumes the pending tagging task.
- `scope-query-guard`: Early library-size validation and recoverable scope selection.

### Modified Capabilities
- None.

## Impact

Primary code is in `moodtag/cli.py`, `moodtag/ui/menu.py`, Eagle scope/query helpers, and related CLI tests and documentation. Provider wire formats, prompt contracts, taxonomy, and Eagle metadata contracts remain unchanged.
