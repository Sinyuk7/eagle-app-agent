Moodboard body design contract
==============================

Purpose
-------

Generate only an HTML body fragment. Do not generate `<!doctype>`, `<html>`,
`<head>`, `<body>`, closing document tags, meta tags, viewport tags, or global
shell code. The CLI owns the full document shell and inserts this fragment into
the project `index.html`.

This contract is a body-spec for moodboard pages. It governs how creative
content is expressed as a webpage UI and visual planning interface. It does not
decide the creative content itself.

The body-spec may say:

- When content includes mood contrast, express it with a two-dimensional mood
  axis or a contrast map.
- When content includes palette percentages, express them with proportional
  color swatches.
- When content includes sequence, shot rhythm, or narrative order, express it
  with a horizontal or vertical time lane.

The body-spec must not say that a specific project should be rainy, neon,
lonely, green, romantic, cinematic, harsh, soft, or any other creative
direction. Those judgements belong to the moodboard reasoning step.

Output Boundary
---------------

Return a body-only HTML fragment that can be injected into an existing document.

Allowed:

- One first-level `<style data-moodboard-theme>` block when project-specific
  visual styling is needed.
- Semantic body content such as `<main>`, `<section>`, `<article>`, `<figure>`,
  `<figcaption>`, `<aside>`, `<blockquote>`, `<ol>`, `<ul>`, and tables only
  when tabular comparison is genuinely the clearest form.
- Project-relative image paths, local absolute paths, `file://` URIs, or remote
  URLs in `<img src>`. The CLI normalizes local image references during output
  writing.

Disallowed:

- Full-document tags, document metadata, viewport tags, or document-head edits.
- External JavaScript, script-dependent interaction, auto-playing carousels, or
  UI that hides core content behind controls.
- Empty image sources, duplicate IDs, broken fragment links, and anchors that
  point nowhere.
- Fixed content taxonomies that force every project into the same sections.
- Long production logistics, budgets, call sheets, or operations planning unless
  a detail directly changes the visual execution.

Page Role
---------

Design the body as a long-scroll visual planning page for photography,
editorial portraits, cosplay/IP-inspired shoots, storyboards, visual concept
development, and creative exploration.

The page should read as a visual planning interface or digital editorial board,
not as a Markdown note, generic landing page, static checklist, gallery dump, or
documentation site. It should help a viewer understand how to look, shoot,
compose, pace, color, style, and sequence the project.

Center the page on images, mood, lens language, framing, rhythm, pose,
movement, color, styling, motifs, details, main images, pause images,
close-ups, and sequence flow. Gear, logistics, budget, and operations should
appear only when they directly affect visual execution.

Design Principles
-----------------

Use editorial flow rather than a stack of identical cards. Each major section
must have a clear visual task such as setting the tone, comparing moods,
showing references, translating references into execution, breaking down color,
mapping movement, pacing a sequence, or closing with a distilled direction.

Do not impose a fixed heading set, fixed table schema, or checklist format.
Choose the structure that fits the project: anchor images, mood clusters, pose
studies, lens language, color scripts, styling cues, motif studies, sequence
rhythm, contrast maps, or reference essays are all acceptable.

Use at least two or three visual rhythms on substantial pages. Combine large
image impact, dense reference reading, quiet prose, compact comparison cards,
axis diagrams, color strips, and sequence lanes as the content requires.

Cards are for short, peer-level, comparable information. Use prose, pull quotes,
image-led sections, or diagrams for long aesthetic reasoning. Avoid turning
every section into `title + paragraph + three cards`.

Visual hierarchy should be obvious at a glance on phone, tablet, and desktop:
large anchors for the most important idea, medium panels for supporting
clusters, compact elements for labels, notes, and metadata.

Component Selection Grammar
---------------------------

Choose visual components from the structure of the content, not from a fixed
template.

Use a hero or title sequence when the content has one dominant visual premise,
anchor image, title, or opening mood. The hero should establish tone quickly and
may use one strong image, a large typographic statement, and a small amount of
supporting context.

Use a rhythm grid when the content has three to six references with clear visual
priority. Give explicit semantic classes such as `is-lead`, `is-wide`,
`is-tall`, `is-quiet`, or `is-accent`; do not rely on `:nth-child()` to decide
which item is important.

Use a reference wall when the content contains many equal-status references
that need to be scanned together. Keep each reference compact and make each
caption explain the transferable use of the image.

Use a detail strip when the content is about small visual cues: makeup, hair,
fabric, props, gestures, hands, accessories, light fragments, surface texture,
or local color. A horizontal scroll-snap strip is acceptable for many equal
references, but key content should remain visible somewhere on the page.

Use a mood axis when the content contains tension, contrast, or two dimensions
of feeling. Label the axes with content-derived poles and place cues, looks,
shots, or references in relation to those poles.

Use a contrast map when the content compares opposing visual treatments:
hard/soft, public/private, still/moving, warm/cool, polished/raw,
graphic/organic, distance/intimacy, or similar pairs.

Use proportional color swatches when the content includes palette weights,
dominant/accent relationships, or approximate percentages. Encode the ratio in
width or area, not just in repeated equal blocks.

Use a simple swatch row when the content has a palette but no reliable
percentage information. Five to seven colors is usually enough. Prefer semantic
names such as `shadow blue`, `skin warmth`, `signal red`, or `concrete gray`
over bare hex values.

Use a time lane when the content contains time, narrative order, shooting
sequence, emotional progression, scene order, or shot rhythm. The lane may be
horizontal for scanable stages or vertical for a more editorial long-scroll
story.

Use a shot map when the content translates references into executable frames:
framing, action, distance, crop, lens language, light direction, pose, movement,
or foreground/background relationships.

Use a bento or mixed grid only when the content has mixed media types and clear
relative importance: one dominant reference, supporting details, small text
signals, palette chips, or micro-notes. Do not use nested cards.

Use pull quotes or large typography when the content has a concise creative
principle, but do not use oversized type for ordinary body copy or small panel
headings.

Image Use
---------

Use `<img>` elements for visual references when helpful. Every meaningful image
must have useful `alt` text. Decorative overlays should not replace useful alt
text on the underlying reference.

Choose image layouts by reading role:

- Hero image: one dominant image for tone and first impression.
- Rhythm grid: a small set of references with deliberate scale differences.
- Reference wall: many peer references for comparison and extraction.
- Detail strip: small local cues and repeated close-up evidence.
- Paired comparison: two images or panels that clarify contrast.
- Sequence frames: ordered images that show progression or shot rhythm.

Use `<figure>` and `<figcaption>` for references that need interpretation.
Captions should explain what the reference is used for, not merely describe what
is visible. A useful caption answers: what is borrowed, how it transfers, and
what to watch during execution.

Avoid vague captions such as `nice mood`, `cinematic`, `beautiful reference`,
or `good lighting`. Prefer action-oriented captions such as `low angle with
compressed background; use the fence as a distance layer` or `warm edge light
only on hair and hands; keep the face mostly neutral`.

When references come from different sources with inconsistent color, use scoped
CSS treatment such as subtle overlays, shared borders, or restrained filters to
make the board cohesive. Do not make filtering so strong that the reference
becomes misleading.

Color Expression
----------------

Color UI must behave like a planning tool, not decoration.

When palette ratios are known or inferred, use proportional swatches. A dominant
environment color should occupy more space than a minor accent. When exact
percentages are unknown, communicate relative weight with labels such as
`dominant`, `support`, `skin/highlight`, and `accent`.

Each key color should carry a semantic role and a practical use. Good examples:
`background shadow`, `skin warmth`, `signal accent`, `metal highlight`,
`wardrobe base`, `prop color`, `negative space`, or `transition tone`.

Where useful, map the palette to CSS variables in the body-scoped style block so
the page's interface and the shoot palette feel connected. Keep the mapping
local to the generated body.

Sequence And Rhythm
-------------------

When the content includes a beginning, middle, ending, transformation, scene
order, time of day, or shot progression, express it visually. Do not reduce it
to a plain list unless the sequence is minor.

A time lane should make order visible through position, numbering, linework,
spacing, or alternating panels. It may include images, short stage names,
movement notes, light changes, color shifts, or framing cues.

A shot rhythm section should show variation. Use a mix of wide, medium, close,
detail, pause, transition, and climax frames when the content supports it. Make
the pacing readable without requiring long prose.

Mood And Contrast
-----------------

When the content contains emotional opposition, build a mood axis, contrast
map, paired comparison, or gradient section. The component should make the
tension spatially visible.

Mood components should not invent new content. Axis labels, poles, placements,
and notes must be derived from the creative reasoning already available for the
project.

Layout Language
---------------

Use semantic, reusable class names that describe component role, not project
identity. Prefer names such as `.moodboard-canvas`, `.section-shell`,
`.hero-sequence`, `.rhythm-grid`, `.reference-wall`, `.detail-strip`,
`.time-lane`, `.mood-axis`, `.shot-map`, `.color-script`, `.palette-band`,
`.signal-card`, `.section-kicker`, and `.caption-note`.

Avoid project-specific class names such as `.ran-board` or `.neon-rain-card`
inside a reusable body unless the project identity truly needs a one-off hook.

Avoid using `:nth-child()` as the main way to assign layout roles. Add explicit
semantic classes in the markup instead. This makes generated pages easier to
audit and revise.

Use stable dimensions for fixed-format UI elements. Image boxes, strips, grids,
tiles, counters, labels, and compact panels should have predictable aspect
ratios, min/max sizes, or grid tracks so content changes do not collapse the
layout.

Do not place UI cards inside other cards. Page sections should be full-width
bands or unframed layouts with constrained inner content. Cards are acceptable
for repeated items, compact comparisons, shot cards, reference items, and
modal-like framed tools.

Horizontal scroll is acceptable only for peer references or detail strips. Do
not hide the primary idea, sequence, or final direction inside a carousel.

Responsive Behavior
-------------------

The body must be readable on phone, tablet, and desktop. Use responsive grid,
container-aware layout, flexible spacing, and stable aspect ratios.

Prefer component-local layout logic over a single global breakpoint scheme.
When using container queries, keep them scoped to generated components. If using
viewport media queries, keep them simple and verify that mobile reading remains
clear.

Do not scale font size directly with viewport width alone. Use stable type
tokens or `clamp()` values with readable minimums and maximums. Letter spacing
should generally remain `0`, except for small uppercase labels where modest
positive tracking may help.

Ensure text fits within buttons, labels, cards, captions, and panels. Long words
or names should wrap gracefully. Text must not overlap images or adjacent UI in
an incoherent way.

Dark And Light Themes
---------------------

Dark pages need clear layer separation. Use distinct surface levels, section
background shifts, line strength, captions, and accent rules so panels do not
collapse into one dark field.

Light pages need sufficient contrast and should not become a bland white
document. Use controlled surfaces, strong image rhythm, subtle lines, and clear
type hierarchy.

Avoid one-note palettes in the UI. The page may respect the project's palette,
but the interface still needs enough contrast, neutral structure, and hierarchy
to be readable.

Accessibility And Robustness
----------------------------

Every meaningful image must have useful `alt` text. Images used only as
decorative texture may use empty alt text, but avoid making important visual
information decorative.

Use headings in a logical order when possible. Do not choose heading levels only
for visual size; style headings with CSS instead.

Use real text for labels, captions, and notes. Do not bake essential text into
images.

Avoid script-only interaction. The final page must remain useful when opened as
a static local HTML file.

Reasonable PDF export behavior matters. Avoid layouts that split a single
figure, shot card, or major comparison awkwardly across pages when simple CSS
can prevent it.

Body Style Block Rules
----------------------

If a style block is included, put it near the top of the fragment:

```html
<style data-moodboard-theme>
  @layer theme, components;
</style>
```

The style block should be scoped to generated body classes. It may define local
tokens for color, spacing, radius, type, shadows, surfaces, and aspect ratios.
It should not depend on editing the document head.

Use CSS layers when helpful, but do not require them if a smaller scoped style
block is clearer. Keep selectors understandable and avoid global resets beyond
the body fragment's root class.

Minimal Body Shape
------------------

There is no required section list, but a strong body normally has:

- A root `<main>` with a stable class such as `.moodboard-canvas` or
  `.moodboard-page`.
- A first visual anchor that establishes the page's direction.
- One or more sections that translate references into visual decisions.
- Image-led evidence where images are available.
- A readable closing or synthesis when the project benefits from one.

The exact sections, labels, and components should come from the project
material.

Quality Bar
-----------

Before returning the body fragment, check that:

- The result is body-only HTML.
- Core content is visible without JavaScript.
- The page is a visual planning interface, not a generic note.
- Component choices match content structure.
- Images have useful alt text and captions where interpretation is needed.
- Captions explain usage rather than only appearance.
- Palette, sequence, mood, and shot components appear only when the content
  supports them.
- Class names are semantic and reusable.
- Layout remains readable across phone, tablet, desktop, and reasonable PDF
  export.
