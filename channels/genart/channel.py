"""Generative Art channel for Mimir.

Renders algorithmic, gallery-grade generative art locally with Pillow —
no external APIs. Eight print styles share thirteen composition engines.
Output is either a static PNG (e-ink safe) or a seamless animated WebP
loop (LCD/OLED).

A **Gallery** is one named, saved configuration (style, algorithm, output
mode, seed policy, density, texture) — a sub-channel. Different galleries
can be assigned to different programs and displays; request_image picks
the gallery named by the caller (subchannel_id / gallery_id /
settings.subChannelId), falling back to the first configured gallery.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .engines import ENGINE_INFO, pick_engine
from .models import Gallery, GalleryStore
from .styles import STYLES, resolve_style
from . import renderer as _renderer

logger = logging.getLogger("mimir.channels.genart")

_PLUGIN_ID = "com.mimir.genart"
_PREVIEW_MAX = 640


class GenArtChannel:
    def __init__(self, channel_dir: str):
        self.channel_dir = Path(channel_dir)
        self.data_dir = self.channel_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self._meta = self._load_plugin_json()
        self.id = self._meta.get("id", _PLUGIN_ID)
        self.store = GalleryStore(self.data_dir / "galleries.json")

        self.supports_push = False

        # Rendered-output cache. Animated WebPs run to a few MB, so the
        # cache stays small and clears wholesale when full.
        self._image_cache: Dict[str, Dict[str, Any]] = {}
        self._IMAGE_CACHE_MAX = 6
        self._render_lock = asyncio.Lock()
        self._last_render: Optional[Dict[str, Any]] = None

        logger.info("[genart] Initialized at %s, %d galleries", self.channel_dir, len(self.store.all()))

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_plugin_json(self) -> Dict[str, Any]:
        try:
            with open(self.channel_dir / "plugin.json") as f:
                import json
                return json.load(f)
        except Exception:
            return {}

    # ── Seeds ─────────────────────────────────────────────────────────────

    def _current_seed(self, gallery: Gallery) -> int:
        mode = gallery.seed_mode
        if mode == "fixed":
            return gallery.seed
        now = datetime.now(timezone.utc)
        if mode == "daily":
            basis = now.strftime("%Y-%m-%d") + gallery.id
        elif mode == "hourly":
            basis = now.strftime("%Y-%m-%d-%H") + gallery.id
        else:  # refresh — new piece on every render request
            return int.from_bytes(hashlib.sha256(str(time.time_ns()).encode()).digest()[:4], "big")
        return int.from_bytes(hashlib.sha256(basis.encode()).digest()[:4], "big")

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render_sync(self, gallery: Gallery, seed: int, w: int, h: int,
                     animated: bool) -> Dict[str, Any]:
        started = time.time()
        if animated:
            data = _renderer.render_animated(
                gallery.style, gallery.algorithm, seed, w, h,
                frames=gallery.frames, frame_ms=gallery.frame_ms,
                density=gallery.density_factor, texture_strength=gallery.texture_factor,
            )
            content_type, fmt = "image/webp", "webp"
        else:
            data = _renderer.render_static(
                gallery.style, gallery.algorithm, seed, w, h,
                density=gallery.density_factor, texture_strength=gallery.texture_factor,
            )
            content_type, fmt = "image/png", "png"

        engine_id = pick_engine(gallery.algorithm, random.Random(seed))
        style = resolve_style(gallery.style, seed)
        entry = {
            "bytes":        data,
            "content_type": content_type,
            "format":       fmt,
            "sha256":       hashlib.sha256(data).hexdigest(),
            "description":  f"{gallery.name} — {style.name} — {engine_id} #{seed}",
            "seed":         seed,
            "engine":       engine_id,
            "style":        style.id,
            "render_ms":    round((time.time() - started) * 1000),
        }
        return entry

    def _cache_key(self, gallery: Gallery, seed: int, w: int, h: int, animated: bool) -> str:
        # Keyed on the *effective* mode: an animated gallery serves static
        # renders to displays that report supports_animation=false, and both
        # variants may be cached side by side.
        mode = "animated" if animated else "static"
        return "|".join(str(v) for v in (
            gallery.id, seed, w, h, gallery.style, gallery.algorithm, mode,
            gallery.density, gallery.texture_strength, gallery.frames, gallery.frame_ms,
        ))

    def _resolve_gallery(self, data: Dict[str, Any]) -> Optional[Gallery]:
        gallery_id = (
            data.get("subchannel_id")
            or data.get("gallery_id")
            or (data.get("settings") or {}).get("subChannelId")
        )
        if gallery_id:
            gallery = self.store.get(gallery_id)
            if gallery:
                return gallery
        galleries = self.store.all()
        return galleries[0] if galleries else None

    async def request_image(self, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = request_data or {}
        gallery = self._resolve_gallery(data)
        if not gallery:
            return {"success": False, "error": "No gallery configured — add one in the channel manager"}

        settings_block = data.get("settings", {})
        res = settings_block.get("resolution", [800, 480])
        width, height = int(res[0]), int(res[1])

        # Capability negotiation: displays report whether their panel can
        # play animated loops. An explicit False downgrades an animated
        # gallery to a static render of the same piece; absent/None means
        # unknown, and the gallery's configured mode is honored.
        animated = gallery.output_mode == "animated"
        if animated and settings_block.get("supports_animation") is False:
            animated = False
            logger.debug("[genart] display reports supports_animation=false — serving static render")

        seed = self._current_seed(gallery)
        cache_key = self._cache_key(gallery, seed, width, height, animated)
        cached = self._image_cache.get(cache_key)
        if cached:
            return self._build_response(cached, width, height, hit=True)

        # Serialize renders — animated pieces are CPU-heavy and a scene with
        # several displays fires refreshes in bursts.
        async with self._render_lock:
            cached = self._image_cache.get(cache_key)
            if cached:
                return self._build_response(cached, width, height, hit=True)
            loop = asyncio.get_event_loop()
            try:
                entry = await loop.run_in_executor(
                    None, self._render_sync, gallery, seed, width, height, animated)
            except Exception as exc:
                logger.exception("[genart] render failed: %s", exc)
                return {"success": False, "error": f"render failed: {exc}"}

            if len(self._image_cache) >= self._IMAGE_CACHE_MAX:
                self._image_cache.clear()
            self._image_cache[cache_key] = entry
            self._last_render = {
                "gallery_id": gallery.id, "gallery_name": gallery.name,
                "seed": entry["seed"], "engine": entry["engine"], "style": entry["style"],
                "output_mode": gallery.output_mode,
                "resolution": [width, height], "render_ms": entry["render_ms"],
                "at": time.time(),
            }
            logger.info("[genart] rendered gallery=%s %s seed=%s %dx%d in %dms",
                        gallery.name, entry["engine"], entry["seed"], width, height, entry["render_ms"])
        return self._build_response(entry, width, height, hit=False)

    def _build_response(self, entry: Dict[str, Any], width: int, height: int, hit: bool) -> Dict[str, Any]:
        return {
            "success":             True,
            "bytes":               entry["bytes"],
            "content_type":        entry["content_type"],
            "format":              entry["format"],
            "sha256":              entry["sha256"],
            "preferred_transport": "bytes",
            "width":               width,
            "height":              height,
            "description":         entry["description"],
            "cache_hit":           hit,
            "metadata": {
                "style":     entry["style"],
                "engine":    entry["engine"],
                "seed":      entry["seed"],
                "animated":  entry["format"] == "webp",
            },
        }

    # ── Manifest / subchannels ──────────────────────────────────────────────

    def get_manifest(self) -> Dict[str, Any]:
        galleries = self.store.all()
        return {
            "id":          self.id,
            "name":        self._meta.get("name", "Generative Art"),
            "version":     self._meta.get("version", "1.0.0"),
            "description": self._meta.get("description", ""),
            "icon":        self._meta.get("icon", "shapes"),
            "capabilities": {
                "supports_upload":      False,
                "supports_subchannels": True,
                "supports_push":        False,
                "supports_now_playing": False,
            },
            "ui": {
                "components": {"manager": f"/api/channels/{self.id}/ui/manage.esm.js"},
                "elements":   {"manager": "x-genart-manager"},
            },
            "healthy":        True,
            "configured":     bool(galleries),
            "setup_required": not bool(galleries),
            "display_count":  len(galleries),
        }

    def supports_subchannels(self) -> bool:
        return True

    def get_subchannels(self) -> List[Dict[str, Any]]:
        return [
            {
                "id":            g.id,
                "name":          g.name,
                "image_count":   1,
                "type":          "subchannel",
                "style":         g.style,
                "algorithm":     g.algorithm,
                "output_mode":   g.output_mode,
            }
            for g in self.store.all()
        ]

    def get_subchannel(self, subchannel_id: str) -> Optional[Dict[str, Any]]:
        g = self.store.get(subchannel_id)
        return g.to_dict() if g else None

    # ── FastAPI router ────────────────────────────────────────────────────

    def get_router(self) -> APIRouter:
        router = APIRouter()
        _ui_dir = self.channel_dir / "ui"

        def _render_preview_bytes(gallery: Gallery, w: int, h: int) -> bytes:
            seed = self._current_seed(gallery) if gallery.seed_mode == "fixed" else (gallery.seed or 1)
            if gallery.output_mode == "animated":
                return _renderer.render_animated(
                    gallery.style, gallery.algorithm, seed, w, h,
                    frames=gallery.frames, frame_ms=gallery.frame_ms,
                    density=gallery.density_factor, texture_strength=gallery.texture_factor,
                )
            return _renderer.render_static(
                gallery.style, gallery.algorithm, seed, w, h,
                density=gallery.density_factor, texture_strength=gallery.texture_factor,
            )

        @router.get("/ui/{filename:path}")
        async def serve_ui(filename: str):
            from fastapi.responses import FileResponse
            file_path = (_ui_dir / filename).resolve()
            try:
                file_path.relative_to(_ui_dir.resolve())
            except ValueError:
                raise HTTPException(403)
            if not file_path.exists():
                raise HTTPException(404)
            return FileResponse(str(file_path))

        @router.get("/manifest")
        async def manifest():
            return JSONResponse(self.get_manifest())

        @router.get("/status")
        async def status():
            return JSONResponse({
                "status":      "ok",
                "last_render": self._last_render,
                "galleries":   self.get_subchannels(),
                "styles":      [{"id": s.id, "name": s.name, "description": s.description}
                                for s in STYLES.values()],
                "algorithms":  ENGINE_INFO,
            })

        @router.get("/subchannels")
        async def list_subchannels():
            return JSONResponse(self.get_subchannels())

        @router.post("/subchannels")
        async def create_gallery(request: Request):
            body = await request.json()
            gallery = self.store.create(body)
            return JSONResponse(gallery.to_dict(), status_code=201)

        @router.get("/subchannels/{gallery_id}")
        async def get_gallery(gallery_id: str):
            g = self.store.get(gallery_id)
            if not g:
                raise HTTPException(404, "Gallery not found")
            return JSONResponse(g.to_dict())

        @router.put("/subchannels/{gallery_id}")
        async def update_gallery(gallery_id: str, request: Request):
            body = await request.json()
            g = self.store.update(gallery_id, body)
            if not g:
                raise HTTPException(404, "Gallery not found")
            self._image_cache.clear()
            return JSONResponse(g.to_dict())

        @router.delete("/subchannels/{gallery_id}")
        async def delete_gallery(gallery_id: str):
            if not self.store.delete(gallery_id):
                raise HTTPException(404, "Gallery not found")
            self._image_cache.clear()
            return JSONResponse({"success": True})

        @router.get("/subchannels/{gallery_id}/preview")
        async def preview_gallery(gallery_id: str, w: int = 400, h: int = 240):
            g = self.store.get(gallery_id)
            if not g:
                raise HTTPException(404, "Gallery not found")
            pw = max(64, min(_PREVIEW_MAX, w))
            ph = max(64, min(_PREVIEW_MAX, h))
            loop = asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(None, _render_preview_bytes, g, pw, ph)
            except Exception as exc:
                logger.exception("[genart] preview render failed: %s", exc)
                raise HTTPException(500, str(exc))
            media = "image/webp" if g.output_mode == "animated" else "image/png"
            return Response(content=data, media_type=media, headers={"Cache-Control": "no-store"})

        @router.post("/preview")
        async def preview_draft(request: Request):
            """Render a preview from an unsaved config (used during add/edit)."""
            body = await request.json()
            config_data = body.get("config", body)
            pw = max(64, min(_PREVIEW_MAX, int(body.get("w", 400))))
            ph = max(64, min(_PREVIEW_MAX, int(body.get("h", 240))))
            try:
                gallery = Gallery.from_dict({**config_data, "id": "draft"})
            except Exception as exc:
                raise HTTPException(422, f"Invalid config: {exc}")
            loop = asyncio.get_event_loop()
            try:
                # Drafts always preview as a static PNG — fast feedback while
                # editing; animated output is confirmed after saving.
                data = await loop.run_in_executor(
                    None,
                    lambda: _renderer.render_static(
                        gallery.style, gallery.algorithm, gallery.seed or 1, pw, ph,
                        density=gallery.density_factor, texture_strength=gallery.texture_factor,
                    ),
                )
            except Exception as exc:
                logger.exception("[genart] draft preview failed: %s", exc)
                raise HTTPException(500, str(exc))
            return Response(content=data, media_type="image/png", headers={"Cache-Control": "no-store"})

        @router.post("/request-image")
        async def request_image_route(request: Request):
            try:
                body = await request.json()
            except Exception:
                body = {}
            result = await self.request_image(body)
            if result.get("preferred_transport") == "bytes" and result.get("bytes"):
                return Response(content=result["bytes"],
                                media_type=result.get("content_type", "image/png"))
            return JSONResponse(result)

        return router
