"""Renderer output tests — formats, determinism, animation looping."""
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "channels"))

from genart import renderer
from genart.styles import STYLES


def test_static_render_is_png_at_requested_size():
    data = renderer.render_static("wabi", "arches", seed=11, w=320, h=200)
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    assert img.size == (320, 200)


def test_static_render_is_deterministic_per_seed():
    a = renderer.render_static("constructivist", "orbits", seed=5, w=200, h=120)
    b = renderer.render_static("constructivist", "orbits", seed=5, w=200, h=120)
    c = renderer.render_static("constructivist", "orbits", seed=6, w=200, h=120)
    assert a == b
    assert a != c


def test_animated_render_is_looping_webp():
    data = renderer.render_animated("wabi", "orbits", seed=3, w=160, h=100,
                                    frames=6, frame_ms=100)
    img = Image.open(io.BytesIO(data))
    assert img.format == "WEBP"
    assert getattr(img, "n_frames", 1) == 6
    assert img.size == (160, 100)


def test_random_style_varies_by_seed_but_is_stable():
    from genart.styles import resolve_style
    picked = {resolve_style("random", seed).id for seed in range(40)}
    assert len(picked) > 3, "random style should span multiple styles"
    assert resolve_style("random", 7).id == resolve_style("random", 7).id
    a = renderer.render_static("random", "arches", seed=7, w=160, h=100)
    b = renderer.render_static("random", "arches", seed=7, w=160, h=100)
    assert a == b


def test_styles_produce_distinct_output():
    a = renderer.render_static("wabi", "tatami", seed=9, w=200, h=120)
    b = renderer.render_static("constructivist", "tatami", seed=9, w=200, h=120)
    assert a != b


def test_paper_dominates_composition():
    """Negative space discipline: paper must remain the dominant field."""
    for style_id, style in STYLES.items():
        data = renderer.render_static(style_id, "tatami", seed=4, w=200, h=120)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        paper = style.paper
        px = list(img.getdata())
        near_paper = sum(
            1 for p in px
            if all(abs(p[i] - paper[i]) < 40 for i in range(3))
        )
        assert near_paper / len(px) > 0.3, f"{style_id} lost its negative space"
