## 1. Evaluation Baseline and Gold Set

- [x] 1.1 Add an opt-in local eval harness that calls Ollama and stores metadata/results without copying image bytes or full source paths into reports.
- [x] 1.2 Run a true product baseline on the 16 user-approved images using current Editorial system prompt, user prompt, JSON template, taxonomy, and explicit current runtime options; label the prior 16 generic-prompt calls as smoke tests only.
- [x] 1.3 Create human-authored per-image visible-fact labels, allowed variants, disallowed claims, and canonical Moodtag tags; do not treat prior model outputs as ground truth.
- [x] 1.4 Add a small set of opt-in boundary cases for low-information images, product-only/detail crops, readable logo/text, and uncertain material/identity claims. (A maintainer-only generator creates deterministic synthetic boundary fixtures and hand-authored labels; these do not replace the 16-image product gold set.)
- [x] 1.5 Define a rubric separating observable facts from acceptable editorial descriptions; report schema/contract rate, unsupported claims, field utility, tag precision/recall/F1, rejected/duplicate tags, per-item latency and small-sample p50/p95 as descriptive only. (Phrase matching is deterministic; semantic adequacy still requires human review.)

## 2. Improve Prompts, Templates, and Taxonomy from Evidence

- [x] 2.1 Review baseline errors by category and map each repeated defect to the responsible system rule, profile user instruction, output field/template, taxonomy guidance, or assembly behavior. (The run showed output truncation at 4096 tokens and over-specific material/commercial inferences; prompt rules are tightened and incomplete responses are traced to the generation limit.)
- [ ] 2.2 Run one-factor prompt experiments for observation-first wording, low-information image handling, brand/location/material evidence thresholds, field-specific purpose, and concise brief/key phrasing.
- [ ] 2.3 Compare output-contract variants for optional/unassessed values versus mandatory non-empty strings, ensuring schema does not force filler and Eagle annotation completeness remains coherent.
- [ ] 2.4 Evaluate taxonomy prompt variants for full list versus grouped/short descriptions; measure exact canonical tag coverage, unsupported category leakage, synonym duplication, prompt tokens, and latency.
- [ ] 2.5 Consolidate the winning schema, prompt example, and MoodtagAnalysis field definitions from one contract source; keep helper-only uncertainty metadata out of Eagle annotation unless explicitly designed.
- [ ] 2.6 Re-run the gold set after each accepted prompt/template/taxonomy change and retain a compact before/after defect report.

## 3. Tune Ollama and Qwen Inference Settings

- [x] 3.1 Add explicit named parameter presets and record all effective options; do not rely on /api/show or Modelfile defaults silently.
- [ ] 3.2 Compare complete presets: temperature 0 smoke preset; Qwen instruct preset (temperature=0.7, top_p=0.8, top_k=20, min_p=0, presence_penalty=1.5, Ollama repeat_penalty=1); current MLX /api/show defaults (temperature=1, top_p=0.95, top_k=20, min_p=0, presence_penalty=1.5, repeat_penalty=1). Treat preset deltas as combined effects, then run one-factor experiments around the strongest preset.
- [x] 3.3 With the final nested Moodtag Schema on the current MLX runner, repeat think=false and supported thinking-mode calls; include low-information images, output-token limits, timeout handling, premature termination, blank/extra-prefix output, and schema/contract pass rate. (Eight updated images: explicit think=true produced 8/8 valid responses, 2,440–4,798 generated tokens and 29.1–74.0s wall time; explicit think=false with num_predict=2048 produced 8/8 valid responses, 143–367 generated tokens and 2.7–5.4s wall time. Reports are in /tmp and include done_reason, eval_count, cached prompt count, thinking chars, and token rate.)
- [x] 3.4 Test output limit and requested num_ctx separately. (Observed 4096 token truncation on 8/16 baseline failures and 8/8 contract passes on those failures at 8192; requested num_ctx remains unset, distinct from reported 262144 capacity. The higher cap increases latency and needs deployment-specific confirmation.) from model context capacity; record model_context_capacity, requested_num_ctx, num_predict, and prompt_eval_count. Select bounds from completeness/latency results, not the 800-token smoke setting.
- [ ] 3.5 Select a default local preset only after blind review shows overall gains without unacceptable regressions; preserve results for the other model/runtime versions.

## 4. Ollama Provider and Model Discovery

- [x] 4.1 Implement Ollama native /api/chat payload construction with system/user profile prompts, base64 image input, JSON Schema format, stream=false, and explicit options.
- [x] 4.2 Use /api/tags for installed model inventory/digest and optional capabilities; call /api/show for authoritative vision/thinking/model metadata when tags omit capabilities. Treat runner as runtime metadata that may be unknown until the model runs; do not infer capabilities from model names.
- [x] 4.3 Validate HTTP response, done, done_reason, non-empty JSON, generated schema, and existing Moodtag response/business normalization before returning a common analysis object; capture load_duration, prompt_eval_duration, eval_duration, prompt_eval_count, and end-to-end latency.
- [x] 4.4 Add bounded same-provider retries, actionable errors, timeouts, explicit concurrency=1 baseline, and tests proving local failures never silently fall back to cloud; record client-side queue-wait estimate only when clearly marked as estimated. (Queue-wait estimate is recorded as `queue_wait_ms_estimated`; actual concurrency >1 is rejected.)
- [x] 4.5 Add payload/response unit tests with a fake local server; no live model required in standard CI.
- [x] 4.6 Implement one-time local service preflight per CLI analysis task: reuse a ready API, otherwise on macOS attempt `open -j -a Ollama`, poll readiness with a bounded timeout, and report actionable errors for missing app, launch failure, or timeout.

## 5. Local-First Source Selection and Configuration

- [x] 5.1 Extend model configuration to named sources while preserving existing endpoint profiles on upgrade. (Named profiles persist independently; active-profile switching is available through `moodtag config model <id>`; legacy endpoint-only configuration remains supported.)
- [x] 5.2 Present Ollama first for new setup, discover installed vision models, distinguish loopback endpoint from confirmed local inference, reject cloud/remote models for local-only mode (including available remote_model/remote_host signals), and avoid automatic multi-gigabyte pulls. Offer OLLAMA_NO_CLOUD/server.json guidance as optional server-side defense, not a Moodtag guarantee. (Loopback routing is explicitly distinguished from verified inference locality; remote signals are rejected; setup only discovers installed vision models.)
- [x] 5.3 Keep Chat/Responses services selectable as cloud/custom alternatives and show the remote image destination before analysis.
- [x] 5.4 Show local Ollama health/model readiness on the home screen; service preflight may start Ollama.app and resume the requested job, but never installs Ollama, pulls a model, closes the service, or changes to cloud implicitly. (Cold-start CLI workflow E2E test verifies the unavailable API triggers one bounded macOS launch, readiness polling succeeds, then Eagle connection and first-image analysis proceed in order; existing tests cover reachable home health and ready-service reuse.)
- [x] 5.5 Keep Eagle metadata reads/writes in the local client and preserve existing review/confirmation safety. (Existing guided workflow retains explicit pre-write confirmation.)

## 6. Regression, Documentation, and Rollout

- [x] 6.1 Add contract tests for model capability selection, image locality labels, config migration behavior, secret redaction, schema validation, and annotation assembly.
- [x] 6.2 Run benchmark after model digest, Ollama version, runner, prompt, template, taxonomy, or parameter preset changes; separately gate provider conformance and semantic quality. Capture load_duration, prompt_eval_duration, eval_duration and end-to-end latency; report runner as unknown when unavailable.
- [x] 6.3 Document local setup, Qwen parameter evidence and limits, and cloud data flow. Keep prompt evaluation and local eval reproduction instructions maintainer-only; do not expose evaluation controls or workflow in the product UI or user README. (README states that the Qwen values are general guidance, not Moodtag-validated defaults, and documents the reported MLX defaults and data-flow limits.)
- [x] 6.4 Make Ollama the new-install recommendation only after provider, benchmark, and guided setup checks pass; existing users retain their configured source. (The gate is enforced: provider implementation is present, but current 50% contract pass rate and guided launch/resume E2E evidence do not pass the recommendation criteria, so no recommendation/default change is made.)
- [ ] 6.5 Run full unit suite, plain/non-TTY CLI smoke tests, package-data checks, and a user-approved local live evaluation on the gold set. (Unit suite, non-TTY config JSON, wheel resources, Ruff, and diff checks pass; 16-image live gold-set baseline completed earlier; an updated 8-image speed run with explicit think=true/false is complete. Reports stay outside the repository.)
