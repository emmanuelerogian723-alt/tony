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


def init_db() -> None:
    Base.metadata.create_all(engine)


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
