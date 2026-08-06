## Why

Moodtag currently hard-codes DashScope as a primary provider and n1n as a fallback. This couples configuration, credential lookup, retry behavior, documentation, and user-facing setup to vendor names even though the application only needs one active model endpoint at a time.

The application needs a small, user-configured model boundary: select a request protocol, enter an endpoint URL, model, and API key once, then update that single configuration whenever the user changes services.

## What Changes

- **BREAKING** Replace the primary/fallback provider configuration with exactly one active provider configuration containing `protocol`, `base_url`, and `model`.
- **BREAKING** Remove DashScope defaults, `DASHSCOPE_API_KEY`, `VL_API_KEY`, vendor URL detection, provider cooldown state, and all fallback routing behavior.
- Store the single credential in the existing user `.env` file under `MOODTAG_API_KEY`; never persist it in JSON configuration, CLI arguments, logs, or error output.
- Add `chat` and `responses` protocol support. Each protocol constructs its own request and extracts its own response text before using the existing Moodtag analysis normalization contract.
- Add an interactive first-run and `moodtag config setup` flow that collects protocol, base URL, model, and API key, confirms before saving, and resumes the requested tagging workflow.
- Keep non-interactive configuration via `moodtag config set` and key-only replacement via `moodtag config auth`.
- Make API-requiring commands report actionable setup errors in non-interactive terminals; commands that do not call a model remain usable without model setup.

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
- Existing user configuration using primary/fallback fields or DashScope-specific environment variables will no longer be supported and must be replaced through `moodtag config setup`.
- Existing provider, configuration, guided-flow, payload, response parsing, and logging tests require replacement or extension for the two supported protocols.
