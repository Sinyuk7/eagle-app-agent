Moodboard body design contract
==============================

Purpose
-------

Generate only an HTML body fragment. Do not generate `<!doctype>`, `<html>`,
`<head>`, `<body>`, closing document tags, meta tags, viewport tags, or global
shell code. The CLI owns the document shell and inserts this fragment into
`index.html`.

This body-spec governs how creative material becomes a webpage UI and visual
planning interface. It does not decide the creative direction. The reasoning
step decides whether a project is rainy, neon, lonely, romantic, harsh, soft,
bright, documentary, synthetic, restrained, maximal, or any other aesthetic
direction.

The spec is a hard delivery contract plus a set of design judgement principles.
It must not become a fixed component menu, page archetype list, section order,
or house style. The agent owns the page structure.

Hard Contract
-------------

Return body-only HTML that can be injected into an existing document.

Allowed: one first-level `<style data-moodboard-theme>` block; semantic body
content such as `<main>`, `<section>`, `<article>`, `<figure>`,
`<figcaption>`, `<aside>`, `<blockquote>`, `<ol>`, `<ul>`, and tables only when
tabular comparison is clearest; project-relative image paths, local absolute
paths, `file://` URIs, or remote URLs in `<img src>`.

Required: visible core content without JavaScript; useful `alt` text for
meaningful images; no empty image sources; no duplicate IDs; stable media
geometry before images load; readable heading order; text that wraps without
overlap; responsive behavior on phone, tablet, and desktop; no hidden primary
idea; no broken local assets or fragment links after `moodboard output write`.

Disallowed: full-document tags, metadata, viewport tags, document-head edits,
external JavaScript, script-dependent interaction, autoplaying carousels, hidden
core content, empty image sources, duplicate IDs, broken links, fixed
taxonomies, and long logistics unless they directly change visual execution.

Page Role
---------

Design a visual planning page for photography, editorial portraits,
cosplay/IP-inspired shoots, storyboards, visual concept development, and
creative exploration.

The page should feel like a visual planning interface, digital editorial board,
or art-directed local web document. It should help viewers understand how to
look, shoot, compose, pace, color, style, sequence, and edit the project.

Center the page on images, mood, lens language, framing, rhythm, pose,
movement, color, styling, motifs, details, main images, pause images,
close-ups, and sequence flow. Mention gear, logistics, budget, or operations
only when they directly affect the image.

Design Judgement
----------------

Build the page from the project's strongest visual problem. Do not start from a
default section list.

Use the material to decide:

- what the first impression must be;
- what should be compared, sequenced, isolated, repeated, enlarged, compressed,
  annotated, or left quiet;
- which visual ideas deserve images and which deserve type, diagrams, lists, or
  negative space;
- whether the page should feel dense, spacious, clinical, cinematic, fragmented,
  archival, intimate, operational, lyrical, or severe;
- which parts should be stable planning information and which parts should be
  expressive visual direction.

Design principles should help resolve tradeoffs, not prescribe widgets. A page
can be strong with no color-module, no timeline, no cards, no hero split, no
shot map, or no named component if the project does not call for those forms.

Design Dimensions
-----------------

Treat the following as dimensions to evaluate, not a checklist to render. Use
only the dimensions supported by the project material, and invent the page
structure that best expresses them.

- Visual narrative: how the set opens, turns, pauses, escalates, or resolves.
- Sequence, time, and rhythm: shoot order, emotional progression, scene order,
  frame pacing, or edit rhythm.
- Anchor image and first impression: the dominant image, color, gesture,
  surface, phrase, or spatial relationship the viewer must understand first.
- Tone and palette: color weight, contrast, temperature, saturation, surface,
  skin treatment, accent behavior, and how the page itself should echo the shoot
  without becoming a one-note palette.
- Lens language and framing: distance, crop, angle, compression, distortion,
  foreground/background relationship, negative space, and gaze direction.
- Spatial relationship and scale: body versus location, prop versus face,
  architecture versus figure, crowding versus isolation.
- Pose, gesture, and movement: stance, hand language, stillness, transition,
  repeated action, choreography, or physical tension.
- Detail and motif systems: makeup, hair, fabric, prop, accessory, texture,
  symbol, light fragment, local color, or recurring shape.
- Contrast and boundary: what to emphasize, what to suppress, what a reference
  contributes, and what must not be copied.
- Evidence and reference coverage: which source images carry the argument,
  which are supporting evidence, and where the set has gaps, duplicates, or
  outliers.
- Final reference audit layer: when the source pool is sizable, include an end
  layer that lets the viewer scan supplied or selected references for coverage,
  repetition, gaps, and outliers.

Optional Strategies, Not Templates
----------------------------------

The agent may use any structure, layout, class names, or local visual language
that satisfies the hard contract and fits the project. The examples below are
strategy prompts, not required components:

- large scale shifts for hierarchy;
- image-led openings, dense contact sheets, quiet text passages, or graphic
  interludes;
- editorial grids, asymmetric layouts, spatial maps, annotated evidence, or
  controlled negative space;
- sequence lanes, frame strips, crop studies, pose studies, motif extraction,
  light maps, palette-as-structure, or comparison diagrams;
- type used as pace, silence, instruction, warning, or summary rather than
  ordinary decoration;
- repeated visual evidence grouped by role instead of by file order;
- responsive art direction through crop, scale, image priority, and layout
  rhythm, not only through resizing.

Do not treat those examples as a menu to exhaust. A page with two highly
resolved visual moves is better than a page that mechanically includes every
possible module.

Anti-template Review
--------------------

Before returning the body fragment, check for template drift:

- If the page still reads as a generic moodboard after replacing the project
  nouns, redesign the structure.
- If the page defaults to `title + paragraph + three cards` in every section,
  redesign the rhythm.
- If the page repeats the same component order used for a previous unrelated
  project, justify the repetition from the current material or change it.
- If every image receives equal scale despite clear differences in importance,
  redesign the hierarchy.
- If color, timeline, shot map, or mood comparison appears only because the spec
  mentioned it, remove or transform it.
- If class names or headings come from habit rather than the page's own logic,
  rename and restructure them.

Grid And Image Layout
---------------------

Image layout is part of the concept. Before placing images, define the layout
system from the current material: visual role, image priority, reading order,
column or row rhythm, aspect ratio behavior, gaps, captions, and what should
remain uncropped.

For modules with several peer images, prefer the deterministic layout toolchain
over hand-computing image dimensions in the body fragment. The toolchain is
spec-only: it returns JSON image specs or geometry plans and must not decide the
surrounding HTML component. The agent still owns the component role, reading
order, semantic classes, captions, and final HTML.

Use `moodboard layout catalog` only to prepare an Eagle folder as a reusable
image pool; the folder itself is not the layout unit. A page module may select
one, two, three, or any number of images from that pool. Use
`moodboard layout inspect` when a module only needs source paths, intrinsic
dimensions, aspect ratios, orientation, and safe `width`/`height` attributes.
Use `moodboard layout plan` when a module needs deterministic geometry for a
declared layout mode such as `justified`, `strip`, `stack`, or `grid`.

Before calling `moodboard layout plan`, decide the module's visual role and pass
that decision explicitly through the mode and parameters. Use `justified` only
for equal-status reference groups, contact sheets, archive walls, or dense peer
image sets that need exact row widths. Use `strip` for one-row detail bands,
`stack` for vertical comparisons or sequence frames, and `grid` for fixed-track
panels. Do not let the tool pick the concept or replace semantic HTML
composition.

For review-oriented moodboards with a sizable local reference pool, generally
append a final reference audit layer that previews all selected or supplied
source images in one place. A final Reference wall is an acceptable and expected
form when it fits, but the audit layer may also become a contact sheet, archive
shelf, film strip, evidence index, or grouped reference ledger. Treat this as an
audit and comparison layer, not as the main concept narrative. Keep earlier
sections selective and content-led, then use a final `moodboard layout plan`
pass, often `--mode justified`, over the complete review set when exact rows
help the viewer scan coverage, duplicates, gaps, and outliers.

Use CSS Grid for primary image groups that need two-dimensional order. Grid
tracks, gutters, and explicit spans make rows, columns, priority, and reading
order auditable. Use Flexbox for one-dimensional strips. Do not use CSS columns
or masonry-style flows for primary concept, sequence, or rhythm sections.

Every primary image group must resolve into an intentional rectangle, clean
band, deliberate stack, or clearly authored asymmetry. Avoid ragged right edges,
accidental holes, orphan tiles, and uneven bottom edges unless the asymmetry is
content-led. Close uneven counts with a lead tile, wide tile, text note, palette
module, diagram, or controlled negative-space panel only when that helps the
concept.

Set stable media geometry before images load: use explicit `aspect-ratio`
values or grid row spans; include `width` and `height` when known; constrain
media with `max-inline-size: 100%` and `block-size: auto`; use
`object-fit: cover` for intentional editorial crops and `object-fit: contain`
only when the full reference must remain visible; set `object-position` when
faces, hands, props, or composition lines must not be cropped accidentally.

Use named layout roles instead of `:nth-child()` placement when individual image
priority matters. Roles may be invented for the project: lead, witness, pause,
trace, signal, obstruction, detail, false-friend, climax, or any other semantic
role that explains the layout.

Image Use
---------

Use `<img>` for visual references. Every meaningful image needs useful `alt`
text, and decorative overlays must not replace the underlying alt text.

Use `<figure>` and `<figcaption>` when interpretation is needed. Captions should
say what is borrowed, how it transfers, and what to watch during execution, not
merely describe appearance. Avoid vague captions such as `nice mood`,
`cinematic`, `beautiful reference`, or `good lighting`.

When references vary by source, use subtle scoped treatment such as shared
borders, restrained filters, overlays, grouping, or consistent frame geometry.
Do not filter so strongly that references become misleading.

Color, Tone, And Surface
------------------------

Color UI must behave like a planning tool and a page atmosphere at the same
time. Use proportional swatches only when palette ratios are known or genuinely
useful. Otherwise express color through section backgrounds, image grouping,
linework, labels, scale, or local tokens.

Each key color should carry a semantic role and practical use, such as
`background shadow`, `skin warmth`, `signal accent`, `metal highlight`,
`wardrobe base`, `prop color`, `negative space`, or `transition tone`.

Where useful, map the palette to local CSS variables so the interface and shoot
palette feel connected. Keep the mapping scoped to the generated body.

Avoid one-note UI palettes even when respecting the project's palette. Dark
pages need clear layer separation through surface levels, section background
shifts, line strength, captions, and accent rules. Light pages need contrast,
controlled surfaces, strong image rhythm, subtle lines, and clear type
hierarchy.

Sequence, Mood, And Contrast
----------------------------

When content includes a beginning, middle, ending, transformation, scene order,
time of day, or shot progression, express the order visually rather than as a
plain list. The form can be linear, circular, staggered, nested, cinematic,
map-like, or editorial as long as order is readable.

When content contains emotional opposition, make the tension spatially visible
through contrast, distance, scale, color, density, image pairing, type
treatment, or diagrammatic structure. Do not force a formal axis if another
structure communicates the opposition better.

When the project needs executable shot planning, describe crop, distance, light
direction, pose, movement, foreground/background relationship, and edit role.
Do not let shot planning consume the whole page when mood, reference evidence,
or visual narrative is more important.

Layout Language
---------------

Use semantic reusable class names that describe role, behavior, or local page
logic. Names may be project-specific when they clarify a unique visual argument.
Generic utility opt-ins from the shell, such as `.moodboard-page`,
`.moodboard-canvas`, `.shell`, `.grid`, `.cluster`, `.media-box`, `.swatch-row`,
and `.snap-row`, are available but never required.

Do not place cards inside cards. Page sections should be full-width bands or
unframed layouts with constrained inner content. Cards are acceptable for
repeated items, compact comparisons, shot cards, reference items, and
modal-like framed tools when those forms are truly appropriate.

Horizontal scroll is acceptable only for peer references, detail strips, contact
surfaces, or deliberately compact evidence. Do not hide the primary idea,
sequence, or final direction inside a carousel.

Responsive Behavior
-------------------

The body must be readable on phone, tablet, and desktop. Use responsive grids,
container-aware layout, flexible spacing, and stable aspect ratios.

Prefer component-local layout logic over a single global breakpoint scheme.
Scoped container queries are acceptable. Viewport media queries should stay
simple and preserve mobile reading.

Do not scale font size directly with viewport width alone. Use stable type
tokens or `clamp()` values with readable minimums and maximums. Letter spacing
should generally remain `0`, except for small uppercase labels where modest
positive tracking may help.

Ensure text fits inside buttons, labels, cards, captions, and panels. Long
words or names should wrap gracefully. Text must not overlap images or adjacent
UI.

Accessibility And Robustness
----------------------------

Use logical heading order, real text for labels and notes, and useful `alt`
text for meaningful images. Decorative images may use empty alt text, but
important visual information should not be decorative.

Avoid script-only interaction. The page must remain useful as a static local
HTML file. Avoid layouts that split a single figure, shot card, grid, or major
comparison awkwardly across PDF pages when simple CSS can prevent it.

Body Style Block Rules
----------------------

If a style block is included, put it near the top of the fragment:

```html
<style data-moodboard-theme>
  @layer theme, components;
</style>
```

Scope the style block to generated body classes. It may define local tokens for
color, spacing, radius, type, shadows, surfaces, and aspect ratios, but must not
depend on editing the document head. Use CSS layers only when they keep the
style block clearer.

Quality Bar
-----------

Before returning the body fragment, check that it is body-only HTML; core
content is visible without JavaScript; the page is a visual planning interface;
the structure comes from the current project rather than a repeated template;
important design dimensions are expressed intentionally and unsupported
dimensions are omitted; primary image layouts form complete rectangles, clean
bands, authored stacks, or deliberate asymmetry; image frames have stable aspect
ratios, dimensions, or grid tracks; images have useful alt text and
interpretive captions where needed; the final reference audit layer appears
when the source set is large enough to benefit from coverage review; class names
are semantic; text does not overlap images or adjacent UI; and layout remains
readable across phone, tablet, desktop, and reasonable PDF export.
