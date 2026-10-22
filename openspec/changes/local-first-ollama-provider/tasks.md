## 1. Evaluation Baseline and Gold Set

- [ ] 1.1 Add an opt-in local eval harness that calls Ollama and stores metadata/results without copying image bytes or full source paths into reports.
- [ ] 1.2 Run a true product baseline on the 16 user-approved images using current Editorial system prompt, user prompt, JSON template, taxonomy, and explicit current runtime options; label the prior 16 generic-prompt calls as smoke tests only.
- [ ] 1.3 Create human-authored per-image visible-fact labels, allowed variants, disallowed claims, and canonical Moodtag tags; do not treat prior model outputs as ground truth.
- [ ] 1.4 Add a small set of opt-in boundary cases for low-information images, product-only/detail crops, readable logo/text, and uncertain material/identity claims.
- [ ] 1.5 Define a rubric separating observable facts from acceptable editorial descriptions; report schema/contract rate, unsupported claims, field utility, tag precision/recall/F1, rejected/duplicate tags, per-item latency and small-sample p50/p95 as descriptive only.

## 2. Improve Prompts, Templates, and Taxonomy from Evidence

- [ ] 2.1 Review baseline errors by category and map each repeated defect to the responsible system rule, profile user instruction, output field/template, taxonomy guidance, or assembly behavior.
- [ ] 2.2 Run one-factor prompt experiments for observation-first wording, low-information image handling, brand/location/material evidence thresholds, field-specific purpose, and concise brief/key phrasing.
- [ ] 2.3 Compare output-contract variants for optional/unassessed values versus mandatory non-empty strings, ensuring schema does not force filler and Eagle annotation completeness remains coherent.
- [ ] 2.4 Evaluate taxonomy prompt variants for full list versus grouped/short descriptions; measure exact canonical tag coverage, unsupported category leakage, synonym duplication, prompt tokens, and latency.
- [ ] 2.5 Consolidate the winning schema, prompt example, and MoodtagAnalysis field definitions from one contract source; keep helper-only uncertainty metadata out of Eagle annotation unless explicitly designed.
- [ ] 2.6 Re-run the gold set after each accepted prompt/template/taxonomy change and retain a compact before/after defect report.

## 3. Tune Ollama and Qwen Inference Settings

- [ ] 3.1 Add explicit named parameter presets and record all effective options; do not rely on /api/show or Modelfile defaults silently.
- [ ] 3.2 Compare complete presets: temperature 0 smoke preset; Qwen instruct preset (temperature=0.7, top_p=0.8, top_k=20, min_p=0, presence_penalty=1.5, Ollama repeat_penalty=1); current MLX /api/show defaults (temperature=1, top_p=0.95, top_k=20, min_p=0, presence_penalty=1.5, repeat_penalty=1). Treat preset deltas as combined effects, then run one-factor experiments around the strongest preset.
- [ ] 3.3 With the final nested Moodtag Schema on the current MLX runner, repeat think=false and supported thinking-mode calls; include low-information images, output-token limits, timeout handling, premature termination, blank/extra-prefix output, and schema/contract pass rate.
- [ ] 3.4 Test output limit and requested num_ctx separately from model context capacity; record model_context_capacity, requested_num_ctx, num_predict, and prompt_eval_count. Select bounds from completeness/latency results, not the 800-token smoke setting.
- [ ] 3.5 Select a default local preset only after blind review shows overall gains without unacceptable regressions; preserve results for the other model/runtime versions.

## 4. Ollama Provider and Model Discovery

- [ ] 4.1 Implement Ollama native /api/chat payload construction with system/user profile prompts, base64 image input, JSON Schema format, stream=false, and explicit options.
- [ ] 4.2 Use /api/tags for installed model inventory/digest and optional capabilities; call /api/show for authoritative vision/thinking/model metadata when tags omit capabilities. Treat runner as runtime metadata that may be unknown until the model runs; do not infer capabilities from model names.
- [ ] 4.3 Validate HTTP response, done, done_reason, non-empty JSON, generated schema, and existing Moodtag response/business normalization before returning a common analysis object; capture load_duration, prompt_eval_duration, eval_duration, prompt_eval_count, and end-to-end latency.
- [ ] 4.4 Add bounded same-provider retries, actionable errors, timeouts, explicit concurrency=1 baseline, and tests proving local failures never silently fall back to cloud; record client-side queue-wait estimate only when clearly marked as estimated.
- [ ] 4.5 Add payload/response unit tests with a fake local server; no live model required in standard CI.
- [ ] 4.6 Implement one-time local service preflight per CLI analysis task: reuse a ready API, otherwise on macOS attempt `open -j -a Ollama`, poll readiness with a bounded timeout, and report actionable errors for missing app, launch failure, or timeout.

## 5. Local-First Source Selection and Configuration

- [ ] 5.1 Extend model configuration to named sources while preserving existing endpoint profiles on upgrade.
- [ ] 5.2 Present Ollama first for new setup, discover installed vision models, distinguish loopback endpoint from confirmed local inference, reject cloud/remote models for local-only mode (including available remote_model/remote_host signals), and avoid automatic multi-gigabyte pulls. Offer OLLAMA_NO_CLOUD/server.json guidance as optional server-side defense, not a Moodtag guarantee.
- [ ] 5.3 Keep Chat/Responses services selectable as cloud/custom alternatives and show the remote image destination before analysis.
- [ ] 5.4 Show local Ollama health/model readiness on the home screen; service preflight may start Ollama.app and resume the requested job, but never installs Ollama, pulls a model, closes the service, or changes to cloud implicitly.
- [ ] 5.5 Keep Eagle metadata reads/writes in the local client and preserve existing review/confirmation safety.

## 6. Regression, Documentation, and Rollout

- [ ] 6.1 Add contract tests for model capability selection, image locality labels, config migration behavior, secret redaction, schema validation, and annotation assembly.
- [ ] 6.2 Run benchmark after model digest, Ollama version, runner, prompt, template, taxonomy, or parameter preset changes; separately gate provider conformance and semantic quality. Capture load_duration, prompt_eval_duration, eval_duration and end-to-end latency; report runner as unknown when unavailable.
- [ ] 6.3 Document local setup, Qwen parameter evidence and limits, cloud data flow, prompt evaluation workflow, and how to reproduce local eval.
- [ ] 6.4 Make Ollama the new-install recommendation only after provider, benchmark, and guided setup checks pass; existing users retain their configured source.
- [ ] 6.5 Run full unit suite, plain/non-TTY CLI smoke tests, package-data checks, and a user-approved local live evaluation on the gold set.
