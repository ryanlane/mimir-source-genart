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
}


def get_style(style_id: str) -> Style:
    return STYLES.get(style_id, STYLES["wabi"])
