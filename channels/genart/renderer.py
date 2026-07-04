"""Material renderer for the Generative Art channel.

Takes the ink plates an engine composed and prints them in the active style:

  1. Supersampled masks are downscaled (the anti-aliasing pass) and edge-
     softened per style — Wabi-Sabi forms breathe, riso shapes stay hard.
  2. Riso styles offset each plate slightly (organic registration error)
     and modulate ink coverage with blotchy noise (distressed print look).
  3. Plates composite onto the paper with a transmittance (overprint) model:
     overlapping inks multiply the way real translucent print inks do.
  4. Paper finish: organic grain, cotton fiber streaks, and a soft vignette.

Static output is lossless PNG (crisp on e-ink); animated output is a looping
animated WebP the Electron display animates natively in an <img> tag.
"""
from __future__ import annotations

import io
import random

import numpy as np
from PIL import Image, ImageFilter

from .engines import ENGINES, pick_engine
from .styles import Style, get_style

# Supersampling is the anti-aliasing mechanism. Static renders happen once
# per seed and can afford 2x; animated renders do frames × the work, so
# large animated targets drop to 1x rather than stalling the first refresh.
_SS_STATIC = 2.0
_ANIMATED_SS_AREA_LIMIT = 1_100_000  # ~HD; above this animate at 1x


def _supersample(w: int, h: int, animated: bool) -> float:
    if animated and w * h > _ANIMATED_SS_AREA_LIMIT:
        return 1.0
    return _SS_STATIC


def _blob_noise(rng: np.random.Generator, w: int, h: int, cells: int) -> np.ndarray:
    """Soft blotch field in [0,1] — low-res noise smoothly upscaled."""
    gw, gh = max(2, cells), max(2, round(cells * h / max(1, w)))
    grid = rng.random((gh, gw), dtype=np.float32)
    img = Image.fromarray((grid * 255).astype(np.uint8), "L")
    img = img.resize((w, h), Image.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0


def render_frame(style: Style, algorithm: str, seed: int, w: int, h: int,
                 phase: float = 0.0, density: float = 1.0,
                 texture_strength: float = 1.0, supersample: float = _SS_STATIC,
                 ) -> Image.Image:
    """Render one finished frame as an RGB PIL image."""
    rng = random.Random(seed)
    engine_id = pick_engine(algorithm, rng)
    ss = max(1.0, supersample)
    sw, sh = round(w * ss), round(h * ss)

    plates = ENGINES[engine_id](rng, style, sw, sh, phase, density)

    # Per-seed material randomness must not disturb composition randomness,
    # and must be identical across animation frames (paper doesn't move).
    mat_rng = np.random.default_rng(seed ^ 0x5EED)
    tex = texture_strength

    paper = np.array(style.paper, dtype=np.float32) / 255.0
    canvas = np.ones((h, w, 3), dtype=np.float32) * paper

    for ink_idx, mask_img, coverage in plates:
        if mask_img.size != (w, h):
            mask_img = mask_img.resize((w, h), Image.LANCZOS)
        if style.edge_blur > 0:
            mask_img = mask_img.filter(ImageFilter.GaussianBlur(style.edge_blur))
        mask = np.asarray(mask_img, dtype=np.float32) / 255.0

        if style.registration_jitter > 0:
            max_off = style.registration_jitter * w
            dx = round(mat_rng.uniform(-max_off, max_off))
            dy = round(mat_rng.uniform(-max_off, max_off))
            if dx or dy:
                mask = np.roll(mask, (dy, dx), axis=(0, 1))

        if style.coverage_noise > 0:
            # Real riso ink drops out as fine speckle plus faint broad
            # unevenness — big soft blobs read as airbrush, not print.
            fine = _blob_noise(mat_rng, w, h, cells=110) ** 2
            broad = _blob_noise(mat_rng, w, h, cells=12) ** 2
            blotch = 0.7 * fine + 0.3 * broad
            mask = mask * (1.0 - style.coverage_noise * tex * blotch)

        ink = np.array(style.inks[ink_idx], dtype=np.float32) / 255.0
        alpha = (mask * style.ink_opacity * coverage)[..., None]
        # Transmittance overprint: paper shows through ink like real print.
        canvas *= (1.0 - alpha * (1.0 - ink))

    # ── Paper finish ─────────────────────────────────────────────────────
    if style.grain > 0:
        grain = mat_rng.normal(0.0, 0.016 * style.grain * tex, (h, w, 1)).astype(np.float32)
        canvas += grain
    if style.fiber > 0:
        # Cotton-rag fiber: faint horizontal streaks from blurred 1-D noise.
        rows = mat_rng.normal(0.0, 1.0, (h, 1)).astype(np.float32)
        kernel = np.ones(9, dtype=np.float32) / 9
        rows = np.convolve(rows[:, 0], kernel, mode="same")[:, None, None]
        canvas += rows * 0.010 * style.fiber * tex
    if style.vignette > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        rr = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
        canvas *= (1.0 - style.vignette * 0.09 * (rr ** 2))[..., None]

    return Image.fromarray((np.clip(canvas, 0.0, 1.0) * 255).astype(np.uint8), "RGB")


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
    with no visible seam.
    """
    style = get_style(style_id)
    ss = _supersample(w, h, animated=True)
    imgs = [
        render_frame(style, algorithm, seed, w, h, phase=i / frames,
                     density=density, texture_strength=texture_strength,
                     supersample=ss)
        for i in range(frames)
    ]
    buf = io.BytesIO()
    imgs[0].save(buf, format="WEBP", save_all=True, append_images=imgs[1:],
                 duration=frame_ms, loop=0, quality=82, method=4)
    return buf.getvalue()
