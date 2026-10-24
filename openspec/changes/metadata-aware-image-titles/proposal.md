## Why

Moodtag currently analyzes image pixels without the Eagle item's existing title or source URL, even though those can provide useful work and provenance context. It also cannot repair meaningless filenames such as `1.jpg`; adding contextual analysis and a conservative title suggestion improves interpretation and library searchability while preserving meaningful human names.

## What Changes

- Pass each Eagle item's original name and optional source URL as per-image user-prompt context to every supported provider.
- Require both `default` and `editorial` model contracts to return `suggest_title`; an empty string means preserve the existing name, and a non-empty title omits the extension.
- Allow metadata to inform contextual interpretation while keeping visible text and brand evidence grounded in pixels, and requiring visual evidence for confirmed commercial-format confidence.
- Conditionally rename through Eagle V2 item update, preserving the existing extension and avoiding overwriting a name changed after analysis.
- Keep title suggestions and input metadata out of Eagle annotation text; leave taxonomy, CLI controls, and unrelated Eagle endpoints unchanged.

## Capabilities

### New Capabilities
- `image-metadata-context`: Use an item's existing title and optional source URL as bounded, unverified context for image analysis.
- `conservative-image-renaming`: Produce an optional replacement title and safely apply it during the existing write flow.

### Modified Capabilities

## Impact

- Affects prompt rendering and resources, shared analysis contract and schema, response normalization, provider call paths, Eagle item update, result/write flow, and related tests and fixtures.
- Eagle writes move from V1 `/api/item/update` to V2 `/api/v2/item/update`; other Eagle endpoints remain unchanged.
- No new dependencies, CLI flags, taxonomy changes, web fetching, or annotation fields.
