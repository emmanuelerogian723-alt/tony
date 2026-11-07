"""Engine, session helpers and bootstrap."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .crypto import new_api_key
from .models import ApiKey, Base, Workspace

_connect_args = {"check_same_thread": False} if settings.sqlalchemy_url.startswith("sqlite") else {}
engine = create_engine(
    settings.sqlalchemy_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


DB_STATUS: dict[str, str] = {"backend": "unknown", "error": ""}


def init_db() -> None:
    """Create tables. Never kills the process: a DB problem is reported, not fatal."""
    global engine, SessionLocal
    backend = "postgres" if settings.is_postgres else "sqlite"
    try:
        Base.metadata.create_all(engine)
    except Exception as exc:  # pragma: no cover - depends on deployment network
        if backend == "postgres":
            import logging

            logging.getLogger("tony").error("postgres unavailable (%s); falling back to sqlite", exc)
            DB_STATUS.update(backend="sqlite-fallback", error=f"{type(exc).__name__}: {exc}"[:300])
            from sqlalchemy import create_engine as _ce
            from sqlalchemy.orm import sessionmaker as _sm

            from .config import DATA_DIR

            DATA_DIR.mkdir(parents=True, exist_ok=True)
            engine = _ce(f"sqlite:///{(DATA_DIR / 'tony.db').as_posix()}",
                         connect_args={"check_same_thread": False}, pool_pre_ping=True, future=True)
            SessionLocal = _sm(bind=engine, expire_on_commit=False, future=True)
            Base.metadata.create_all(engine)
            return
        raise
    DB_STATUS.update(backend=backend, error="")


@contextmanager
def session() -> Iterator[Session]:
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def ensure_demo_workspace() -> tuple[Workspace, str]:
    """Create (once) the demo workspace and return its API key plaintext.

    In demo mode the plaintext is regenerated and returned; otherwise the key is
    created only on first boot and written to data/demo-key.txt for the operator.
    """
    with session() as s:
        ws = s.scalar(select(Workspace).where(Workspace.is_demo.is_(True)))
        if ws is None:
            ws = Workspace(name="Demo workspace", is_demo=True)
            s.add(ws)
            s.flush()
        key_row = s.scalar(select(ApiKey).where(ApiKey.workspace_id == ws.id, ApiKey.revoked.is_(False)))
        if key_row is not None:
            return ws, ""
        plain, prefix, hashed = new_api_key()
        s.add(ApiKey(workspace_id=ws.id, name="demo", prefix=prefix, key_hash=hashed))
        return ws, plain


def create_workspace(name: str) -> tuple[Workspace, str]:
    with session() as s:
        ws = Workspace(name=name or "Workspace")
        s.add(ws)
        s.flush()
        plain, prefix, hashed = new_api_key()
        s.add(ApiKey(workspace_id=ws.id, name="default", prefix=prefix, key_hash=hashed))
        return ws, plain
