# Mimir Source — Generative Art

Gallery-grade algorithmic art for Mimir displays, rendered locally with
Pillow + NumPy. No external APIs, no keys, works offline.

## Styles

| Style | Look |
|---|---|
| **Kyoto Bauhaus** (`wabi`) | Bauhaus structure with a Wabi-Sabi finish — soft geometric arches, sand-textured curves, fine ink lines. Muted terracotta, raw linen oat, deep charcoal, soft sage on heavyweight cotton paper with giclée grain. |
| **Riso Constructivist '66** (`constructivist`) | Bold 1960s constructivism — hard-edge geometry, mathematical grids, rhythmic curves and sharp angles. Mustard, deep teal, burnt orange risograph inks overprinted on warm cream with registration error and tactile grain. |
| **Phosphor Terminal** (`phosphor`) | Every element rebuilt from ASCII characters on a near-black CRT — a glyph density ramp in glowing Mimir green, with scanlines and phosphor bloom. |
| **Blueprint Cyanotype** (`blueprint`) | Draftsman's cyanotype — pale washes and near-white line work on deep Prussian blue paper with brush dropout and sun-faded vignette. |
| **Neon Dusk** (`neon`) | Synthwave — hot pink, electric cyan and violet light-forms blooming on deep indigo. Made for OLED; pairs well with animated output. |
| **Ben-Day Pop** (`popart`) | Comic-press pop art — primary fills printed as Ben-Day dot fields under solid black line work, with newsstand plate misregistration. |
| **Morning Watercolor** (`watercolor`) | Translucent washes with wet bleeding edges that pool darker at their rims, pigment granulation, cold-press paper tooth. |
| **Gilded Deco** (`deco`) | Art Deco nocturne — gold leaf, brass and champagne glowing on warm black lacquer with hand-gilding mottle. |

Set style to **`random`** to get a different style with every piece (the
pick is seed-stable, so a fixed seed always reproduces the same artwork).

Light-emitting styles (`phosphor`, `blueprint`, `neon`) composite with a
*screen* blend (light adds up) instead of the print styles' transmittance
multiply (ink soaks in).

## Algorithms

Six composition engines, all available in both styles (`auto` picks per piece):

- `arches` — Arch Study: soft geometric arches on a staggered baseline grid
- `flowfield` — Sand Currents: fine algorithmic curves through a noise field
- `inkweave` — Ink Weave: intersecting fine ink lines over sparse blocks
- `orbits` — Orbit Rhythm: rhythmic concentric arcs around one or two poles
- `tatami` — Tatami Grid: recursive golden-ratio subdivision, mostly negative space
- `beams` — Signal Beams: sharp-angle rays fanning from the frame edges
- `hexgrid` — Honeycomb: a hex grid field with sparse filled cells and concentric hex targets
- `interference` — Standing Waves: wavefronts from point sources weaving real moiré interference fringes; animated, the waves travel outward
- `flora` — Quiet Meadow: abstract nature scene — layered noise hills, a low sun, swaying botanical sprigs and drifting birds
- `truchet` — Truchet Maze: quarter-circle arc tiles weaving endless paths; animated, tiles turn in place and rewire the maze
- `contours` — Contour Map: marching-squares elevation lines over a noise heightfield; animated, the contours flow like a rising tide
- `harmonograph` — Harmonograph: decaying detuned pendulum curves in fine plotter ink, continuously re-blooming in animation
- `glyphrain` — Glyph Rain: falling streak columns at three parallax speeds — literal Matrix rain in the phosphor style

## Output modes

- **static** — lossless PNG. Use for e-ink displays (and anywhere else).
- **animated** — seamless looping animated WebP. LCD/OLED only; e-ink
  displays can't animate. Engines treat animation phase cyclically so the
  loop closes without a seam.

## Seed modes

`refresh` (new piece every display refresh) · `hourly` · `daily` ·
`fixed` (pin one composition by seed).

## Galleries

A **gallery** is one named, saved configuration — style, algorithm, output
mode, seed policy, density, texture — the plugin's sub-channel. Create as
many as you like from the channel manager and assign different galleries
to different programs and displays (a calm watercolor meadow in one room,
glowing ASCII waves on another OLED). The manager shows a first-run
explainer with a "Create Your First Gallery" button when none exist yet.

`request_image` resolves which gallery to render from the caller's
`subchannel_id` / `gallery_id` / `settings.subChannelId`, falling back to
the first configured gallery.

## Architecture

Engines compose pieces as *ink plates* (grayscale masks per palette slot);
the renderer prints the plates in the active style — transmittance
overprint blending, per-plate registration offsets and ink-coverage noise
for risograph, soft edges and cotton-rag grain for giclée. This keeps
every algorithm compatible with every style.

## Tests

```bash
pip install -r requirements.txt
pytest tests/
```
