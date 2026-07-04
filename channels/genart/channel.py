"""Generative Art channel for Mimir.

Renders algorithmic, gallery-grade generative art locally with Pillow —
no external APIs. Two print styles (Bauhaus × Wabi-Sabi giclée and 1960s
constructivist risograph) share six composition engines. Output is either
a static PNG (e-ink safe) or a seamless animated WebP loop (LCD/OLED).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .engines import ENGINE_INFO, pick_engine
from .models import Settings
from .styles import STYLES
from . import renderer as _renderer

logger = logging.getLogger("mimir.channels.genart")

_PLUGIN_ID = "com.mimir.genart"
_PREVIEW_MAX = 640


class GenArtChannel:
    def __init__(self, channel_dir: str, config: Optional[Dict[str, Any]] = None):
        self.channel_dir = Path(channel_dir)
        self.data_dir = self.channel_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self._settings_path = self.data_dir / "settings.json"
        self._meta = self._load_plugin_json()
        self.id = self._meta.get("id", _PLUGIN_ID)
        self.settings = self._load_settings()
        if config:
            self.settings = Settings.from_dict({**self.settings.to_dict(), **config})
            self._save_settings()

        self.supports_push = False

        # Rendered-output cache. Animated WebPs run to a few MB, so the
        # cache stays small and clears wholesale when full.
        self._image_cache: Dict[str, Dict[str, Any]] = {}
        self._IMAGE_CACHE_MAX = 6
        self._render_lock = asyncio.Lock()
        self._last_render: Optional[Dict[str, Any]] = None

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_plugin_json(self) -> Dict[str, Any]:
        try:
            with open(self.channel_dir / "plugin.json") as f:
                return json.load(f)
        except Exception:
            return {}

    def _load_settings(self) -> Settings:
        try:
            return Settings.from_dict(json.loads(self._settings_path.read_text()))
        except FileNotFoundError:
            return Settings()
        except Exception as exc:
            logger.warning("[genart] could not load settings: %s", exc)
            return Settings()

    def _save_settings(self) -> None:
        try:
            self._settings_path.write_text(json.dumps(self.settings.to_dict(), indent=2))
        except Exception as exc:
            logger.warning("[genart] could not save settings: %s", exc)

    # ── Seeds ─────────────────────────────────────────────────────────────

    def _current_seed(self) -> int:
        mode = self.settings.seed_mode
        if mode == "fixed":
            return self.settings.seed
        now = datetime.now(timezone.utc)
        if mode == "daily":
            basis = now.strftime("%Y-%m-%d")
        elif mode == "hourly":
            basis = now.strftime("%Y-%m-%d-%H")
        else:  # refresh — new piece on every render request
            return int.from_bytes(hashlib.sha256(str(time.time_ns()).encode()).digest()[:4], "big")
        return int.from_bytes(hashlib.sha256(basis.encode()).digest()[:4], "big")

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render_sync(self, seed: int, w: int, h: int) -> Dict[str, Any]:
        s = self.settings
        started = time.time()
        if s.output_mode == "animated":
            data = _renderer.render_animated(
                s.style, s.algorithm, seed, w, h,
                frames=s.frames, frame_ms=s.frame_ms,
                density=s.density_factor, texture_strength=s.texture_factor,
            )
            content_type, fmt = "image/webp", "webp"
        else:
            data = _renderer.render_static(
                s.style, s.algorithm, seed, w, h,
                density=s.density_factor, texture_strength=s.texture_factor,
            )
            content_type, fmt = "image/png", "png"

        import random as _random
        engine_id = pick_engine(s.algorithm, _random.Random(seed))
        style = STYLES[s.style]
        entry = {
            "bytes":        data,
            "content_type": content_type,
            "format":       fmt,
            "sha256":       hashlib.sha256(data).hexdigest(),
            "description":  f"{style.name} — {engine_id} #{seed}",
            "seed":         seed,
            "engine":       engine_id,
            "render_ms":    round((time.time() - started) * 1000),
        }
        return entry

    def _cache_key(self, seed: int, w: int, h: int) -> str:
        s = self.settings
        return "|".join(str(v) for v in (
            seed, w, h, s.style, s.algorithm, s.output_mode,
            s.density, s.texture_strength, s.frames, s.frame_ms,
        ))

    async def request_image(self, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        rd = request_data or {}
        settings_block = rd.get("settings", {})
        res = settings_block.get("resolution", [800, 480])
        width, height = int(res[0]), int(res[1])

        seed = self._current_seed()
        cache_key = self._cache_key(seed, width, height)
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
                entry = await loop.run_in_executor(None, self._render_sync, seed, width, height)
            except Exception as exc:
                logger.exception("[genart] render failed: %s", exc)
                return {"success": False, "error": f"render failed: {exc}"}

            if len(self._image_cache) >= self._IMAGE_CACHE_MAX:
                self._image_cache.clear()
            self._image_cache[cache_key] = entry
            self._last_render = {
                "seed": entry["seed"], "engine": entry["engine"],
                "style": self.settings.style, "output_mode": self.settings.output_mode,
                "resolution": [width, height], "render_ms": entry["render_ms"],
                "at": time.time(),
            }
            logger.info("[genart] rendered %s seed=%s %dx%d in %dms",
                        entry["engine"], entry["seed"], width, height, entry["render_ms"])
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
                "style":     self.settings.style,
                "engine":    entry["engine"],
                "seed":      entry["seed"],
                "animated":  entry["format"] == "webp",
            },
        }

    # ── Manifest ──────────────────────────────────────────────────────────

    def get_manifest(self) -> Dict[str, Any]:
        return {
            "id":          self.id,
            "name":        self._meta.get("name", "Generative Art"),
            "version":     self._meta.get("version", "1.0.0"),
            "description": self._meta.get("description", ""),
            "icon":        self._meta.get("icon", "shapes"),
            "capabilities": {
                "supports_upload":      False,
                "supports_subchannels": False,
                "supports_push":        False,
                "supports_now_playing": False,
            },
            "ui": {
                "components": {"manager": f"/api/channels/{self.id}/ui/manage.esm.js"},
                "elements":   {"manager": "x-genart-manager"},
            },
            "healthy":    True,
            "configured": True,  # no external service — always ready
        }

    # ── FastAPI router ────────────────────────────────────────────────────

    def get_router(self) -> APIRouter:
        router = APIRouter()
        _ui_dir = self.channel_dir / "ui"

        @router.get("/ui/{filename:path}")
        async def serve_ui(filename: str):
            from fastapi.responses import FileResponse
            from fastapi import HTTPException
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
                "styles":      [{"id": s.id, "name": s.name, "description": s.description}
                                for s in STYLES.values()],
                "algorithms":  ENGINE_INFO,
            })

        @router.get("/settings")
        async def get_settings():
            return JSONResponse({"success": True, "settings": self.settings.to_public_dict()})

        @router.put("/settings")
        async def put_settings(request: Request):
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"success": False, "error": "invalid JSON"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"success": False, "error": "expected object"}, status_code=400)
            self.settings = Settings.from_dict({**self.settings.to_dict(), **body})
            self._save_settings()
            self._image_cache.clear()
            return JSONResponse({"success": True, "settings": self.settings.to_public_dict()})

        @router.get("/preview")
        async def preview(width: int = 400, height: int = 240,
                          style: str = "", algorithm: str = "", seed: int = 0):
            """Small static render for the manage UI — always PNG."""
            w = max(64, min(_PREVIEW_MAX, width))
            h = max(64, min(_PREVIEW_MAX, height))
            s = self.settings
            style_id = style if style in STYLES else s.style
            algo = algorithm or s.algorithm
            loop = asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(
                    None,
                    lambda: _renderer.render_static(
                        style_id, algo, seed or 1, w, h,
                        density=s.density_factor, texture_strength=s.texture_factor,
                    ),
                )
            except Exception as exc:
                logger.exception("[genart] preview render failed: %s", exc)
                return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
            return Response(content=data, media_type="image/png")

        @router.post("/request-image")
        async def request_image(request: Request):
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
