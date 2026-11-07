"""Tony application entrypoint."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .mcp import router as mcp_router

from . import __version__
from .catalog import catalog
from .config import settings
from .db import ensure_demo_workspace, init_db
from .oauth import OAuthError, complete_oauth
from .triggers import poller
from .ui import dashboard_html
from .landing import landing_html

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tony")

_poller_task: asyncio.Task | None = None
demo_key: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _poller_task, demo_key
    init_db()
    ws, key = ensure_demo_workspace()
    demo_key = key
    log.info("Tony %s ready — %s apps, %s actions", __version__, catalog.stats()["apps"], catalog.stats()["actions"])
    if catalog.errors:
        for err in catalog.errors:
            log.warning("manifest: %s", err)
    _poller_task = asyncio.create_task(poller())
    try:
        yield
    finally:
        if _poller_task:
            _poller_task.cancel()
            try:
                await _poller_task
            except asyncio.CancelledError:
                pass


logger = logging.getLogger("tony")

app = FastAPI(
    title="Tony",
    version=__version__,
    description="Open-source integration gateway: connect any app, let any agent act on it.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router)
app.include_router(mcp_router)


_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")



@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(_STATIC / "brand" / "favicon.ico", media_type="image/x-icon")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def touch_icon():
    return FileResponse(_STATIC / "brand" / "tony-180.png", media_type="image/png")


@app.get("/site.webmanifest", include_in_schema=False)
def manifest():
    return JSONResponse({
        "name": "Tony — every app, one port",
        "short_name": "Tony",
        "description": "Open-source integration gateway. 9,877 apps, 22,107 actions.",
        "start_url": "/app",
        "display": "standalone",
        "background_color": "#F3F0E9",
        "theme_color": "#0E0E0C",
        "icons": [
            {"src": "/static/brand/tony-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/brand/tony-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "apps": catalog.stats()["apps"],
        "actions": catalog.stats()["actions"],
        "manifest_errors": len(catalog.errors),
        "demo_open": settings.demo_open,
    }


@app.get("/v1/openapi.json", include_in_schema=False)
def openapi_alias():
    return app.openapi()


@app.get("/oauth/callback")
async def oauth_callback(code: str = "", state: str = "", error: str = "", error_description: str = ""):
    if error:
        return RedirectResponse(f"/app?connection=error&{urlencode({'reason': error_description or error})}")
    if not code or not state:
        return RedirectResponse("/app?connection=error&reason=missing_code")
    try:
        account = await complete_oauth(state, code)
    except OAuthError as exc:
        return RedirectResponse(f"/app?connection=error&{urlencode({'reason': str(exc)})}")
    return RedirectResponse(f"/app?connection=ok&{urlencode({'app': account.app_slug})}")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing(request: Request):
    return HTMLResponse(landing_html())


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request):
    from .auth import workspace_from_request
    key = ""
    ws_id = ""
    try:
        ws_id, is_demo = workspace_from_request(request)
        if is_demo and demo_key:
            key = demo_key
    except Exception as exc:
        logger.warning("demo bootstrap skipped: %s", exc)
    return HTMLResponse(dashboard_html(key=key, workspace_id=ws_id, demo_open=settings.demo_open))


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover
    log.exception("unhandled error")
    return JSONResponse({"ok": False, "error": f"Internal error: {type(exc).__name__}"}, status_code=500)
