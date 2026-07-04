"""Composition engines for the Generative Art channel.

An engine is an algorithm that composes a piece as a stack of *ink plates*:

    Plate = (ink_index, mask, coverage)

      ink_index — which palette slot of the active Style to print with
      mask      — PIL "L" image; 255 = full ink, 0 = bare paper
      coverage  — 0..1 multiplier on the style's ink opacity

Plates are returned bottom-to-top in print order. Engines draw pure
composition — all material treatment (edge softness, registration error,
ink-coverage noise, paper texture) is applied by the renderer according to
the active Style, so every engine renders correctly in every style.

Engines receive a seeded ``random.Random`` so a given (seed, size) pair is
fully reproducible, and a cyclic ``phase`` in [0, 1) for animation — all
motion is periodic in phase so animated loops close seamlessly.
"""
from __future__ import annotations

import math
import random
from typing import Callable

from PIL import Image, ImageDraw

from .styles import Style

Plate = tuple[int, Image.Image, float]

TWO_PI = math.tau


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mask(w: int, h: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("L", (w, h), 0)
    return img, ImageDraw.Draw(img)


def _value_noise(rng: random.Random) -> Callable[[float, float], float]:
    """Smooth 2-D value noise in [0, 1], seeded from *rng*."""
    perm = list(range(256))
    rng.shuffle(perm)
    perm = perm * 2

    def fade(t: float) -> float:
        return t * t * (3.0 - 2.0 * t)

    def noise(x: float, y: float) -> float:
        xf0, yf0 = math.floor(x), math.floor(y)
        xi, yi = int(xf0) & 255, int(yf0) & 255
        dx, dy = x - xf0, y - yf0

        def corner(cx: int, cy: int) -> float:
            return perm[perm[cx & 255] + (cy & 255)] / 255.0

        u, v = fade(dx), fade(dy)
        top = corner(xi, yi) * (1 - u) + corner(xi + 1, yi) * u
        bot = corner(xi, yi + 1) * (1 - u) + corner(xi + 1, yi + 1) * u
        return top * (1 - v) + bot * v

    return noise


def _osc(phase: float, offset: float = 0.0) -> float:
    """Cyclic oscillator in [-1, 1]; period 1 in phase → seamless loops."""
    return math.sin(TWO_PI * (phase + offset))


def _pulse(phase: float, offset: float, window: float) -> float:
    """One smooth 0→1 transition per loop, then hold at 1.

    Used for motions where the end state is visually identical to the start
    (e.g. a 180° turn of a symmetric motif) — each element fires once per
    loop inside its own window, and the wrap is seamless because held-at-1
    looks exactly like 0."""
    t = (phase - offset) % 1.0
    if t >= window:
        return 1.0
    u = t / window
    return u * u * (3.0 - 2.0 * u)


# ── Engine: arches ───────────────────────────────────────────────────────────

def arches(rng: random.Random, style: Style, w: int, h: int,
           phase: float, density: float) -> list[Plate]:
    """Soft geometric arches on a loose baseline grid.

    Rounded arch forms (Bauhaus doorways) rise from staggered baselines,
    overlapping where the grid allows; a thin ground rule and one small
    charcoal accent arch anchor the composition.
    """
    d = density * style.density_bias
    n = max(3, round(4 * d) + rng.randint(0, 2))
    margin = 0.08 * min(w, h)
    baseline_lo, baseline_hi = 0.55 * h, 0.92 * h

    color_masks: dict[int, Image.Image] = {}
    draws: dict[int, ImageDraw.ImageDraw] = {}
    body_inks = [0, 1, 2]

    def draw_for(ink: int) -> ImageDraw.ImageDraw:
        if ink not in color_masks:
            color_masks[ink], draws[ink] = _mask(w, h)
        return draws[ink]

    # Loose columns so arches cluster and overlap rather than scatter.
    slots = [margin + (w - 2 * margin) * (i + rng.uniform(0.05, 0.85)) / n
             for i in range(n)]
    rng.shuffle(slots)

    for i, cx in enumerate(slots):
        aw = rng.uniform(0.14, 0.34) * w * (1.25 - 0.5 * (d > 1))
        # The stem needs room below the half-disc cap: keep height ≥ the cap.
        ah = max(rng.uniform(0.22, 0.55) * h, 0.62 * aw)
        baseline = rng.uniform(baseline_lo, baseline_hi)
        bob = 0.012 * h * _osc(phase, i / max(1, n))
        top = baseline - ah + bob
        ink = body_inks[i % len(body_inks)]
        dr = draw_for(ink)
        x0, x1 = cx - aw / 2, cx + aw / 2
        # Arch = half-disc cap + rectangular stem.
        dr.pieslice([x0, top, x1, top + aw], 180, 360, fill=255)
        dr.rectangle([x0, top + aw / 2, x1, baseline + bob], fill=255)

    # Small accent arch — deliberate, sparse.
    acc_mask, acc_draw = _mask(w, h)
    aw = rng.uniform(0.05, 0.09) * w
    cx = rng.uniform(0.2, 0.8) * w
    baseline = rng.uniform(baseline_lo, baseline_hi)
    top = baseline - max(rng.uniform(0.08, 0.16) * h, 0.62 * aw)
    acc_draw.pieslice([cx - aw / 2, top, cx + aw / 2, top + aw], 180, 360, fill=255)
    acc_draw.rectangle([cx - aw / 2, top + aw / 2, cx + aw / 2, baseline], fill=255)

    # Ground rule.
    line_mask, line_draw = _mask(w, h)
    rule_y = baseline_hi + 0.02 * h
    lw = max(2, round(0.0022 * min(w, h)))
    line_draw.line([(margin, rule_y), (w - margin, rule_y)], fill=255, width=lw)

    plates: list[Plate] = [(ink, m, 1.0) for ink, m in color_masks.items()]
    plates.append((style.accent_index, acc_mask, 1.0))
    plates.append((style.line_index, line_mask, 0.9))
    return plates


# ── Engine: flowfield ────────────────────────────────────────────────────────

def flowfield(rng: random.Random, style: Style, w: int, h: int,
              phase: float, density: float) -> list[Plate]:
    """Flowing algorithmic curves traced through a smooth noise field.

    Fine sand-textured strands in banded ink bundles drift across the frame;
    the field angle is modulated cyclically so animation loops.
    """
    d = density * style.density_bias
    noise = _value_noise(rng)
    # A handful of noise cells across the frame gives long dune-like swells;
    # higher frequencies degrade into per-pixel scribble.
    ns = rng.uniform(2.2, 4.5) / max(w, h)
    base_angle = rng.uniform(0, TWO_PI)
    hard_edge = style.edge_blur < 1.0
    strands = max(24, round((70 if hard_edge else 210) * d))
    width_lo, width_hi = ((0.004, 0.010) if hard_edge else (0.0012, 0.0032))
    step = 0.011 * max(w, h)
    steps = round(1.35 * max(w, h) / step)

    bundles = [0, 1, 2]
    masks: dict[int, Image.Image] = {}
    draws: dict[int, ImageDraw.ImageDraw] = {}
    for b in bundles:
        masks[b], draws[b] = _mask(w, h)

    for s in range(strands):
        band = min(len(bundles) - 1, int(len(bundles) * s / strands))
        ink = bundles[band]
        x = rng.uniform(-0.15, 1.15) * w
        y = (band + rng.uniform(-0.35, 1.35)) / len(bundles) * h
        pts = [(x, y)]
        wobble = rng.uniform(0.15, 0.4)
        for _ in range(steps):
            a = (base_angle
                 + (noise(x * ns, y * ns) - 0.5) * 2.6
                 + wobble * _osc(phase, x / w * 0.5))
            x += step * math.cos(a)
            y += step * math.sin(a) * 0.55  # flatten drift into dune-like bands
            pts.append((x, y))
        lw = max(1, round(rng.uniform(width_lo, width_hi) * max(w, h)))
        draws[ink].line(pts, fill=rng.randint(150, 255), width=lw, joint="curve")

    # One fine horizon hairline for structure.
    line_mask, line_draw = _mask(w, h)
    yline = rng.uniform(0.2, 0.8) * h
    line_draw.line([(0.06 * w, yline), (0.94 * w, yline)], fill=255,
                   width=max(1, round(0.0015 * min(w, h))))

    plates: list[Plate] = [(ink, masks[ink], 0.9) for ink in bundles]
    plates.append((style.line_index, line_mask, 0.8))
    return plates


# ── Engine: inkweave ─────────────────────────────────────────────────────────

def inkweave(rng: random.Random, style: Style, w: int, h: int,
             phase: float, density: float) -> list[Plate]:
    """Intersecting fine ink lines over sparse geometric blocks.

    Two or three families of parallel hairlines cross at deliberate angles;
    a few filled rectangles and quarter-discs sit beneath the weave on a
    mathematical grid. Line families slide one spacing per loop.
    """
    d = density * style.density_bias
    diag = math.hypot(w, h)

    # Blocks first (under the lines).
    block_masks: dict[int, Image.Image] = {}
    block_draws: dict[int, ImageDraw.ImageDraw] = {}
    cols, rows = rng.choice([(4, 3), (5, 3), (6, 4)])
    n_blocks = max(2, round(3 * d) + rng.randint(0, 2))
    cells = [(c, r) for c in range(cols) for r in range(rows)]
    rng.shuffle(cells)
    for c, r in cells[:n_blocks]:
        ink = rng.choice([0, 1, 2])
        if ink not in block_masks:
            block_masks[ink], block_draws[ink] = _mask(w, h)
        x0, y0 = c / cols * w, r / rows * h
        x1, y1 = (c + 1) / cols * w, (r + 1) / rows * h
        pad = 0.08 * (x1 - x0)
        kind = rng.random()
        if kind < 0.45:
            block_draws[ink].rectangle([x0 + pad, y0 + pad, x1 - pad, y1 - pad], fill=255)
        elif kind < 0.8:
            side = min(x1 - x0, y1 - y0) - 2 * pad
            qx, qy = x0 + pad, y0 + pad
            start, end = rng.choice([(0, 90), (90, 180), (180, 270), (270, 360)])
            block_draws[ink].pieslice([qx, qy, qx + 2 * side, qy + 2 * side], start, end, fill=255)
        else:
            cxc, cyc = (x0 + x1) / 2, (y0 + y1) / 2
            rr = (min(x1 - x0, y1 - y0) / 2) - pad
            block_draws[ink].ellipse([cxc - rr, cyc - rr, cxc + rr, cyc + rr], fill=255)

    # Line families.
    line_mask, line_draw = _mask(w, h)
    hairline = max(1, round(0.0016 * min(w, h)))
    n_families = 2 + (rng.random() < 0.35)
    angles = rng.sample([0, 90, rng.choice([30, 45, 60, 120, 135])], n_families)
    for fi, ang_deg in enumerate(angles):
        ang = math.radians(ang_deg)
        ux, uy = math.cos(ang), math.sin(ang)      # line direction
        nx, ny = -uy, ux                           # family normal
        spacing = rng.uniform(0.055, 0.13) * min(w, h) / max(0.6, d)
        count = int(diag / spacing) + 2
        slide = spacing * (phase if fi % 2 == 0 else -phase)  # one spacing per loop
        cx0, cy0 = w / 2, h / 2
        for k in range(-count // 2, count // 2 + 1):
            off = k * spacing + slide
            px, py = cx0 + nx * off, cy0 + ny * off
            half = diag * rng.uniform(0.2, 0.48)
            shift = diag * rng.uniform(-0.16, 0.16)
            p0 = (px + ux * (shift - half), py + uy * (shift - half))
            p1 = (px + ux * (shift + half), py + uy * (shift + half))
            lw = hairline * (3 if rng.random() < 0.04 else 1)
            line_draw.line([p0, p1], fill=255, width=lw)

    plates: list[Plate] = [(ink, m, 0.95) for ink, m in block_masks.items()]
    plates.append((style.line_index, line_mask, 0.85))
    return plates


# ── Engine: orbits ───────────────────────────────────────────────────────────

def orbits(rng: random.Random, style: Style, w: int, h: int,
           phase: float, density: float) -> list[Plate]:
    """Rhythmic concentric arcs around one or two poles.

    Hairline rings alternate with chunky ink arcs in strict radial rhythm;
    alternate rings counter-rotate a full turn per loop.
    """
    d = density * style.density_bias
    n_centers = 1 if rng.random() < 0.65 else 2
    line_mask, line_draw = _mask(w, h)
    ink_masks: dict[int, Image.Image] = {}
    ink_draws: dict[int, ImageDraw.ImageDraw] = {}

    for ci in range(n_centers):
        cx = rng.uniform(0.28, 0.72) * w if n_centers == 1 else (0.22 + 0.56 * ci) * w
        cy = rng.uniform(0.3, 0.7) * h
        rings = max(6, round(11 * d) + rng.randint(0, 4))
        r_step = rng.uniform(0.03, 0.05) * min(w, h)
        r0 = rng.uniform(0.5, 1.4) * r_step
        chunky_every = rng.choice([3, 4, 5])
        for k in range(rings):
            r = r0 + k * r_step * (1 + 0.12 * _osc(phase, k / rings) * 0)  # radius static
            box = [cx - r, cy - r, cx + r, cy + r]
            turn = 360.0 * phase * (1 if k % 2 == 0 else -1)   # integer turns → seamless
            start = rng.uniform(0, 360) + turn
            sweep = rng.uniform(50, 300)
            if k % chunky_every == chunky_every - 1:
                ink = rng.choice([0, 1, 2])
                if ink not in ink_masks:
                    ink_masks[ink], ink_draws[ink] = _mask(w, h)
                bw = max(3, round(r_step * rng.uniform(0.35, 0.6)))
                ink_draws[ink].arc(box, start, start + sweep, fill=255, width=bw)
            else:
                lw = max(1, round(0.0018 * min(w, h)))
                line_draw.arc(box, start, start + sweep, fill=255, width=lw)
        # Pole dot.
        pr = 0.012 * min(w, h)
        line_draw.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=255)

    plates: list[Plate] = [(ink, m, 1.0) for ink, m in ink_masks.items()]
    plates.append((style.line_index, line_mask, 0.85))
    return plates


# ── Engine: tatami ───────────────────────────────────────────────────────────

def tatami(rng: random.Random, style: Style, w: int, h: int,
           phase: float, density: float) -> list[Plate]:
    """Recursive grid subdivision with disciplined negative space.

    The frame divides at golden-ish ratios; most cells stay bare paper,
    a few fill with flat geometry, hairline rules trace the grid.
    """
    d = density * style.density_bias
    max_depth = 3 + (d > 0.9) + (d > 1.3)
    line_mask, line_draw = _mask(w, h)
    ink_masks: dict[int, Image.Image] = {}
    ink_draws: dict[int, ImageDraw.ImageDraw] = {}
    hairline = max(1, round(0.0016 * min(w, h)))
    margin = 0.06 * min(w, h)
    fill_p = 0.16 + 0.10 * d

    def fill_cell(x0: float, y0: float, x1: float, y1: float, idx: int) -> None:
        ink = rng.choice([0, 1, 2, style.accent_index])
        if ink not in ink_masks:
            ink_masks[ink], ink_draws[ink] = _mask(w, h)
        dr = ink_draws[ink]
        breathe = 1.0 + 0.03 * _osc(phase, idx * 0.17)
        cw, ch = (x1 - x0), (y1 - y0)
        pad = 0.06 * min(cw, ch) * breathe
        bx0, by0, bx1, by1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
        kind = rng.random()
        if kind < 0.4:
            dr.rectangle([bx0, by0, bx1, by1], fill=255)
        elif kind < 0.7:
            side = min(bx1 - bx0, by1 - by0)
            start, end = rng.choice([(0, 90), (90, 180), (180, 270), (270, 360)])
            corner = {(0, 90): (bx1 - 2 * side, by1 - 2 * side), (90, 180): (bx0, by1 - 2 * side),
                      (180, 270): (bx0, by0), (270, 360): (bx1 - 2 * side, by0)}[(start, end)]
            dr.pieslice([corner[0], corner[1], corner[0] + 2 * side, corner[1] + 2 * side],
                        start, end, fill=255)
        else:
            ccx, ccy = (bx0 + bx1) / 2, (by0 + by1) / 2
            rr = min(bx1 - bx0, by1 - by0) / 2
            dr.pieslice([ccx - rr, ccy - rr * 2 + rr, ccx + rr, ccy + rr], 180, 360, fill=255)

    cell_idx = 0

    def divide(x0: float, y0: float, x1: float, y1: float, depth: int) -> None:
        nonlocal cell_idx
        cw, ch = x1 - x0, y1 - y0
        if depth >= max_depth or min(cw, ch) < 0.12 * min(w, h):
            cell_idx += 1
            if rng.random() < fill_p:
                fill_cell(x0, y0, x1, y1, cell_idx)
            return
        ratio = rng.choice([0.382, 0.5, 0.618])
        if (cw > ch) == (rng.random() < 0.85):  # usually split the long side
            xm = x0 + cw * ratio
            line_draw.line([(xm, y0), (xm, y1)], fill=255, width=hairline)
            divide(x0, y0, xm, y1, depth + 1)
            divide(xm, y0, x1, y1, depth + 1)
        else:
            ym = y0 + ch * ratio
            line_draw.line([(x0, ym), (x1, ym)], fill=255, width=hairline)
            divide(x0, y0, x1, ym, depth + 1)
            divide(x0, ym, x1, y1, depth + 1)

    line_draw.rectangle([margin, margin, w - margin, h - margin],
                        outline=255, width=hairline)
    divide(margin, margin, w - margin, h - margin, 0)

    plates: list[Plate] = [(ink, m, 0.95) for ink, m in ink_masks.items()]
    plates.append((style.line_index, line_mask, 0.8))
    return plates


# ── Engine: beams ────────────────────────────────────────────────────────────

def beams(rng: random.Random, style: Style, w: int, h: int,
          phase: float, density: float) -> list[Plate]:
    """Sharp-angle beams fanning from edge anchors across the frame.

    Hard triangular rays overlap mid-frame — under risograph overprint the
    intersections mix into dark compound tones; a large half-disc anchors
    the geometry.
    """
    d = density * style.density_bias
    n_anchors = 2 + (rng.random() < 0.4 * d)
    ink_masks: dict[int, Image.Image] = {}
    ink_draws: dict[int, ImageDraw.ImageDraw] = {}

    edges = ["left", "right", "top", "bottom"]
    rng.shuffle(edges)
    for ai in range(n_anchors):
        edge = edges[ai % len(edges)]
        if edge == "left":
            ax, ay = -0.02 * w, rng.uniform(0.15, 0.85) * h
        elif edge == "right":
            ax, ay = 1.02 * w, rng.uniform(0.15, 0.85) * h
        elif edge == "top":
            ax, ay = rng.uniform(0.15, 0.85) * w, -0.02 * h
        else:
            ax, ay = rng.uniform(0.15, 0.85) * w, 1.02 * h

        n_beams = rng.randint(3, 5)
        toward = math.atan2(h / 2 - ay, w / 2 - ax)
        spread = rng.uniform(0.5, 1.1)
        for bi in range(n_beams):
            ink = (ai + bi) % 3
            if ink not in ink_masks:
                ink_masks[ink], ink_draws[ink] = _mask(w, h)
            a = toward + spread * ((bi / max(1, n_beams - 1)) - 0.5)
            a += 0.02 * _osc(phase, (ai * 3 + bi) * 0.13)
            half_w = rng.uniform(0.008, 0.05)
            reach = 1.45 * math.hypot(w, h)
            p1 = (ax + reach * math.cos(a - half_w), ay + reach * math.sin(a - half_w))
            p2 = (ax + reach * math.cos(a + half_w), ay + reach * math.sin(a + half_w))
            ink_draws[ink].polygon([(ax, ay), p1, p2], fill=255)

    # Half-disc anchor form.
    acc_mask, acc_draw = _mask(w, h)
    r = rng.uniform(0.1, 0.2) * min(w, h)
    cx, cy = rng.uniform(0.3, 0.7) * w, rng.uniform(0.35, 0.65) * h
    rot = rng.choice([0, 90, 180, 270])
    acc_draw.pieslice([cx - r, cy - r, cx + r, cy + r], rot, rot + 180, fill=255)

    plates: list[Plate] = [(ink, m, 0.85) for ink, m in ink_masks.items()]
    plates.append((style.accent_index, acc_mask, 1.0))
    return plates


# ── Engine: interference ─────────────────────────────────────────────────────

def interference(rng: random.Random, style: Style, w: int, h: int,
                 phase: float, density: float) -> list[Plate]:
    """Light-wave interference — concentric wavefronts from point sources.

    Each source emits fine rings on its own ink plate; where the ring
    systems overlap, hyperbolic moiré fringes emerge exactly as physical
    interference bands do. Animation advances every wavefront outward one
    wavelength per loop, so the waves travel seamlessly.
    """
    d = density * style.density_bias
    diag = math.hypot(w, h)
    n_src = 2 + (rng.random() < 0.45 * d)

    # Sources spread apart so the fringe field fills the frame.
    sources: list[tuple[float, float]] = []
    for i in range(n_src):
        ang = TWO_PI * (i / n_src) + rng.uniform(-0.5, 0.5)
        rad = rng.uniform(0.12, 0.3) * min(w, h)
        sources.append((w / 2 + rad * math.cos(ang) * rng.uniform(0.8, 2.2),
                        h / 2 + rad * math.sin(ang) * rng.uniform(0.8, 1.6)))

    wavelength = rng.uniform(0.022, 0.04) * min(w, h) / max(0.75, math.sqrt(d))
    if style.render_mode == "ascii":
        # Rings finer than the character grid alias into a solid glyph
        # field — waves must span several cells to read as waves.
        wavelength *= 2.6
    ring_w = max(1, round(wavelength * rng.uniform(0.3, 0.42)))
    rings = int(1.25 * diag / wavelength) + 1
    ink_coverage = 0.7 if style.blend == "multiply" else 0.8

    plates: list[Plate] = []
    dot_mask, dot_draw = _mask(w, h)
    for si, (sx, sy) in enumerate(sources):
        m, dr = _mask(w, h)
        travel = wavelength * phase  # one wavelength per loop → seamless
        for k in range(rings):
            r = travel + k * wavelength
            if r < 1:
                continue
            dr.ellipse([sx - r, sy - r, sx + r, sy + r], outline=255, width=ring_w)
        plates.append((si % 3, m, ink_coverage))
        pr = 0.008 * min(w, h)
        dot_draw.ellipse([sx - pr, sy - pr, sx + pr, sy + pr], fill=255)

    plates.append((style.accent_index, dot_mask, 1.0))
    return plates


# ── Engine: flora ────────────────────────────────────────────────────────────

def flora(rng: random.Random, style: Style, w: int, h: int,
          phase: float, density: float) -> list[Plate]:
    """Abstract nature scene — layered hills, a low sun, swaying sprigs.

    Noise-displaced horizon bands recede toward a quiet sky; botanical
    sprigs with seed heads grow from the front slopes and sway gently
    with the animation phase; an occasional bird drifts above.
    """
    d = density * style.density_bias
    noise = _value_noise(rng)

    # Sun (or moon) first, so hills occlude its lower edge at the horizon.
    sun_mask, sun_draw = _mask(w, h)
    sr = rng.uniform(0.06, 0.11) * min(w, h)
    sx = rng.uniform(0.18, 0.82) * w
    sy = rng.uniform(0.16, 0.38) * h
    sun_draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=255)
    sun_ink = rng.choice([0, 2])

    # Hill bands, back to front.
    n_hills = 3 + (rng.random() < 0.5 * d)
    hill_inks = [1, 2, 0, 1]
    rng.shuffle(hill_inks)
    hill_masks: dict[int, Image.Image] = {}
    hill_draws: dict[int, ImageDraw.ImageDraw] = {}
    silhouettes: list[list[tuple[float, float]]] = []
    for hi in range(n_hills):
        depth = hi / max(1, n_hills - 1)          # 0 = far, 1 = near
        base_y = (0.45 + 0.4 * depth) * h
        amp = rng.uniform(0.035, 0.085) * h * (0.6 + 0.7 * depth)
        freq = rng.uniform(1.2, 2.6)
        yoff = rng.uniform(0, 100)
        pts = []
        steps = 48
        for sxi in range(steps + 1):
            x = w * sxi / steps
            y = base_y + (noise(freq * sxi / steps * 4, yoff) - 0.5) * 2 * amp
            pts.append((x, y))
        silhouettes.append(pts)
        ink = hill_inks[hi % len(hill_inks)]
        if ink not in hill_masks:
            hill_masks[ink], hill_draws[ink] = _mask(w, h)
        hill_draws[ink].polygon(pts + [(w, h * 1.05), (0, h * 1.05)], fill=255)

    # Sprigs grow from the front two silhouettes.
    line_mask, line_draw = _mask(w, h)
    head_mask, head_draw = _mask(w, h)
    hairline = max(1, round(0.002 * min(w, h)))
    n_sprigs = max(4, round(9 * d) + rng.randint(0, 3))
    front = silhouettes[-2:] if len(silhouettes) > 1 else silhouettes
    for si in range(n_sprigs):
        sil = front[rng.randrange(len(front))]
        bx, by = sil[rng.randrange(4, len(sil) - 4)]
        height = rng.uniform(0.07, 0.17) * h
        sway = 0.018 * w * _osc(phase, si * 0.21) * rng.uniform(0.4, 1.0)
        lean = rng.uniform(-0.15, 0.15) * height
        pts = []
        segs = 8
        for t in range(segs + 1):
            f = t / segs
            px = bx + (lean + sway) * (f ** 2)
            py = by - height * f
            pts.append((px, py))
        line_draw.line(pts, fill=255, width=hairline)
        top = pts[-1]
        kind = rng.random()
        hr = rng.uniform(0.008, 0.02) * min(w, h)
        if kind < 0.45:      # seed head disc
            head_draw.ellipse([top[0] - hr, top[1] - hr, top[0] + hr, top[1] + hr], fill=255)
        elif kind < 0.75:    # open umbel: short rays
            for a in (-0.9, -0.45, 0.0, 0.45, 0.9):
                ex = top[0] + 2.2 * hr * math.sin(a)
                ey = top[1] - 2.2 * hr * math.cos(a)
                line_draw.line([top, (ex, ey)], fill=255, width=hairline)
        else:                # bud arc
            line_draw.arc([top[0] - hr * 1.6, top[1] - hr * 1.6,
                           top[0] + hr * 1.6, top[1] + hr * 1.6], 200, 340,
                          fill=255, width=hairline)

    # A bird or two.
    if rng.random() < 0.65:
        for bi in range(rng.randint(1, 3)):
            bx = rng.uniform(0.15, 0.85) * w + 0.01 * w * _osc(phase, bi * 0.37)
            by = rng.uniform(0.08, 0.3) * h
            bw = rng.uniform(0.012, 0.022) * w
            line_draw.arc([bx - bw, by - bw * 0.6, bx, by + bw * 0.6], 200, 330,
                          fill=255, width=hairline)
            line_draw.arc([bx, by - bw * 0.6, bx + bw, by + bw * 0.6], 210, 340,
                          fill=255, width=hairline)

    plates: list[Plate] = [(sun_ink, sun_mask, 0.9)]
    plates.extend((ink, m, 1.0) for ink, m in hill_masks.items())
    plates.append((style.accent_index, head_mask, 1.0))
    plates.append((style.line_index, line_mask, 0.9))
    return plates


# ── Engine: truchet ──────────────────────────────────────────────────────────

def truchet(rng: random.Random, style: Style, w: int, h: int,
            phase: float, density: float) -> list[Plate]:
    """Truchet tiling — quarter-circle arc tiles weaving endless paths.

    Each tile holds two arcs in one of two orientations; adjacent tiles
    connect into winding labyrinths. A fraction of tiles turn 180° once
    per loop (motif-symmetric, so the loop closes), continuously rewiring
    the maze.
    """
    d = density * style.density_bias
    across = max(4, round(rng.uniform(5, 8) * max(0.75, math.sqrt(d))))
    ts = min(w, h) / across
    cols, rows = int(w / ts) + 1, int(h / ts) + 1
    ox, oy = (w - cols * ts) / 2, (h - rows * ts) / 2

    line_mask, line_draw = _mask(w, h)
    ink_masks: dict[int, Image.Image] = {}
    ink_draws: dict[int, ImageDraw.ImageDraw] = {}
    hairline = max(1, round(0.0016 * min(w, h)))
    corner_base = {  # corner position → angular range of the inside arc
        (0, 0): 0, (1, 0): 90, (1, 1): 180, (0, 1): 270,
    }

    for r in range(rows):
        for c in range(cols):
            x0, y0 = ox + c * ts, oy + r * ts
            xc, yc = x0 + ts / 2, y0 + ts / 2
            state = rng.random() < 0.5
            kind = rng.random()

            # Sparse filled quarter-disc accents (static — a 180° turn of a
            # single disc is not motif-symmetric).
            if kind < 0.06:
                ink = rng.choice([0, 1, 2])
                if ink not in ink_masks:
                    ink_masks[ink], ink_draws[ink] = _mask(w, h)
                cx_, cy_ = rng.choice([(0, 0), (1, 0), (1, 1), (0, 1)])
                base = corner_base[(cx_, cy_)]
                px, py = x0 + cx_ * ts, y0 + cy_ * ts
                ink_draws[ink].pieslice([px - ts / 2, py - ts / 2, px + ts / 2, py + ts / 2],
                                        base, base + 90, fill=255)
                continue

            thick = rng.random() < 0.16
            if thick:
                ink = rng.choice([0, 1, 2])
                if ink not in ink_masks:
                    ink_masks[ink], ink_draws[ink] = _mask(w, h)
                dr, lw = ink_draws[ink], max(2, round(ts * 0.24))
            else:
                dr, lw = line_draw, hairline

            theta = 0.0
            if rng.random() < 0.3:  # rotating tiles
                theta = 180.0 * _pulse(phase, rng.random(), 0.14)
            corners = [(0, 0), (1, 1)] if state else [(1, 0), (0, 1)]
            th = math.radians(theta)
            ca, sa = math.cos(th), math.sin(th)
            for cx_, cy_ in corners:
                base = corner_base[(cx_, cy_)]
                px, py = x0 + cx_ * ts, y0 + cy_ * ts
                dx, dy = px - xc, py - yc
                nx = xc + dx * ca - dy * sa
                ny = yc + dx * sa + dy * ca
                dr.arc([nx - ts / 2, ny - ts / 2, nx + ts / 2, ny + ts / 2],
                       base + theta, base + theta + 90, fill=255, width=lw)

    plates: list[Plate] = [(ink, m, 0.95) for ink, m in ink_masks.items()]
    plates.append((style.line_index, line_mask, 0.85))
    return plates


# ── Engine: contours ─────────────────────────────────────────────────────────

def contours(rng: random.Random, style: Style, w: int, h: int,
             phase: float, density: float) -> list[Plate]:
    """Topographic contours of a noise heightfield (marching squares).

    Hairline elevation lines with every few levels drawn heavy in ink, and
    the lowest basin filled as a soft wash. Animated, the elevation set
    drifts one level-spacing per loop, so contours flow like a rising tide.
    """
    d = density * style.density_bias
    noise = _value_noise(rng)
    gw = 104
    gh = max(10, round(gw * h / max(1, w)))
    f1 = rng.uniform(1.7, 2.8)
    off = rng.uniform(0, 60)
    aspect = gh / gw

    field: list[list[float]] = []
    for gy in range(gh + 1):
        row = []
        for gx in range(gw + 1):
            u, v = gx / gw, gy / gh * aspect
            val = noise(f1 * u, f1 * v + off) + 0.45 * noise(2.6 * f1 * u + 17, 2.6 * f1 * v + off + 9)
            row.append(val)
        field.append(row)
    flat = [v for row in field for v in row]
    lo, hi = min(flat), max(flat)
    span = (hi - lo) or 1.0
    field = [[(v - lo) / span for v in row] for row in field]

    n_levels = max(6, round(9 * d))
    spacing = 1.0 / (n_levels + 1)
    toff = spacing * phase  # one spacing per loop → the level set maps to itself
    chunky_every = rng.choice([3, 4])
    hairline = max(1, round(0.0016 * min(w, h)))
    cw, chh = w / gw, h / gh

    line_mask, line_draw = _mask(w, h)
    ink_masks: dict[int, Image.Image] = {}
    ink_draws: dict[int, ImageDraw.ImageDraw] = {}

    def lerp(pa: float, pb: float, t: float) -> float:
        return (t - pa) / (pb - pa) if pb != pa else 0.5

    for li in range(n_levels):
        t = (li + 1) * spacing + toff
        if t >= 1.0:
            t -= 1.0 + spacing  # wrapped level re-enters at the bottom
        if not (0.0 < t < 1.0):
            continue
        if li % chunky_every == chunky_every - 1:
            ink = [0, 1, 2][li % 3]
            if ink not in ink_masks:
                ink_masks[ink], ink_draws[ink] = _mask(w, h)
            dr, lw = ink_draws[ink], max(2, hairline * 3)
        else:
            dr, lw = line_draw, hairline
        for gy in range(gh):
            for gx in range(gw):
                a = field[gy][gx]
                b = field[gy][gx + 1]
                c = field[gy + 1][gx + 1]
                e = field[gy + 1][gx]
                case = (a > t) | ((b > t) << 1) | ((c > t) << 2) | ((e > t) << 3)
                if case in (0, 15):
                    continue
                x0, y0 = gx * cw, gy * chh
                top = (x0 + cw * lerp(a, b, t), y0)
                right = (x0 + cw, y0 + chh * lerp(b, c, t))
                bottom = (x0 + cw * lerp(e, c, t), y0 + chh)
                left = (x0, y0 + chh * lerp(a, e, t))
                segs = {
                    1: [(left, top)], 2: [(top, right)], 3: [(left, right)],
                    4: [(right, bottom)], 5: [(left, top), (right, bottom)],
                    6: [(top, bottom)], 7: [(left, bottom)],
                    8: [(bottom, left)], 9: [(top, bottom)],
                    10: [(top, right), (bottom, left)], 11: [(right, bottom)],
                    12: [(left, right)], 13: [(top, right)], 14: [(left, top)],
                }[case]
                for p0, p1 in segs:
                    dr.line([p0, p1], fill=255, width=lw)

    # Basin wash: fill below the lowest active level as a soft plate.
    basin_t = spacing + toff
    coarse = Image.frombytes(
        "L", (gw + 1, gh + 1),
        bytes(255 if v < basin_t else 0 for row in field for v in row))
    basin = coarse.resize((w, h), Image.BICUBIC)
    plates: list[Plate] = [(rng.choice([0, 1, 2]), basin, 0.55)]
    plates.extend((ink, m, 0.9) for ink, m in ink_masks.items())
    plates.append((style.line_index, line_mask, 0.85))
    return plates


# ── Engine: harmonograph ─────────────────────────────────────────────────────

def harmonograph(rng: random.Random, style: Style, w: int, h: int,
                 phase: float, density: float) -> list[Plate]:
    """Harmonograph — decaying pendulum curves in fine ink.

    Two detuned oscillators per axis trace the classic precessing Lissajous
    bloom. The inter-axis phase advances one full cycle per loop, so the
    figure continuously re-blooms without a seam.
    """
    d = density * style.density_bias
    n_curves = 2 + (rng.random() < 0.5 * d)
    cx, cy = w / 2, h / 2
    pairs = [(2, 3), (3, 4), (3, 5), (2, 5), (4, 5)]

    plates: list[Plate] = []
    hairline = max(1, round(0.0015 * min(w, h)))

    for ci in range(n_curves):
        a, b = rng.choice(pairs)
        if rng.random() < 0.5:
            a, b = b, a
        scale = rng.uniform(0.9, 1.02) * (1.0 - 0.08 * ci)
        ax = 0.45 * w * scale
        ay = 0.45 * h * scale
        det = rng.uniform(0.006, 0.02)
        decay = rng.uniform(0.010, 0.028)
        p = [rng.uniform(0, TWO_PI) for _ in range(4)]
        total_t = rng.uniform(9, 14) * math.pi
        steps = 2400
        pts = []
        for i in range(steps):
            t = total_t * i / (steps - 1)
            e = math.exp(-decay * t)
            x = cx + ax * e * (0.72 * math.sin(a * t + p[0] + TWO_PI * phase)
                               + 0.28 * math.sin((a + det) * t + p[1]))
            y = cy + ay * e * (0.72 * math.sin(b * t + p[2])
                               + 0.28 * math.sin((b + det) * t + p[3]))
            pts.append((x, y))
        m, dr = _mask(w, h)
        last = ci == n_curves - 1
        lw = hairline if last else max(2, hairline * rng.randint(2, 3))
        dr.line(pts, fill=255, width=lw, joint="curve")
        if last:
            plates.append((style.line_index, m, 0.85))
        else:
            plates.append((ci % 3, m, 0.7))

    return plates


# ── Engine: glyphrain ────────────────────────────────────────────────────────

def glyphrain(rng: random.Random, style: Style, w: int, h: int,
              phase: float, density: float) -> list[Plate]:
    """Falling streak columns — abstract rain, or Matrix rain in phosphor.

    Columns carry streaks at three integer speed tiers (fast streaks print
    bright, slow ones dim — cheap depth). Each tier travels a whole number
    of frame-heights per loop, wrapping cylindrically, so the loop closes.
    """
    d = density * style.density_bias
    pitch = min(w, h) / rng.uniform(26, 38)
    cols = int(w / pitch) + 1
    lw = max(1, round(pitch * 0.3))
    tier_ink = {3: 0, 2: 1, 1: 2}  # fast → brightest palette slot

    ink_masks: dict[int, Image.Image] = {}
    ink_draws: dict[int, ImageDraw.ImageDraw] = {}
    head_mask, head_draw = _mask(w, h)

    def seg(dr: ImageDraw.ImageDraw, x: float, y_top: float, y_bot: float) -> None:
        """Draw a vertical segment on the h-cylinder (wraps at the edges)."""
        y_top %= h
        y_bot = y_top + (y_bot - y_top)
        if y_bot <= h:
            dr.line([(x, y_top), (x, y_bot)], fill=255, width=lw)
        else:
            dr.line([(x, y_top), (x, h)], fill=255, width=lw)
            dr.line([(x, 0), (x, y_bot - h)], fill=255, width=lw)

    for c in range(cols):
        if rng.random() < 0.2:  # breathing room between columns
            continue
        x = (c + 0.5) * pitch + rng.uniform(-0.15, 0.15) * pitch
        v = rng.choice([1, 1, 2, 2, 2, 3])
        ink = tier_ink[v]
        if ink not in ink_masks:
            ink_masks[ink], ink_draws[ink] = _mask(w, h)
        n_streaks = 1 + (rng.random() < 0.45 * d)
        for _ in range(n_streaks):
            length = rng.uniform(0.1, 0.3) * h * (0.55 + 0.22 * v)
            head_y = (rng.uniform(0, h) + v * h * phase) % h
            seg(ink_draws[ink], x, head_y - length, head_y)
            hr = lw * 1.1
            head_draw.ellipse([x - hr, head_y - hr, x + hr, head_y + hr], fill=255)

    plates: list[Plate] = []
    for ink in (2, 1, 0):  # slow/dim behind, fast/bright in front
        if ink in ink_masks:
            plates.append((ink, ink_masks[ink], 0.62 + 0.13 * (2 - ink)))
    plates.append((style.accent_index, head_mask, 1.0))
    return plates


# ── Registry ─────────────────────────────────────────────────────────────────

ENGINES: dict[str, Callable[..., list[Plate]]] = {
    "arches":       arches,
    "flowfield":    flowfield,
    "inkweave":     inkweave,
    "orbits":       orbits,
    "tatami":       tatami,
    "beams":        beams,
    "interference": interference,
    "flora":        flora,
    "truchet":      truchet,
    "contours":     contours,
    "harmonograph": harmonograph,
    "glyphrain":    glyphrain,
}

ENGINE_INFO: list[dict[str, str]] = [
    {"id": "arches",    "name": "Arch Study",
     "description": "Soft geometric arches on a staggered baseline grid"},
    {"id": "flowfield", "name": "Sand Currents",
     "description": "Fine algorithmic curves flowing through a noise field"},
    {"id": "inkweave",  "name": "Ink Weave",
     "description": "Intersecting fine ink lines over sparse geometric blocks"},
    {"id": "orbits",    "name": "Orbit Rhythm",
     "description": "Rhythmic concentric arcs around one or two poles"},
    {"id": "tatami",    "name": "Tatami Grid",
     "description": "Recursive golden-ratio subdivision, mostly negative space"},
    {"id": "beams",     "name": "Signal Beams",
     "description": "Sharp-angle rays fanning from the frame edges"},
    {"id": "interference", "name": "Standing Waves",
     "description": "Wavefronts from point sources weaving interference fringes"},
    {"id": "flora",     "name": "Quiet Meadow",
     "description": "Layered hills, a low sun, and swaying botanical sprigs"},
    {"id": "truchet",   "name": "Truchet Maze",
     "description": "Quarter-circle arc tiles weaving endless winding paths"},
    {"id": "contours",  "name": "Contour Map",
     "description": "Topographic elevation lines over a noise heightfield"},
    {"id": "harmonograph", "name": "Harmonograph",
     "description": "Decaying pendulum curves in fine plotter ink"},
    {"id": "glyphrain", "name": "Glyph Rain",
     "description": "Falling streak columns — Matrix rain in phosphor"},
]


def pick_engine(algorithm: str, rng: random.Random) -> str:
    """Resolve an algorithm setting ('auto' picks per-seed) to an engine id."""
    if algorithm in ENGINES:
        return algorithm
    return rng.choice(sorted(ENGINES.keys()))
