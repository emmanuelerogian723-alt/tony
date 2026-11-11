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
from .files_api import router as files_router
from .playground import router as playground_router
from . import files as _files_models
from . import playground as _pg_models  # noqa: F401  (registers file_objects)
from . import runtime as _runtime_models  # noqa: F401  (registers idempotency_records)
from . import events as _event_models  # noqa: F401  (inbound_events, subscriptions)
from . import flows as _flow_models  # noqa: F401  (flows, flow_steps)
from . import syncs as _sync_models  # noqa: F401  (syncs, sync_records)
from .billing import router as billing_router
from .customtools import router as customtools_router
from .assistant import router as assistant_router
from .power import router as power_router
from .ecosystem import router as ecosystem_router
from .mcp import router as mcp_router
from .connectlinks import router as connect_router
from .security import router as security_router
from .health import router as health_router
from .install import router as install_router
from .sessions import router as sessions_router
from .events import router as events_router
from .flows import router as flows_router
from .syncs import router as syncs_router
from .firewall import router as firewall_router
from .pages import router as pages_router

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
    # Nango-style safety net: refresh connections before they expire, quietly.
    try:
        import asyncio as _aio

        from . import connhealth as _ch

        app.state.conn_watch = _aio.create_task(_ch.watch(900))
    except Exception as exc:  # never block startup on the watcher
        log.warning("connection watcher not started: %s", exc)
    if catalog.errors:
        for err in catalog.errors:
            log.warning("manifest: %s", err)
    _poller_task = asyncio.create_task(poller())
    # Durable flow + sync workers: the half of Tony that wakes up on its own.
    from .flows import runner as _flow_runner
    from .syncs import runner as _sync_runner
    app.state.workers = [asyncio.create_task(_flow_runner()), asyncio.create_task(_sync_runner())]
    if settings.self_url and settings.ping_seconds > 0:
        _tasks = getattr(app.state, "tasks", [])
        _tasks.append(asyncio.create_task(self_ping(settings.self_url, settings.ping_seconds)))
        app.state.tasks = _tasks
    try:
        yield
    finally:
        for _t in getattr(app.state, "workers", []):
            _t.cancel()
        for _t in getattr(app.state, "workers", []):
            try:
                await _t
            except (asyncio.CancelledError, Exception):
                pass
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
app.include_router(files_router)
app.include_router(playground_router)
app.include_router(mcp_router)
@app.middleware("http")
async def shield_mw(request, call_next):
    from fastapi.responses import JSONResponse
    from . import shield
    try:
        shield.inspect(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    response = await call_next(request)
    if response.status_code in (401, 403) and request.url.path.startswith("/v1/") and \
            request.headers.get("authorization", "").lower().startswith("bearer "):
        try:
            shield.note_auth_failure(request)
        except HTTPException:
            pass
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


app.include_router(install_router)
app.include_router(health_router)
from .authflow import router as authflow_router  # one-click connect + connected accounts
app.include_router(authflow_router)
app.include_router(connect_router)
app.include_router(security_router)
app.include_router(billing_router)
app.include_router(sessions_router)
app.include_router(customtools_router)
app.include_router(assistant_router)
app.include_router(ecosystem_router)
app.include_router(power_router)
app.include_router(events_router)
app.include_router(flows_router)
app.include_router(syncs_router)
app.include_router(firewall_router)
app.include_router(pages_router)


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
    after = getattr(account, "_redirect_after", "") or ""
    # same-site paths only, so an authorization link can never become an open redirect
    if after.startswith("/connect/") and "//" not in after and "\\" not in after:
        return RedirectResponse(after)
    return RedirectResponse(f"/app?connection=ok&{urlencode({'app': account.app_slug})}")


@app.get("/providers", response_class=HTMLResponse)
def provider_setup(request: Request):
    from .accounts import require_user
    from .providerui import provider_setup_html

    try:
        require_user(request)
    except Exception:  # noqa: BLE001 - anonymous visitors go and sign in first
        return RedirectResponse("/account", status_code=307)
    return HTMLResponse(provider_setup_html())


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
