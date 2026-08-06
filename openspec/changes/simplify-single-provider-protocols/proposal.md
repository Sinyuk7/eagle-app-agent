## Why

Moodtag currently models more than one endpoint slot. This couples configuration, credential lookup, retry behavior, documentation, and user-facing setup even though the application only needs one active model endpoint at a time.

The application needs a small, user-configured model boundary: select a request protocol, enter an endpoint URL, model, and API key once, then update that single configuration whenever the user changes services.

This is a clean next-version boundary. There are no existing users or supported provider configurations to migrate, so the runtime and documentation can remove the old endpoint slots and fallback behavior outright.

## What Changes

- Replace provider slots with exactly one active model configuration containing `protocol`, `base_url`, and `model`.
- **BREAKING** Remove model-endpoint defaults from the clean configuration. A model command with no complete endpoint must enter setup (TTY) or fail with the setup command (non-TTY).
- Remove endpoint-specific defaults, URL detection, cooldown state, and routing behavior.
- Store the single credential in the existing user `.env` file under `MOODTAG_API_KEY`; never persist it in JSON configuration, CLI arguments, logs, or error output.
- Add `chat` and `responses` protocol support. Each protocol constructs its own request and extracts its own response text before using the existing Moodtag analysis normalization contract.
- Add an interactive first-run and `moodtag config setup` flow that collects protocol, base URL, model, and API key, confirms before saving, and resumes the requested tagging workflow.
- Keep non-interactive configuration via `moodtag config set` and key-only replacement via `moodtag config auth`.
- Preserve non-secret environment overrides (`MOODTAG_PROTOCOL`, `MOODTAG_BASE_URL`, `MOODTAG_MODEL`, and `MOODTAG_EAGLE_API`) over JSON; inherited `MOODTAG_API_KEY` always wins over `.env`.
- Make API-requiring commands report actionable setup errors in non-interactive terminals; commands that do not call a model remain usable without model setup.
- Do not migrate, infer, or preserve old provider/fallback fields; a clean setup is the only supported configuration path.

## Capabilities

### New Capabilities
- `single-provider-configuration`: Configure, inspect, and replace one active Moodtag model endpoint and its secret reference.
- `model-protocol-adapters`: Analyze images through either Chat Completions or Responses while preserving the common Moodtag result contract.
- `guided-model-setup`: Provide a recoverable first-run CLI setup experience for the single configured endpoint.

### Modified Capabilities

- None.

## Impact

- Affected core modules: `moodtag_core/provider.py`, `moodtag_core/response.py`, and `moodtag_core/contract.py`.
- Affected CLI/configuration modules: `moodtag/cli.py`, `moodtag/config.py`, `.env.example`, README, contributor documentation, and live-run scripts.
- Existing configuration, guided-flow, payload, response parsing, and logging tests require replacement for the two supported protocols.
