"""Channel behavior tests — gallery CRUD, seeds, request_image resolution."""
import asyncio
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent / "channels"))

from genart.channel import GenArtChannel
from genart.models import Gallery


def _make_channel(tmp_path):
    src_plugin = Path(__file__).parent.parent / "channels" / "genart" / "plugin.json"
    (tmp_path / "plugin.json").write_text(src_plugin.read_text())
    return GenArtChannel(str(tmp_path))


def _make_gallery(ch, **overrides):
    data = {"name": "Test Gallery", **overrides}
    return ch.store.create(data)


def test_gallery_validation_clamps_bad_values():
    g = Gallery.from_dict({
        "style": "vaporwave", "algorithm": "nope", "output_mode": "video",
        "seed_mode": "sometimes", "density": "extreme",
        "texture_strength": 999, "frames": 500, "frame_ms": 1,
    })
    assert g.style == "wabi"
    assert g.algorithm == "auto"
    assert g.output_mode == "static"
    assert g.seed_mode == "refresh"
    assert g.density == "balanced"
    assert g.texture_strength == 200
    assert g.frames == 60
    assert g.frame_ms == 40


def test_gallery_random_style_passes_through():
    g = Gallery.from_dict({"style": "random"})
    assert g.style == "random"


def test_gallery_blank_name_gets_default():
    g = Gallery.from_dict({"name": "   "})
    assert g.name == "New Gallery"


def test_fixed_seed_mode_is_stable(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=123)
    assert ch._current_seed(gallery) == 123
    assert ch._current_seed(gallery) == 123


def test_refresh_seed_mode_varies(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="refresh")
    seeds = {ch._current_seed(gallery) for _ in range(5)}
    assert len(seeds) > 1


def test_request_image_with_no_galleries_returns_error(tmp_path):
    ch = _make_channel(tmp_path)
    result = asyncio.run(ch.request_image({"settings": {"resolution": [240, 160]}}))
    assert result["success"] is False
    assert "gallery" in result["error"].lower()


def test_request_image_falls_back_to_first_gallery(tmp_path):
    ch = _make_channel(tmp_path)
    _make_gallery(ch, name="Only One", seed_mode="fixed", seed=7)
    result = asyncio.run(ch.request_image({"settings": {"resolution": [240, 160]}}))
    assert result["success"] is True


def test_request_image_resolves_gallery_by_subchannel_id(tmp_path):
    ch = _make_channel(tmp_path)
    _make_gallery(ch, name="First", seed_mode="fixed", seed=1, style="wabi")
    second = _make_gallery(ch, name="Second", seed_mode="fixed", seed=1, style="constructivist")
    result = asyncio.run(ch.request_image({
        "subchannel_id": second.id,
        "settings": {"resolution": [200, 120]},
    }))
    assert result["success"] is True
    assert result["metadata"]["style"] == "constructivist"


def test_request_image_resolves_gallery_via_settings_subchannelid(tmp_path):
    ch = _make_channel(tmp_path)
    target = _make_gallery(ch, name="Target", seed_mode="fixed", seed=1, style="neon")
    result = asyncio.run(ch.request_image({
        "settings": {"resolution": [200, 120], "subChannelId": target.id},
    }))
    assert result["success"] is True
    assert result["metadata"]["style"] == "neon"


def test_request_image_unknown_gallery_id_falls_back(tmp_path):
    ch = _make_channel(tmp_path)
    _make_gallery(ch, name="Fallback", seed_mode="fixed", seed=1)
    result = asyncio.run(ch.request_image({
        "subchannel_id": "does-not-exist",
        "settings": {"resolution": [200, 120]},
    }))
    assert result["success"] is True


def test_request_image_static_returns_png(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=7, output_mode="static")
    result = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id, "settings": {"resolution": [240, 160]},
    }))
    assert result["success"] is True
    assert result["content_type"] == "image/png"
    img = Image.open(io.BytesIO(result["bytes"]))
    assert img.size == (240, 160)
    assert result["metadata"]["animated"] is False


def test_request_image_animated_returns_webp(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=7,
                            output_mode="animated", frames=8, frame_ms=100)
    result = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id, "settings": {"resolution": [160, 100]},
    }))
    assert result["success"] is True
    assert result["content_type"] == "image/webp"
    img = Image.open(io.BytesIO(result["bytes"]))
    assert img.format == "WEBP"
    assert getattr(img, "n_frames", 1) == 8
    assert result["metadata"]["animated"] is True


def test_animated_gallery_downgrades_when_display_cannot_animate(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=7,
                            output_mode="animated", frames=8)
    result = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id,
        "settings": {"resolution": [160, 100], "supports_animation": False},
    }))
    assert result["success"] is True
    assert result["content_type"] == "image/png"
    assert result["metadata"]["animated"] is False


def test_animated_gallery_stays_animated_when_capability_unknown_or_true(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=7,
                            output_mode="animated", frames=8)
    for settings in ({"resolution": [160, 100]},
                     {"resolution": [160, 100], "supports_animation": True}):
        result = asyncio.run(ch.request_image({
            "subchannel_id": gallery.id, "settings": settings,
        }))
        assert result["content_type"] == "image/webp"
        assert result["metadata"]["animated"] is True


def test_downgraded_and_animated_renders_cache_separately(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=7,
                            output_mode="animated", frames=8)
    anim = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id, "settings": {"resolution": [160, 100]},
    }))
    static = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id,
        "settings": {"resolution": [160, 100], "supports_animation": False},
    }))
    assert anim["content_type"] == "image/webp"
    assert static["content_type"] == "image/png"
    # Both cached independently — repeat requests hit their own entries.
    anim2 = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id, "settings": {"resolution": [160, 100]},
    }))
    assert anim2["cache_hit"] is True
    assert anim2["content_type"] == "image/webp"


def test_request_image_caches_fixed_seed(tmp_path):
    ch = _make_channel(tmp_path)
    gallery = _make_gallery(ch, seed_mode="fixed", seed=9)
    r1 = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id, "settings": {"resolution": [200, 120]},
    }))
    r2 = asyncio.run(ch.request_image({
        "subchannel_id": gallery.id, "settings": {"resolution": [200, 120]},
    }))
    assert r1["cache_hit"] is False
    assert r2["cache_hit"] is True
    assert r1["sha256"] == r2["sha256"]


def test_gallery_crud_persists(tmp_path):
    ch = _make_channel(tmp_path)
    created = ch.store.create({"name": "Persisted", "style": "deco"})
    ch2 = GenArtChannel(str(tmp_path))
    reloaded = ch2.store.get(created.id)
    assert reloaded is not None
    assert reloaded.name == "Persisted"
    assert reloaded.style == "deco"

    ch2.store.update(created.id, {"name": "Renamed"})
    ch3 = GenArtChannel(str(tmp_path))
    assert ch3.store.get(created.id).name == "Renamed"

    assert ch3.store.delete(created.id) is True
    assert ch3.store.get(created.id) is None


def test_get_subchannels_lists_galleries(tmp_path):
    ch = _make_channel(tmp_path)
    _make_gallery(ch, name="A")
    _make_gallery(ch, name="B")
    subchannels = ch.get_subchannels()
    assert {s["name"] for s in subchannels} == {"A", "B"}


def test_manifest_reflects_gallery_state(tmp_path):
    ch = _make_channel(tmp_path)
    m = ch.get_manifest()
    assert m["id"] == "com.mimir.genart"
    assert m["configured"] is False
    assert m["setup_required"] is True
    assert m["capabilities"]["supports_subchannels"] is True
    assert m["capabilities"]["supports_push"] is False

    _make_gallery(ch)
    m2 = ch.get_manifest()
    assert m2["configured"] is True
    assert m2["setup_required"] is False
    assert m2["display_count"] == 1
