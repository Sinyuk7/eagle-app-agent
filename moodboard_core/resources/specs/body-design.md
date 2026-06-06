Moodboard body design contract
==============================

Generate only an HTML body fragment. Do not generate `<!doctype>`, `<html>`,
`<head>`, `<body>`, closing document tags, meta tags, viewport tags, or global
shell code. The CLI owns the full document shell and inserts this fragment into
the project `index.html`.

The fragment may include one first-level `<style data-moodboard-theme>` block
when project-specific visual styling is needed. Keep styles scoped to the body
content and avoid relying on document-head edits.

Design the body as a long-scroll visual planning page for photography,
editorial portraits, cosplay/IP-inspired shoots, storyboards, or visual concept
development. Make it readable on phone, tablet, and desktop, with careful
spacing, clear hierarchy, and reasonable PDF export behavior.

Do not impose a fixed heading set, fixed table schema, or checklist format.
Choose the structure that fits the project: anchor images, mood clusters, pose
studies, lens language, color scripts, styling cues, motif studies, sequence
rhythm, contrast maps, or reference essays are all acceptable.

Center the page on images, mood, lens language, framing, rhythm, pose,
movement, color, styling, motifs, details, main images, pause images,
close-ups, and sequence flow. Gear, logistics, budget, and operations should
appear only when they directly affect visual execution.

Use `<img>` elements for visual references when helpful. The `src` may be a
project-relative path, local absolute path, `file://` URI, or remote URL. During
`moodboard body apply`, the CLI normalizes local image references into stable
project-relative assets. Remote URLs are kept remote in this version.

Every meaningful image must have useful `alt` text. Avoid empty `src`, duplicate
IDs, broken fragment links, and layout choices that rely on external scripts.
