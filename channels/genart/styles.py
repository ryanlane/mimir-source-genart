"""Style system for the Generative Art channel.

A *style* is the material identity of a piece: its palette, how ink plates
composite onto the paper, and the print-finish texture applied at the end.
Algorithms (see engines.py) are composition engines that emit ink plates;
they are style-agnostic, so every algorithm renders in every style.

Styles:
  wabi           — Bauhaus structure with a Wabi-Sabi finish: muted terracotta,
                   raw linen oat, deep charcoal, soft sage on heavyweight cotton
                   paper. Soft edges, giclée grain, generous negative space.
  constructivist — Bold 1960s constructivist: mustard, deep teal, burnt orange
                   on warm cream. Hard edges, risograph overprint with slight
                   registration error and distressed ink coverage.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    description: str
    paper: tuple[int, int, int]          # background / paper color
    inks: list[tuple[int, int, int]]     # palette slots engines draw with
    accent_index: int                    # ink reserved for sparse accents
    line_index: int                      # ink used for fine line work
    edge_blur: float                     # px blur on plate masks (at 1x scale)
    ink_opacity: float                   # 0..1 plate coverage strength
    registration_jitter: float           # max plate offset as fraction of width
    coverage_noise: float                # 0..1 ink-coverage irregularity (riso blotch)
    grain: float                         # 0..1 paper grain strength
    fiber: float                         # 0..1 paper fiber streak strength (cotton rag)
    vignette: float                      # 0..1 edge-light falloff
    density_bias: float                  # multiplier on element counts (wabi is sparser)
    # Material extensions (defaults preserve the original print styles)
    blend: str = "multiply"              # multiply = ink on paper | screen = light on dark
    render_mode: str = "solid"           # solid | ascii (plates become glyph grids)
    ascii_rows: int = 44                 # ascii mode: character rows across the short edge
    ascii_ramp: str = " .:-=+*#%@"       # ascii mode: glyph density ramp, sparse → solid
    glow: float = 0.0                    # 0..1 bloom for light-emitting styles
    scanlines: float = 0.0               # 0..1 CRT scanline strength


STYLES: dict[str, Style] = {
    "wabi": Style(
        id="wabi",
        name="Kyoto Bauhaus",
        description=(
            "Bauhaus structure, Wabi-Sabi soul — soft geometric arches, "
            "sand-textured curves and fine ink lines on heavyweight cotton "
            "paper. Muted terracotta, raw linen oat, deep charcoal, soft sage."
        ),
        paper=(0xED, 0xE6, 0xD6),                 # raw linen oat
        inks=[
            (0xB4, 0x6A, 0x48),                   # muted terracotta
            (0x9B, 0xA8, 0x8B),                   # soft sage green
            (0xD9, 0xC9, 0xAE),                   # warm sand (quiet mid-tone)
            (0x2B, 0x28, 0x24),                   # deep charcoal (accent + line)
        ],
        accent_index=3,
        line_index=3,
        edge_blur=1.6,
        ink_opacity=0.82,
        registration_jitter=0.0,
        coverage_noise=0.18,
        grain=0.5,
        fiber=0.6,
        vignette=0.35,
        density_bias=0.7,
    ),
    "constructivist": Style(
        id="constructivist",
        name="Riso Constructivist '66",
        description=(
            "Bold 1960s constructivism — hard-edge geometry on a mathematical "
            "grid, rhythmic curves and sharp angles. Mustard, deep teal and "
            "burnt orange risograph inks overprinted on warm cream, with "
            "organic registration error and tactile paper grain."
        ),
        paper=(0xF3, 0xEA, 0xD7),                 # warm off-white cream
        inks=[
            (0xD8, 0x9E, 0x14),                   # mustard yellow
            (0x0F, 0x5B, 0x63),                   # deep teal
            (0xC2, 0x59, 0x24),                   # burnt orange
            (0x24, 0x26, 0x28),                   # near-black ink (line work)
        ],
        accent_index=2,
        line_index=3,
        edge_blur=0.4,
        ink_opacity=0.92,
        registration_jitter=0.004,
        coverage_noise=0.38,
        grain=0.65,
        fiber=0.25,
        vignette=0.15,
        density_bias=1.0,
    ),
    "phosphor": Style(
        id="phosphor",
        name="Phosphor Terminal",
        description=(
            "Every element rebuilt from ASCII characters — a density ramp of "
            "glyphs on a near-black CRT, glowing Mimir green with scanlines "
            "and soft phosphor bloom. All six algorithms render as living "
            "terminal art."
        ),
        paper=(0x05, 0x09, 0x08),                 # CRT black
        inks=[
            (0x3C, 0xFF, 0x6E),                   # bright phosphor green
            (0x2B, 0xD9, 0xA0),                   # teal-green
            (0x1E, 0x8F, 0x4D),                   # dim green
            (0xCF, 0xFF, 0xDD),                   # pale mint (lines/accent)
        ],
        accent_index=3,
        line_index=3,
        edge_blur=0.0,                            # glyphs are the texture
        ink_opacity=1.0,
        registration_jitter=0.0,
        coverage_noise=0.2,                       # phosphor dropout flicker
        grain=0.3,
        fiber=0.0,
        vignette=0.38,
        density_bias=1.0,
        blend="screen",
        render_mode="ascii",
        glow=0.65,
        scanlines=0.3,
    ),
    "blueprint": Style(
        id="blueprint",
        name="Blueprint Cyanotype",
        description=(
            "Draftsman's cyanotype — pale washes and near-white line work "
            "screened onto deep Prussian blue paper, with brush dropout, "
            "paper grain and a sun-faded vignette."
        ),
        paper=(0x11, 0x3A, 0x63),                 # Prussian blue
        inks=[
            (0x9F, 0xC8, 0xE8),                   # pale cyan wash
            (0x6F, 0xA8, 0xD6),                   # mid wash
            (0x4A, 0x87, 0xBD),                   # soft wash
            (0xE9, 0xF2, 0xFF),                   # near-white (lines/accent)
        ],
        accent_index=3,
        line_index=3,
        edge_blur=0.6,
        ink_opacity=0.85,
        registration_jitter=0.0,
        coverage_noise=0.15,
        grain=0.5,
        fiber=0.4,
        vignette=0.4,
        density_bias=0.9,
        blend="screen",
    ),
    "neon": Style(
        id="neon",
        name="Neon Dusk",
        description=(
            "Synthwave gallery piece — hot pink, electric cyan and violet "
            "light-forms blooming on deep indigo, faint scanlines and haze. "
            "Made for OLED; pairs beautifully with animated output."
        ),
        paper=(0x0E, 0x0A, 0x1F),                 # deep indigo
        inks=[
            (0xFF, 0x3D, 0x9A),                   # hot pink
            (0x23, 0xE5, 0xFF),                   # electric cyan
            (0x8C, 0x5B, 0xFF),                   # violet
            (0xF4, 0xF9, 0xC0),                   # pale lemon (lines/accent)
        ],
        accent_index=3,
        line_index=3,
        edge_blur=0.8,
        ink_opacity=0.9,
        registration_jitter=0.002,                # chromatic drift
        coverage_noise=0.12,
        grain=0.35,
        fiber=0.0,
        vignette=0.5,
        density_bias=1.0,
        blend="screen",
        glow=0.55,
        scanlines=0.12,
    ),
}


def get_style(style_id: str) -> Style:
    return STYLES.get(style_id, STYLES["wabi"])
