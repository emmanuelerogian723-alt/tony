"""Tony application entrypoint."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .accounts import router as account_router
from .api import router as api_router
from .billing import router as billing_router
from .customtools import router as customtools_router
from .assistant import router as assistant_router
from .ecosystem import router as ecosystem_router
from .mcp import router as mcp_router
from .sessions import router as sessions_router

from . import __version__
from .catalog import catalog
from .config import settings
from .db import DB_STATUS, ensure_demo_workspace, init_db
from .oauth import OAuthError, complete_oauth
from .triggers import poller
from .ui import dashboard_html
from .landing import landing_html

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tony")

_poller_task: asyncio.Task | None = None
demo_key: str = ""


async def self_ping(base: str, every: int) -> None:
    """Keep a free Render instance from idling out (public URL, every N seconds)."""
    import httpx

    await asyncio.sleep(20)
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            try:
                r = await client.get(f"{base}/health")
                log.info("self-ping %s %s", r.status_code, base)
            except Exception as exc:  # network hiccup is not fatal
                log.warning("self-ping failed: %s", exc)
            await asyncio.sleep(max(60, every))


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
    if settings.self_url and settings.ping_seconds > 0:
        _tasks = getattr(app.state, "tasks", [])
        _tasks.append(asyncio.create_task(self_ping(settings.self_url, settings.ping_seconds)))
        app.state.tasks = _tasks
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


app.include_router(account_router)
app.include_router(api_router)
app.include_router(mcp_router)
app.include_router(billing_router)
app.include_router(sessions_router)
app.include_router(customtools_router)
app.include_router(assistant_router)
app.include_router(ecosystem_router)


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
        "db": DB_STATUS.get("backend"),
        "db_error": DB_STATUS.get("error", "")[:300],
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


@app.get("/account", response_class=HTMLResponse, include_in_schema=False)
def account_page(request: Request):
    from .accounts import current_user
    from .console import console_html

    user = current_user(request)
    return HTMLResponse(console_html(user=user))


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing(request: Request):
    return HTMLResponse(landing_html())


@app.get("/app", include_in_schema=False)
def dashboard_redirect():
    return RedirectResponse("/account", status_code=307)


def _old_dashboard(request: Request):
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


@app.get("/sdk", response_class=HTMLResponse, include_in_schema=False)
def sdk_page():
    """Download page for the five official clients."""
    from .static_sdk import sdk_html

    return HTMLResponse(sdk_html())


@app.get("/sdk/{filename}", include_in_schema=False)
def sdk_file(filename: str):
    from pathlib import Path

    from fastapi.responses import PlainTextResponse

    allowed = {"tony_sdk.py": "python/tony_sdk.py", "tony.ts": "typescript/tony.ts",
               "tony.js": "javascript/tony.js", "tony.go": "go/tony.go", "Tony.java": "java/Tony.java"}
    rel = allowed.get(filename)
    if not rel:
        raise HTTPException(404, detail="Unknown SDK file")
    path = Path(__file__).resolve().parent.parent / "sdk" / rel
    return PlainTextResponse(path.read_text(), media_type="text/plain",
                             headers={"content-disposition": f'attachment; filename="{filename}"'})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover
    log.exception("unhandled error")
    return JSONResponse({"ok": False, "error": f"Internal error: {type(exc).__name__}"}, status_code=500)
