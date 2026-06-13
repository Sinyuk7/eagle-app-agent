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
or any other aesthetic direction.

The spec may require visual forms for known structures: mood contrast becomes a
mood axis, contrast map, or paired comparison; palette weights become
proportional swatches; sequence or shot rhythm becomes a time lane or ordered
frame system; image sets become grids, walls, strips, comparisons, or sequence
frames according to role.

Output Boundary
---------------

Return body-only HTML that can be injected into an existing document.

Allowed: one first-level `<style data-moodboard-theme>` block; semantic body
content such as `<main>`, `<section>`, `<article>`, `<figure>`,
`<figcaption>`, `<aside>`, `<blockquote>`, `<ol>`, `<ul>`, and tables only
when tabular comparison is clearest; project-relative image paths, local
absolute paths, `file://` URIs, or remote URLs in `<img src>`.

Disallowed: full-document tags, metadata, viewport tags, document-head edits,
external JavaScript, script-dependent interaction, autoplaying carousels, hidden
core content, empty image sources, duplicate IDs, broken links, fixed
taxonomies, and long logistics unless they directly change visual execution.

Page Role
---------

Design a long-scroll visual planning page for photography, editorial portraits,
cosplay/IP-inspired shoots, storyboards, visual concept development, and
creative exploration.

The page should feel like a visual planning interface or digital editorial
board, not a Markdown note, landing page, static checklist, gallery dump, or
documentation site. It should help viewers understand how to look, shoot,
compose, pace, color, style, and sequence the project.

Center the page on images, mood, lens language, framing, rhythm, pose,
movement, color, styling, motifs, details, main images, pause images,
close-ups, and sequence flow. Mention gear, logistics, budget, or operations
only when they directly affect the image.

Design Principles
-----------------

Use editorial flow instead of identical cards. Each major section must have a
clear visual task: establish tone, compare moods, show references, translate
references into execution, break down color, map movement, pace a sequence, or
close with a distilled direction.

Choose structure from the project material rather than a fixed heading set.
Valid structures include anchor images, mood clusters, pose studies, lens
language, color scripts, styling cues, motif studies, sequence rhythm, contrast
maps, and reference essays.

Substantial pages should combine at least two or three rhythms: large image
impact, dense reference reading, quiet prose, compact comparison cards, axis
diagrams, color strips, sequence lanes, or shot maps.

Cards are for short peer-level comparisons. Use prose, pull quotes, image-led
sections, or diagrams for long aesthetic reasoning. Avoid making every section
`title + paragraph + three cards`.

Visual hierarchy must be obvious on phone, tablet, and desktop: large anchors
for primary ideas, medium panels for supporting clusters, compact elements for
labels, notes, and metadata.

Component Grammar
-----------------

Choose components by content role, not template habit:

- Hero or title sequence: one dominant premise, anchor image, title, or opening
  mood.
- Rhythm grid: three to six references with clear priority. Mark items with
  semantic classes such as `is-lead`, `is-wide`, `is-tall`, `is-quiet`, or
  `is-accent`.
- Reference wall: many equal-status references scanned together, with compact
  transferable captions.
- Detail strip: makeup, hair, fabric, props, gestures, hands, accessories,
  light fragments, surface texture, or local color.
- Mood axis or contrast map: content-derived emotional poles or opposing visual
  treatments.
- Proportional swatches: known or inferred palette weights. Simple swatch rows
  are enough when percentages are unreliable.
- Time lane: time, narrative order, shoot sequence, emotional progression,
  scene order, or shot rhythm.
- Shot map: executable frames describing crop, action, distance, lens language,
  light direction, pose, movement, or foreground/background relationships.
- Bento or mixed grid: mixed media with clear relative importance. Do not nest
  cards.
- Pull quote or large type: concise creative principle only, not ordinary body
  copy or panel headings.

Grid And Image Layout
---------------------

Image layout is part of the concept. Before placing images, define the layout
system: component role, column count, row rhythm, tile aspect ratios, gaps, and
semantic priority.

Use CSS Grid for primary image groups that need two-dimensional order. Grid
tracks, gutters, and explicit spans make rows, columns, priority, and reading
order auditable. Use Flexbox for one-dimensional strips. Do not use CSS columns
or masonry-style flows for primary concept, sequence, or rhythm sections.

Every primary image group must resolve into an intentional rectangle or clean
band. Avoid ragged right edges, accidental holes, orphan tiles, and uneven
bottom edges unless the asymmetry is deliberate and content-led. Close uneven
counts with a lead tile, wide tile, text note, palette module, or controlled
negative-space panel.

Set stable media geometry before images load: use explicit `aspect-ratio`
values or grid row spans; include `width` and `height` when known; constrain
media with `max-inline-size: 100%` and `block-size: auto`; use
`object-fit: cover` for intentional editorial crops and `object-fit: contain`
only when the full reference must remain visible; set `object-position` when
faces, hands, props, or composition lines must not be cropped accidentally.

Use named layout roles instead of `:nth-child()` placement. Mark which image is
lead, wide, tall, quiet, accent, pause, detail, or climax, then map those roles
to grid spans and aspect ratios.

Keep repeated grids coherent: one gap scale per component; a limited aspect
ratio set such as `16 / 9`, `4 / 3`, `3 / 4`, `1 / 1`, or `2 / 3`; no random
mix of unrelated proportions; captions that do not unpredictably resize tiles;
compact text placed in a fixed caption area, overlay band, or note column.

Masonry is allowed only as a secondary reference wall when abundance is the
point, items are equal-status, reading order is not semantic, and the fallback
still looks coherent. Do not rely on experimental native masonry as the default
layout.

Image Use
---------

Use `<img>` for visual references. Every meaningful image needs useful `alt`
text, and decorative overlays must not replace the underlying alt text.

Choose layouts by role: hero image for one dominant first impression; rhythm
grid for deliberate scale differences; reference wall for peer comparison;
detail strip for close-up evidence; paired comparison for contrast; sequence
frames for progression or shot rhythm.

Use `<figure>` and `<figcaption>` when interpretation is needed. Captions
should say what is borrowed, how it transfers, and what to watch during
execution, not merely describe appearance. Avoid vague captions such as
`nice mood`, `cinematic`, `beautiful reference`, or `good lighting`.

When references vary by source, use subtle scoped treatment such as shared
borders, restrained filters, overlays, or consistent frame geometry. Do not
filter so strongly that references become misleading.

Color Expression
----------------

Color UI must behave like a planning tool. Use proportional swatches when
palette ratios are known or inferred; otherwise label relative weight such as
`dominant`, `support`, `skin/highlight`, and `accent`.

Each key color should carry a semantic role and practical use, such as
`background shadow`, `skin warmth`, `signal accent`, `metal highlight`,
`wardrobe base`, `prop color`, `negative space`, or `transition tone`.

Where useful, map the palette to local CSS variables so the interface and shoot
palette feel connected. Keep the mapping scoped to the generated body.

Sequence, Mood, And Contrast
----------------------------

When content includes a beginning, middle, ending, transformation, scene order,
time of day, or shot progression, express it visually rather than as a plain
list.

A time lane should make order visible through position, numbering, linework,
spacing, or alternating panels. A shot rhythm section should vary wide, medium,
close, detail, pause, transition, and climax frames when supported.

When content contains emotional opposition, build a mood axis, contrast map,
paired comparison, or gradient section that makes the tension spatially
visible. Axis labels, poles, placements, and notes must come from the creative
reasoning already available for the project.

Layout Language
---------------

Use semantic reusable class names that describe component role, not project
identity. Prefer `.moodboard-canvas`, `.section-shell`, `.hero-sequence`,
`.rhythm-grid`, `.reference-wall`, `.detail-strip`, `.time-lane`, `.mood-axis`,
`.shot-map`, `.color-script`, `.palette-band`, `.signal-card`,
`.section-kicker`, and `.caption-note`.

Avoid project-specific class names unless identity truly needs a one-off hook.
Use stable dimensions for image boxes, strips, grids, tiles, counters, labels,
and compact panels. Do not place cards inside cards. Page sections should be
full-width bands or unframed layouts with constrained inner content. Cards are
acceptable for repeated items, compact comparisons, shot cards, reference
items, and modal-like framed tools.

Horizontal scroll is acceptable only for peer references or detail strips. Do
not hide the primary idea, sequence, or final direction inside a carousel.

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

Themes, Accessibility, And Robustness
-------------------------------------

Dark pages need clear layer separation through surface levels, section
background shifts, line strength, captions, and accent rules. Light pages need
contrast, controlled surfaces, strong image rhythm, subtle lines, and clear
type hierarchy. Avoid one-note UI palettes even when respecting the project's
palette.

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
color, spacing, radius, type, shadows, surfaces, and aspect ratios, but must
not depend on editing the document head. Use CSS layers only when they keep the
style block clearer.

Minimal Body Shape
------------------

There is no required section list, but a strong body normally has a root
`<main>` with a stable class such as `.moodboard-canvas` or `.moodboard-page`,
a first visual anchor, sections that translate references into visual
decisions, image-led evidence where available, and a readable closing or
synthesis when useful.

The exact sections, labels, and components must come from the project material.

Quality Bar
-----------

Before returning the body fragment, check that it is body-only HTML; core
content is visible without JavaScript; the page is a visual planning interface;
component choices match content structure; primary image layouts form complete
rectangles or clean bands; image frames have stable aspect ratios, dimensions,
or grid tracks; images have useful alt text and interpretive captions where
needed; palette, sequence, mood, and shot components appear only when
supported; class names are semantic and reusable; text does not overlap images
or adjacent UI; and layout remains readable across phone, tablet, desktop, and
reasonable PDF export.
