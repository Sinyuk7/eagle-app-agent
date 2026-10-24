## 1. Tag Contract

- [ ] 1.1 Refactor generated-tag reconciliation so direct model tags and accepted `use_intents` mappings share one active-profile taxonomy validation path.
- [ ] 1.2 Apply canonicalization, stable deduplication, and `max_tags` only after all generated candidates are combined.
- [ ] 1.3 Keep accepted `use_intents` and rejected intent IDs in their existing structured fields when a mapped tag is unavailable in the active taxonomy.
- [ ] 1.4 Fix `reconcile_tags()` so repeated valid tags are ignored without entering `rejected_tags`.
- [ ] 1.5 Ensure `tag_groups` is recomputed from final canonical tags and that writeback continues preserving existing Eagle tags outside the taxonomy.
- [ ] 1.6 Add profile-specific regression tests for direct tags, derived tags, missing mapped tags, case variants, duplicates, max-tags truncation, grouping, and manual Eagle tags.

## 2. Eagle Scope Adapter

- [ ] 2.1 Define the internal scope input and metadata-bearing `ResolvedScope` model without changing the public analysis result contract.
- [ ] 2.2 Extend Eagle V2 item querying to support a one-time selected snapshot and validated filter parameters while preserving recursive Folder behavior.
- [ ] 2.3 Implement API-adapter mappings for Eagle field names such as `star`/`rating` and confirm the native Shape query semantics before exposing Shape filtering.
- [ ] 2.4 Enforce complete pagination, deduplication, stable ordering, and explicit errors when a requested filter or complete result is unsupported.
- [ ] 2.5 Add tests for empty selection, selected-scope snapshot stability, Folder plus tag intersection, non-taxonomy manual filter tags, pagination beyond 1000 items, duplicate items, unsupported media, and unsupported API filters.

## 3. CLI and Workflow Integration

- [ ] 3.1 Add `moodtag selected` as a scope entry while keeping existing Folder invocation compatible.
- [ ] 3.2 Add the first supported condition filter (`--tag`) with documented repeated-tag intersection semantics; gate Rating/Shape options on confirmed Eagle API behavior.
- [ ] 3.3 Feed every resolved scope through the existing scan summary, skip/regenerate policy, model setup, analysis, and metadata-safe writeback pipeline.
- [ ] 3.4 Ensure empty scopes exit before provider setup or AI requests and that selected scope remains fixed during analysis.
- [ ] 3.5 Add CLI and workflow tests for JSON/plain output, empty results, selected snapshots, recursive folders with filters, and safe handling of unsupported or non-image items.

## 4. Documentation and Verification

- [ ] 4.1 Document the generated-tag versus existing-manual-tag boundary and the active-profile validation rule.
- [ ] 4.2 Document `moodtag selected`, supported filters, filter semantics, API version requirements, and the absence of public Moodtag state filters.
- [ ] 4.3 Run the focused taxonomy, scope, and CLI tests, then run the complete test suite and resolve regressions.
- [ ] 4.4 Verify the OpenSpec scenarios against implementation behavior and record any Eagle API capability findings before enabling additional filters.
