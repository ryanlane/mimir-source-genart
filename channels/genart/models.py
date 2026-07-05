"""Settings model for the Generative Art channel."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mimir_utils import SettingsMixin
from .engines import ENGINES
from .styles import STYLES

OUTPUT_MODES = ("static", "animated")
SEED_MODES = ("refresh", "hourly", "daily", "fixed")
DENSITIES = {"sparse": 0.65, "balanced": 1.0, "rich": 1.4}

_FRAMES_RANGE = (8, 60)
_FRAME_MS_RANGE = (40, 500)


@dataclass
class Settings(SettingsMixin):
    style: str = "wabi"              # wabi | constructivist
    algorithm: str = "auto"          # auto | engine id
    output_mode: str = "static"      # static (PNG, e-ink safe) | animated (WebP loop)
    seed_mode: str = "refresh"       # refresh | hourly | daily | fixed
    seed: int = 1                    # used when seed_mode == fixed
    density: str = "balanced"        # sparse | balanced | rich
    texture_strength: int = 100      # percent of the style's default texture
    frames: int = 24                 # animated mode: frames per loop
    frame_ms: int = 120              # animated mode: per-frame duration

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        if not isinstance(data, dict):
            return cls()
        s: Settings = super().from_dict(data)  # type: ignore[assignment]
        if s.style != "random" and s.style not in STYLES:
            s.style = "wabi"
        if s.algorithm != "auto" and s.algorithm not in ENGINES:
            s.algorithm = "auto"
        if s.output_mode not in OUTPUT_MODES:
            s.output_mode = "static"
        if s.seed_mode not in SEED_MODES:
            s.seed_mode = "refresh"
        if s.density not in DENSITIES:
            s.density = "balanced"
        try:
            s.seed = int(s.seed)
        except (TypeError, ValueError):
            s.seed = 1
        s.texture_strength = max(0, min(200, int(s.texture_strength or 0)))
        s.frames = max(_FRAMES_RANGE[0], min(_FRAMES_RANGE[1], int(s.frames or 24)))
        s.frame_ms = max(_FRAME_MS_RANGE[0], min(_FRAME_MS_RANGE[1], int(s.frame_ms or 120)))
        return s

    @property
    def density_factor(self) -> float:
        return DENSITIES.get(self.density, 1.0)

    @property
    def texture_factor(self) -> float:
        return self.texture_strength / 100.0
