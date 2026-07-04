"""Engine contract tests — every engine, every style, reproducibility."""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "channels"))

from genart.engines import ENGINES, ENGINE_INFO, pick_engine
from genart.styles import STYLES

SIZES = [(400, 240), (240, 400), (300, 300)]  # landscape, portrait, square


@pytest.mark.parametrize("engine_id", sorted(ENGINES))
@pytest.mark.parametrize("style_id", sorted(STYLES))
def test_engine_emits_valid_plates(engine_id, style_id):
    style = STYLES[style_id]
    for w, h in SIZES:
        plates = ENGINES[engine_id](random.Random(7), style, w, h, 0.0, 1.0)
        assert plates, f"{engine_id} emitted no plates at {w}x{h}"
        for ink_idx, mask, coverage in plates:
            assert 0 <= ink_idx < len(style.inks)
            assert mask.mode == "L"
            assert mask.size == (w, h)
            assert 0.0 < coverage <= 1.0
        # At least one plate must actually contain ink.
        assert any(m.getbbox() for _, m, _ in plates), f"{engine_id} drew nothing"


@pytest.mark.parametrize("engine_id", sorted(ENGINES))
def test_engine_is_seed_reproducible(engine_id):
    style = STYLES["wabi"]
    a = ENGINES[engine_id](random.Random(42), style, 300, 200, 0.0, 1.0)
    b = ENGINES[engine_id](random.Random(42), style, 300, 200, 0.0, 1.0)
    assert len(a) == len(b)
    for (ia, ma, ca), (ib, mb, cb) in zip(a, b):
        assert ia == ib and ca == cb
        assert ma.tobytes() == mb.tobytes()


def test_engine_info_covers_all_engines():
    assert {e["id"] for e in ENGINE_INFO} == set(ENGINES)


def test_pick_engine_resolves_auto_and_passthrough():
    assert pick_engine("orbits", random.Random(1)) == "orbits"
    picked = pick_engine("auto", random.Random(1))
    assert picked in ENGINES
    # auto is seed-stable
    assert pick_engine("auto", random.Random(1)) == picked
