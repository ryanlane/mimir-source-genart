"""Material renderer for the Generative Art channel.

Takes the ink plates an engine composed and prints them in the active style:

  1. Supersampled masks are downscaled (the anti-aliasing pass) and edge-
     softened per style — Wabi-Sabi forms breathe, riso shapes stay hard.
  2. Riso styles offset each plate slightly (organic registration error)
     and modulate ink coverage with speckle noise (distressed print look).
  3. Plates composite onto the paper with a transmittance (overprint) model:
     overlapping inks multiply the way real translucent print inks do —
     implemented as ImageChops.multiply masked by the plate alpha.
  4. Paper finish: organic grain, cotton fiber streaks, and a soft vignette.

Pure PIL + stdlib on purpose: Pillow ships in the Mimir base image, so the
plugin renders even when the installer's best-effort `pip install` can't run.

Static output is lossless PNG (crisp on e-ink); animated output is a looping
animated WebP the Electron display animates natively in an <img> tag.
"""
from __future__ import annotations

import io
import random

from PIL import Image, ImageChops, ImageFilter

from .engines import ENGINES, pick_engine
from .styles import Style, get_style

# Supersampling is the anti-aliasing mechanism. Static renders happen once
# per seed and can afford 2x; animated renders do frames × the work, so
# large animated targets drop to 1x rather than stalling the first refresh.
_SS_STATIC = 2.0
_ANIMATED_SS_AREA_LIMIT = 1_100_000  # ~HD; above this animate at 1x

_MAX_PLATES = 16  # registration offsets are pre-drawn for this many plates


def _supersample(w: int, h: int, animated: bool) -> float:
    if animated and w * h > _ANIMATED_SS_AREA_LIMIT:
        return 1.0
    return _SS_STATIC


def _noise_image(rng: random.Random, w: int, h: int) -> Image.Image:
    """Seeded uniform-noise L image (PIL's effect_noise is unseedable)."""
    return Image.frombytes("L", (w, h), bytes(rng.getrandbits(8) for _ in range(w * h)))


def _blob_noise(rng: random.Random, w: int, h: int, cells: int) -> Image.Image:
    """Soft blotch field — low-res seeded noise smoothly upscaled, squared
    so ink dropout stays mostly-nothing with occasional light patches."""
    gw = max(2, cells)
    gh = max(2, round(cells * h / max(1, w)))
    img = _noise_image(rng, gw, gh).resize((w, h), Image.BICUBIC)
    return img.point(lambda v: (v * v) // 255)


class _Materials:
    """Per-piece print materials, computed once and reused for every
    animation frame — paper, ink dropout, and plate offsets don't move."""

    def __init__(self, style: Style, seed: int, w: int, h: int, tex: float):
        rng = random.Random(seed ^ 0x5EED)
        self.blotch: Image.Image | None = None
        if style.coverage_noise > 0:
            fine = _blob_noise(rng, w, h, cells=110)
            broad = _blob_noise(rng, w, h, cells=12)
            blotch = Image.blend(fine, broad, 0.3)
            # Coverage multiplier map: 255 = full ink, lower = dropout.
            drop = style.coverage_noise * tex
            self.blotch = blotch.point(lambda v: 255 - round(drop * v))

        self.offsets: list[tuple[int, int]] = []
        max_off = style.registration_jitter * w
        for _ in range(_MAX_PLATES):
            if max_off > 0:
                self.offsets.append((round(rng.uniform(-max_off, max_off)),
                                     round(rng.uniform(-max_off, max_off))))
            else:
                self.offsets.append((0, 0))

        # Grain: seeded noise centered on 128, softened and contrast-scaled.
        self.grain: Image.Image | None = None
        amp = 0.016 * style.grain * tex
        if amp > 0:
            g = _noise_image(rng, max(1, w // 2), max(1, h // 2)).resize((w, h), Image.BILINEAR)
            k = amp * 255 * 2.0
            self.grain = g.point(lambda v: max(0, min(255, round(128 + (v - 128) / 127 * k))))

        # Cotton fiber: horizontal streaks from a 1-px-wide noise column.
        self.fiber: Image.Image | None = None
        famp = 0.010 * style.fiber * tex
        if famp > 0:
            col = _noise_image(rng, 1, max(2, h // 3)).resize((1, h), Image.BICUBIC)
            fk = famp * 255 * 2.0
            col = col.point(lambda v: max(0, min(255, round(128 + (v - 128) / 127 * fk))))
            self.fiber = col.resize((w, h), Image.NEAREST)

        # Vignette: radial multiplier map (255 center → darker corners).
        self.vignette: Image.Image | None = None
        if style.vignette > 0:
            rad = Image.radial_gradient("L").resize((w, h), Image.BILINEAR)
            vig = style.vignette * 0.09
            self.vignette = rad.point(
                lambda v: round(255 * (1.0 - vig * (v / 255.0) ** 2)))


def _apply_centered_add(canvas: Image.Image, delta: Image.Image) -> Image.Image:
    """Add (delta - 128) to the canvas — additive texture around neutral."""
    return ImageChops.add(canvas, delta.convert("RGB"), scale=1.0, offset=-128)


def render_frame(style: Style, algorithm: str, seed: int, w: int, h: int,
                 phase: float = 0.0, density: float = 1.0,
                 texture_strength: float = 1.0, supersample: float = _SS_STATIC,
                 materials: "_Materials | None" = None) -> Image.Image:
    """Render one finished frame as an RGB PIL image."""
    rng = random.Random(seed)
    engine_id = pick_engine(algorithm, rng)
    ss = max(1.0, supersample)
    sw, sh = round(w * ss), round(h * ss)

    plates = ENGINES[engine_id](rng, style, sw, sh, phase, density)
    mat = materials or _Materials(style, seed, w, h, texture_strength)

    canvas = Image.new("RGB", (w, h), style.paper)

    for plate_idx, (ink_idx, mask, coverage) in enumerate(plates):
        if mask.size != (w, h):
            mask = mask.resize((w, h), Image.LANCZOS)
        if style.edge_blur > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(style.edge_blur))

        dx, dy = mat.offsets[plate_idx % _MAX_PLATES]
        if dx or dy:
            mask = ImageChops.offset(mask, dx, dy)
        if mat.blotch is not None:
            mask = ImageChops.multiply(mask, mat.blotch)

        alpha = style.ink_opacity * coverage
        if alpha < 1.0:
            mask = mask.point(lambda v: round(v * alpha))

        # Transmittance overprint: where the plate covers, the canvas is
        # multiplied by the ink color — paper and prior inks show through.
        inked = ImageChops.multiply(canvas, Image.new("RGB", (w, h), style.inks[ink_idx]))
        canvas = Image.composite(inked, canvas, mask)

    # ── Paper finish ─────────────────────────────────────────────────────
    if mat.grain is not None:
        canvas = _apply_centered_add(canvas, mat.grain)
    if mat.fiber is not None:
        canvas = _apply_centered_add(canvas, mat.fiber)
    if mat.vignette is not None:
        canvas = ImageChops.multiply(canvas, mat.vignette.convert("RGB"))

    return canvas


def render_static(style_id: str, algorithm: str, seed: int, w: int, h: int,
                  density: float = 1.0, texture_strength: float = 1.0) -> bytes:
    """Render a finished piece as PNG bytes (lossless — crisp on e-ink)."""
    style = get_style(style_id)
    img = render_frame(style, algorithm, seed, w, h, phase=0.0, density=density,
                       texture_strength=texture_strength,
                       supersample=_supersample(w, h, animated=False))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_animated(style_id: str, algorithm: str, seed: int, w: int, h: int,
                    frames: int = 24, frame_ms: int = 120,
                    density: float = 1.0, texture_strength: float = 1.0) -> bytes:
    """Render a seamless looping animation as animated WebP bytes.

    Engines treat ``phase`` cyclically, so frame N wraps back to frame 0
    with no visible seam. Materials are computed once — paper texture and
    registration error hold still while the composition moves.
    """
    style = get_style(style_id)
    ss = _supersample(w, h, animated=True)
    mat = _Materials(style, seed, w, h, texture_strength)
    imgs = [
        render_frame(style, algorithm, seed, w, h, phase=i / frames,
                     density=density, texture_strength=texture_strength,
                     supersample=ss, materials=mat)
        for i in range(frames)
    ]
    buf = io.BytesIO()
    imgs[0].save(buf, format="WEBP", save_all=True, append_images=imgs[1:],
                 duration=frame_ms, loop=0, quality=82, method=4)
    return buf.getvalue()
