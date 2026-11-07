"""Database models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), default="Workspace")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    keys: Mapped[list[ApiKey]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    prefix: Mapped[str] = mapped_column(String(24), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    workspace: Mapped[Workspace] = relationship(back_populates="keys")


class Entity(Base):
    """An end-user identity inside a workspace (the person whose accounts we connect)."""
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id", name="uq_entity"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(160), index=True)
    label: Mapped[str] = mapped_column(String(160), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    __table_args__ = (Index("ix_conn_lookup", "workspace_id", "entity_id", "app_slug"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), index=True)
    app_slug: Mapped[str] = mapped_column(String(80), index=True)
    auth_type: Mapped[str] = mapped_column(String(24), default="oauth2")
    status: Mapped[str] = mapped_column(String(24), default="active")  # active|expired|revoked|error
    label: Mapped[str] = mapped_column(String(160), default="")
    scopes: Mapped[str] = mapped_column(Text, default="")
    credentials_enc: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    """Pending OAuth dance."""
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160))
    app_slug: Mapped[str] = mapped_column(String(80))
    code_verifier: Mapped[str] = mapped_column(String(128), default="")
    redirect_after: Mapped[str] = mapped_column(String(400), default="/app")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class ActionRun(Base):
    __tablename__ = "action_runs"
    __table_args__ = (Index("ix_run_ws", "workspace_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), default="")
    app_slug: Mapped[str] = mapped_column(String(80), index=True)
    action_slug: Mapped[str] = mapped_column(String(80), index=True)
    tier: Mapped[str] = mapped_column(String(16), default="read")
    status: Mapped[str] = mapped_column(String(24), default="success")  # success|error|pending_approval|denied
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    chars_out: Mapped[int] = mapped_column(Integer, default=0)
    request_json: Mapped[str] = mapped_column(Text, default="{}")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class Trigger(Base):
    __tablename__ = "triggers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), default="")
    app_slug: Mapped[str] = mapped_column(String(80))
    action_slug: Mapped[str] = mapped_column(String(80))
    args_json: Mapped[str] = mapped_column(Text, default="{}")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    webhook_url: Mapped[str] = mapped_column(String(400), default="")
    secret: Mapped[str] = mapped_column(String(64), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    trigger_id: Mapped[str] = mapped_column(String(32), index=True)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    """A human who signs in to the console (Google or email+password)."""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    picture: Mapped[str] = mapped_column(String(500), default="")
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    google_sub: Mapped[str] = mapped_column(String(64), default="", index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSession(Base):
    """Opaque server-side session: the cookie holds a random token, we store its hash."""
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(String(200), default="")
