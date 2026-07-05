"""Gallery model for the Generative Art channel.

A Gallery is one named, saved generative-art configuration (style,
algorithm, output mode, seed policy, density, texture) — a sub-channel in
Mimir's terms. Different galleries can be assigned to different programs
and displays, the same way other multi-item sources (headlines feeds,
comic-covers series) work.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from .mimir_utils import JsonStore
from .engines import ENGINES
from .styles import STYLES

OUTPUT_MODES = ("static", "animated")
SEED_MODES = ("refresh", "hourly", "daily", "fixed")
DENSITIES = {"sparse": 0.65, "balanced": 1.0, "rich": 1.4}

_FRAMES_RANGE = (8, 60)
_FRAME_MS_RANGE = (40, 500)


@dataclass
class Gallery:
    id: str = ""
    name: str = "New Gallery"
    style: str = "wabi"               # wabi | constructivist | ... | random
    algorithm: str = "auto"           # auto | engine id
    output_mode: str = "static"       # static (PNG, e-ink safe) | animated (WebP loop)
    seed_mode: str = "refresh"        # refresh | hourly | daily | fixed
    seed: int = 1                     # used when seed_mode == fixed
    density: str = "balanced"         # sparse | balanced | rich
    texture_strength: int = 100       # percent of the style's default texture
    frames: int = 24                  # animated mode: frames per loop
    frame_ms: int = 120               # animated mode: per-frame duration
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Gallery":
        if not isinstance(d, dict):
            return cls()
        known = set(cls.__dataclass_fields__)
        g = cls(**{k: v for k, v in d.items() if k in known})
        if g.style != "random" and g.style not in STYLES:
            g.style = "wabi"
        if g.algorithm != "auto" and g.algorithm not in ENGINES:
            g.algorithm = "auto"
        if g.output_mode not in OUTPUT_MODES:
            g.output_mode = "static"
        if g.seed_mode not in SEED_MODES:
            g.seed_mode = "refresh"
        if g.density not in DENSITIES:
            g.density = "balanced"
        try:
            g.seed = int(g.seed)
        except (TypeError, ValueError):
            g.seed = 1
        g.texture_strength = max(0, min(200, int(g.texture_strength or 0)))
        g.frames = max(_FRAMES_RANGE[0], min(_FRAMES_RANGE[1], int(g.frames or 24)))
        g.frame_ms = max(_FRAME_MS_RANGE[0], min(_FRAME_MS_RANGE[1], int(g.frame_ms or 120)))
        if not g.name or not g.name.strip():
            g.name = "New Gallery"
        return g

    @classmethod
    def create(cls, data: dict[str, Any]) -> "Gallery":
        data = dict(data or {})
        if not data.get("id"):
            data["id"] = str(uuid.uuid4())
        if not data.get("created_at"):
            data["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return cls.from_dict(data)

    @property
    def density_factor(self) -> float:
        return DENSITIES.get(self.density, 1.0)

    @property
    def texture_factor(self) -> float:
        return self.texture_strength / 100.0


class GalleryStore(JsonStore[Gallery]):
    def _from_dict(self, d: dict[str, Any]) -> Gallery:
        return Gallery.from_dict(d)

    def _to_dict(self, item: Gallery) -> dict[str, Any]:
        return item.to_dict()

    def _new_item(self, data: dict[str, Any]) -> Gallery:
        return Gallery.create(data)
