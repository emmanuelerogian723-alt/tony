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
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
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


class OAuthProvider(Base):
    """OAuth client registered once by the owner so users just sign in.

    Users never paste client ids or secrets: they click Connect, land on the
    provider's own login page, and come back connected.
    """

    __tablename__ = "oauth_providers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    app_slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    client_id: Mapped[str] = mapped_column(String(400), default="")
    secret_enc: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Subscription(Base):
    """One row per console user: which plan they are on and until when."""
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    plan: Mapped[str] = mapped_column(String(24), default="free")  # free|pro|business
    status: Mapped[str] = mapped_column(String(24), default="active")  # active|trialing|past_due|cancelled
    provider: Mapped[str] = mapped_column(String(24), default="none")  # none|paystack|passcode|admin
    external_ref: Mapped[str] = mapped_column(String(120), default="")
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class PaymentEvent(Base):
    """Every checkout we started or payment we received, for audit and replay safety."""
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    workspace_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    provider: Mapped[str] = mapped_column(String(24), default="paystack")
    reference: Mapped[str] = mapped_column(String(120), index=True, default="")
    plan: Mapped[str] = mapped_column(String(24), default="pro")
    months: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[int] = mapped_column(Integer, default=0)  # minor units (kobo/cents)
    currency: Mapped[str] = mapped_column(String(8), default="NGN")
    status: Mapped[str] = mapped_column(String(24), default="pending")  # pending|paid|failed|abandoned
    raw_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentSession(Base):
    """A scoped runtime session for one end-user of a workspace.

    This is the Composio-style primitive: your agent gets a session bound to a
    person, a subset of apps and a run budget, so a support bot or a per-customer
    automation cannot act outside its lane.
    """
    __tablename__ = "agent_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    entity_id: Mapped[str] = mapped_column(String(160), default="default")
    label: Mapped[str] = mapped_column(String(160), default="")
    allowed_apps: Mapped[str] = mapped_column(Text, default="")  # csv; empty means every app the plan allows
    allowed_tiers: Mapped[str] = mapped_column(String(40), default="read")  # read|read,write|read,write,destructive
    run_limit: Mapped[int] = mapped_column(Integer, default=0)  # 0 = use the plan's monthly limit
    runs_used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CustomTool(Base):
    """A user-defined HTTP tool: bring an internal API or a service we do not list.

    It behaves exactly like a catalog action: same quota, same approval gate on
    writes, same run log. Only the request shape is yours.
    """
    __tablename__ = "custom_tools"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_custom_tool"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    slug: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(String(8), default="GET")
    url: Mapped[str] = mapped_column(String(600), default="")
    headers_json: Mapped[str] = mapped_column(Text, default="{}")
    body_template: Mapped[str] = mapped_column(Text, default="")
    secret_enc: Mapped[str] = mapped_column(Text, default="")
    auth_style: Mapped[str] = mapped_column(String(24), default="bearer")  # bearer|header|query|none
    auth_name: Mapped[str] = mapped_column(String(80), default="Authorization")
    tier: Mapped[str] = mapped_column(String(16), default="read")
    params_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssistantGap(Base):
    """A question Tony could not answer. The weekly fix list starts here."""
    __tablename__ = "assistant_gaps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    question: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AppRating(Base):
    """Community signal on an integration, per workspace, one row each."""
    __tablename__ = "app_ratings"
    __table_args__ = (UniqueConstraint("workspace_id", "app_slug", name="uq_app_rating"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    app_slug: Mapped[str] = mapped_column(String(80), index=True)
    stars: Mapped[int] = mapped_column(Integer, default=5)
    review: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AppVersion(Base):
    """Changelog for an integration, so upgrading is a decision not a surprise."""
    __tablename__ = "app_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    app_slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(24), default="1.0.0")
    notes: Mapped[str] = mapped_column(Text, default="")
    breaking: Mapped[bool] = mapped_column(Boolean, default=False)
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SecurityReview(Base):
    """Public verdict: how an integration handles credentials and writes."""
    __tablename__ = "security_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    app_slug: Mapped[str] = mapped_column(String(80), index=True)
    verdict: Mapped[str] = mapped_column(String(24), default="pass")  # pass|review|fail
    encryption: Mapped[str] = mapped_column(String(40), default="AES-256-GCM at rest")
    scopes: Mapped[str] = mapped_column(Text, default="")
    findings: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RevenueShare(Base):
    """Builder earnings: a share of the runs a published integration generated."""
    __tablename__ = "revenue_share"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    app_slug: Mapped[str] = mapped_column(String(80), default="")
    period: Mapped[str] = mapped_column(String(7), default="")  # YYYY-MM
    runs: Mapped[int] = mapped_column(Integer, default=0)
    amount_ngn: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="accruing")  # accruing|payable|paid
    payout_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentMemory(Base):
    """Per-entity key/value store so an agent can keep state between calls."""
    __tablename__ = "agent_memory"
    __table_args__ = (Index("ix_memory_lookup", "workspace_id", "entity_id", "key", unique=True),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(160), index=True, default="default")
    key: Mapped[str] = mapped_column(String(200), index=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
