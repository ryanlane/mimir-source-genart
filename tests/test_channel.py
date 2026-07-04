"""Channel behavior tests — settings, seeds, request_image contract."""
import asyncio
import io
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "channels"))

from genart.channel import GenArtChannel
from genart.models import Settings


def _make_channel(tmp_path, **config):
    src_plugin = Path(__file__).parent.parent / "channels" / "genart" / "plugin.json"
    (tmp_path / "plugin.json").write_text(src_plugin.read_text())
    return GenArtChannel(str(tmp_path), config=config or None)


def test_settings_validation_clamps_bad_values():
    s = Settings.from_dict({
        "style": "vaporwave", "algorithm": "nope", "output_mode": "video",
        "seed_mode": "sometimes", "density": "extreme",
        "texture_strength": 999, "frames": 500, "frame_ms": 1,
    })
    assert s.style == "wabi"
    assert s.algorithm == "auto"
    assert s.output_mode == "static"
    assert s.seed_mode == "refresh"
    assert s.density == "balanced"
    assert s.texture_strength == 200
    assert s.frames == 60
    assert s.frame_ms == 40


def test_fixed_seed_mode_is_stable(tmp_path):
    ch = _make_channel(tmp_path, seed_mode="fixed", seed=123)
    assert ch._current_seed() == 123
    assert ch._current_seed() == 123


def test_refresh_seed_mode_varies(tmp_path):
    ch = _make_channel(tmp_path, seed_mode="refresh")
    seeds = {ch._current_seed() for _ in range(5)}
    assert len(seeds) > 1


def test_request_image_static_returns_png(tmp_path):
    ch = _make_channel(tmp_path, seed_mode="fixed", seed=7, output_mode="static")
    result = asyncio.run(ch.request_image({"settings": {"resolution": [240, 160]}}))
    assert result["success"] is True
    assert result["content_type"] == "image/png"
    img = Image.open(io.BytesIO(result["bytes"]))
    assert img.size == (240, 160)
    assert result["metadata"]["animated"] is False


def test_request_image_animated_returns_webp(tmp_path):
    ch = _make_channel(tmp_path, seed_mode="fixed", seed=7,
                       output_mode="animated", frames=8, frame_ms=100)
    result = asyncio.run(ch.request_image({"settings": {"resolution": [160, 100]}}))
    assert result["success"] is True
    assert result["content_type"] == "image/webp"
    img = Image.open(io.BytesIO(result["bytes"]))
    assert img.format == "WEBP"
    assert getattr(img, "n_frames", 1) == 8
    assert result["metadata"]["animated"] is True


def test_request_image_caches_fixed_seed(tmp_path):
    ch = _make_channel(tmp_path, seed_mode="fixed", seed=9)
    r1 = asyncio.run(ch.request_image({"settings": {"resolution": [200, 120]}}))
    r2 = asyncio.run(ch.request_image({"settings": {"resolution": [200, 120]}}))
    assert r1["cache_hit"] is False
    assert r2["cache_hit"] is True
    assert r1["sha256"] == r2["sha256"]


def test_settings_persist_roundtrip(tmp_path):
    ch = _make_channel(tmp_path, style="constructivist", output_mode="animated")
    saved = json.loads((tmp_path / "data" / "settings.json").read_text())
    assert saved["style"] == "constructivist"
    ch2 = GenArtChannel(str(tmp_path))
    assert ch2.settings.style == "constructivist"
    assert ch2.settings.output_mode == "animated"


def test_manifest_shape(tmp_path):
    ch = _make_channel(tmp_path)
    m = ch.get_manifest()
    assert m["id"] == "com.mimir.genart"
    assert m["configured"] is True
    assert m["capabilities"]["supports_push"] is False
