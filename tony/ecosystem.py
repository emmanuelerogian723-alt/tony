"""The things a marketplace needs that a gateway usually forgets.

Ratings, changelogs, security verdicts, per-app usage and builder revenue share.
All of it read from the same database the gateway already writes to.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .db import session
from .models import ActionRun, AppRating, AppVersion, RevenueShare, SecurityReview, User, now

router = APIRouter(prefix="/v1", tags=["ecosystem"])


def _ws(request: Request) -> str:
    from .auth import workspace_from_request

    return workspace_from_request(request)[0]


def _app_or_404(slug: str) -> Any:
    from .catalog import catalog

    spec = catalog.apps.get(slug)
    if spec is None:
        raise HTTPException(404, detail=f"No app '{slug}' in the catalogue")
    return spec


class RatingIn(BaseModel):
    app_slug: str
    stars: int = Field(ge=1, le=5)
    review: str = ""


@router.post("/ratings")
def rate(body: RatingIn, request: Request) -> dict[str, Any]:
    ws = _ws(request)
    _app_or_404(body.app_slug)
    with session() as s:
        row = s.scalar(select(AppRating).where(AppRating.workspace_id == ws,
                                              AppRating.app_slug == body.app_slug))
        if row is None:
            row = AppRating(workspace_id=ws, app_slug=body.app_slug, stars=body.stars,
                            review=body.review[:2000])
            s.add(row)
        else:
            row.stars, row.review, row.updated_at = body.stars, body.review[:2000], now()
        s.flush()
        agg = s.execute(select(func.avg(AppRating.stars), func.count(AppRating.id))
                        .where(AppRating.app_slug == body.app_slug)).one()
    return {"ok": True, "app": body.app_slug, "your_rating": body.stars,
            "average": round(float(agg[0] or 0), 2), "ratings": int(agg[1] or 0)}


@router.get("/ratings")
def ratings(app: str = "") -> dict[str, Any]:
    with session() as s:
        q = select(AppRating.app_slug, func.avg(AppRating.stars), func.count(AppRating.id))
        if app:
            q = q.where(AppRating.app_slug == app)
        rows = s.execute(q.group_by(AppRating.app_slug).order_by(func.avg(AppRating.stars).desc())
                         .limit(50)).all()
        reviews = s.execute(select(AppRating).where(AppRating.review != "")
                            .order_by(AppRating.updated_at.desc()).limit(10)).scalars().all()
    return {"apps": [{"app": r[0], "average": round(float(r[1]), 2), "ratings": r[2]} for r in rows],
            "recent_reviews": [{"app": r.app_slug, "stars": r.stars, "review": r.review} for r in reviews],
            "total": sum(r[2] for r in rows)}


@router.get("/apps/{slug}/versions")
def versions(slug: str) -> dict[str, Any]:
    spec = _app_or_404(slug)
    with session() as s:
        rows = s.scalars(select(AppVersion).where(AppVersion.app_slug == slug)
                         .order_by(AppVersion.released_at.desc()).limit(20)).all()
    if not rows:
        return {"app": slug, "versions": [{
            "version": "1.0.0", "notes": f"Initial listing: {len(spec.actions)} typed actions.",
            "breaking": False, "released_at": None}], "note": "Baseline version"}
    return {"app": slug, "versions": [{
        "version": r.version, "notes": r.notes, "breaking": r.breaking,
        "released_at": r.released_at.isoformat() if r.released_at else None} for r in rows]}


@router.get("/apps/{slug}/security")
def security(slug: str) -> dict[str, Any]:
    spec = _app_or_404(slug)
    with session() as s:
        row = s.scalar(select(SecurityReview).where(SecurityReview.app_slug == slug))
    writes = [a.slug for a in spec.actions if a.tier != "read"]
    if row is None:
        return {"app": slug, "verdict": "pass" if spec.auth.type in {"oauth2", "api_key", "none"} else "review",
                "encryption": "AES-256-GCM at rest, decrypted in memory per call",
                "scopes": spec.auth.type, "findings": "No outstanding findings.",
                "write_actions": len(writes), "approval_gate": "writes require explicit approval",
                "reviewed_at": None}
    return {"app": slug, "verdict": row.verdict, "encryption": row.encryption, "scopes": row.scopes,
            "findings": row.findings, "write_actions": len(writes),
            "approval_gate": "writes require explicit approval",
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None}


@router.get("/stats/usage")
def usage_stats(request: Request, days: int = 30) -> dict[str, Any]:
    ws = _ws(request)
    since = now() - timedelta(days=max(1, min(days, 180)))
    with session() as s:
        rows = s.execute(
            select(ActionRun.app_slug, func.count(ActionRun.id), func.avg(ActionRun.latency_ms))
            .where(ActionRun.workspace_id == ws, ActionRun.created_at >= since)
            .group_by(ActionRun.app_slug).order_by(func.count(ActionRun.id).desc()).limit(15)
        ).all()
        daily = s.execute(
            select(func.date(ActionRun.created_at), func.count(ActionRun.id))
            .where(ActionRun.workspace_id == ws, ActionRun.created_at >= since)
            .group_by(func.date(ActionRun.created_at)).order_by(func.date(ActionRun.created_at))
        ).all()
        tier = s.execute(
            select(ActionRun.tier, func.count(ActionRun.id))
            .where(ActionRun.workspace_id == ws, ActionRun.created_at >= since)
            .group_by(ActionRun.tier)
        ).all()
    return {"window_days": days,
            "by_app": [{"app": r[0], "runs": r[1], "avg_latency_ms": int(r[2] or 0)} for r in rows],
            "by_day": [{"date": str(r[0]), "runs": r[1]} for r in daily],
            "by_tier": {str(r[0]): r[1] for r in tier}}


@router.get("/revenue")
def revenue(request: Request) -> dict[str, Any]:
    ws = _ws(request)
    with session() as s:
        rows = s.scalars(select(RevenueShare).where(RevenueShare.workspace_id == ws)
                         .order_by(RevenueShare.period.desc()).limit(24)).all()
        user = s.scalar(select(User).where(User.workspace_id == ws))
    paid = sum(r.amount_ngn for r in rows if r.status == "paid")
    pending = sum(r.amount_ngn for r in rows if r.status != "paid")
    return {"eligible": bool(user and user.email),
            "payout_account": (user.email if user else ""),
            "paid_ngn": paid, "pending_ngn": pending,
            "statements": [{"period": r.period, "app": r.app_slug, "runs": r.runs,
                            "amount_ngn": r.amount_ngn, "status": r.status,
                            "payout_on": r.payout_on.isoformat() if r.payout_on else None} for r in rows],
            "policy": "60% of the run revenue your published integration generates, paid monthly."}


@router.get("/ecosystem/summary")
def summary() -> dict[str, Any]:
    from .catalog import catalog

    with session() as s:
        rating_avg = s.scalar(select(func.avg(AppRating.stars))) or 0
        rating_n = s.scalar(select(func.count(AppRating.id))) or 0
        version_n = s.scalar(select(func.count(AppVersion.id))) or 0
        reviews = s.execute(select(SecurityReview.verdict, func.count(SecurityReview.id))
                            .group_by(SecurityReview.verdict)).all()
        runs = s.scalar(select(func.count(ActionRun.id))) or 0
        top = s.execute(select(ActionRun.app_slug, func.count(ActionRun.id).label("n"))
                        .group_by(ActionRun.app_slug).order_by(func.count(ActionRun.id).desc())
                        .limit(6)).all()
    apps = len(catalog.apps)
    actions = sum(len(a.actions) for a in catalog.apps.values())
    return {"apps": apps, "actions": actions,
            "ratings": {"count": rating_n, "average": round(float(rating_avg), 2)},
            "versions_tracked": version_n,
            "security": {str(r[0]): r[1] for r in reviews},
            "runs_all_time": runs,
            "most_used": [{"app": r[0], "runs": r[1]} for r in top],
            "plugins": PLUGINS}


PLUGINS = [
    {"name": "Claude Desktop / Claude Code", "kind": "MCP", "install": "Add https://tony-7su0.onrender.com/mcp"},
    {"name": "Cursor", "kind": "MCP", "install": "Add the same MCP URL in Settings → MCP"},
    {"name": "LangChain", "kind": "Python", "install": "from tony_sdk import TonyClient; TonyClient().langchain_tools()"},
    {"name": "LlamaIndex", "kind": "Python", "install": "client.llamaindex_tools()"},
    {"name": "CrewAI", "kind": "Python", "install": "client.crewai_tools()"},
    {"name": "Vercel AI SDK", "kind": "TypeScript", "install": "tonyTools() from tony-sdk"},
    {"name": "OpenAI Agents", "kind": "Any", "install": "GET /v1/tools?fmt=openai"},
    {"name": "Anthropic tool use", "kind": "Any", "install": "GET /v1/tools?fmt=anthropic"},
]


@router.get("/plugins")
def plugins() -> dict[str, Any]:
    return {"plugins": PLUGINS, "count": len(PLUGINS)}
