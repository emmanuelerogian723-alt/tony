"""Typed connectors: real, ergonomic actions for the workflows people ask for.

The declarative YAML actions are great for breadth, but a raw API call is not an
integration. `gmail.send_message` demanding a base64url MIME blob is exactly
the Composio-style friction we are removing.

Each connector here takes friendly arguments, builds the real provider payload
(including MIME emails and file handles), and returns the exact request plan the
executor sends. Tests exercise the builders without any network access.
"""
from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

from . import files as file_engine

# app slug -> {action slug: builder}
CONNECTORS: dict[str, dict[str, Any]] = {}


def connector(app: str):
    def wrap(fn):
        CONNECTORS.setdefault(app, {})[fn.__name__] = fn
        return fn
    return wrap


def has(app: str, action: str) -> bool:
    return action in CONNECTORS.get(app, {})


def build(app: str, action: str, args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    fn = CONNECTORS.get(app, {}).get(action)
    if fn is None:
        raise KeyError(f"No typed connector for {app}.{action}")
    return fn(args, workspace_id=workspace_id)


def _as_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if str(x).strip()]
    return [p.strip() for p in str(v).replace(";", ",").split(",") if p.strip()]


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


# ── Gmail ─────────────────────────────────────────────────────────────────
@connector("gmail")
def send_email(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    """to / subject / body (+ cc, bcc, html, attachments) -> one real RFC822 send."""
    to = _as_list(args.get("to"))
    if not to:
        raise ValueError("send_email requires 'to'")
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    cc = _as_list(args.get("cc"))
    bcc = _as_list(args.get("bcc"))
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = str(args.get("subject") or "(no subject)")
    body = str(args.get("body") or args.get("text") or "")
    if args.get("html"):
        msg.set_content(body or "This message contains HTML.")
        msg.add_alternative(str(args["html"]), subtype="html")
    else:
        msg.set_content(body)

    for handle in _as_list(args.get("attachments") or args.get("files")):
        f = file_engine.resolve(handle, workspace_id)
        data = f["bytes"] or file_engine.read_bytes(handle, workspace_id)
        maintype, _, subtype = (f["mime"] or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype or "application", subtype=subtype or "octet-stream",
                           filename=f["filename"])

    raw = _b64url(msg.as_bytes())
    return {
        "method": "POST",
        "url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        "body": {"raw": raw},
        "summary": f"Email to {', '.join(to)}",
        "idempotent": False,
    }


@connector("gmail")
def reply_email(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    thread_id = str(args.get("thread_id") or "")
    if not thread_id:
        raise ValueError("reply_email requires 'thread_id'")
    plan = send_email(args, workspace_id=workspace_id)
    plan["body"]["threadId"] = thread_id
    plan["summary"] = f"Reply in thread {thread_id}"
    return plan


# ── YouTube ───────────────────────────────────────────────────────────────
@connector("youtube")
def upload_video(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    """A file handle plus a title is all an agent should need."""
    handle = str(args.get("file") or args.get("video") or "")
    if not handle:
        raise ValueError("upload_video requires a 'file' handle")
    f = file_engine.resolve(handle, workspace_id)
    if f["kind"] not in {"video", "file"}:
        raise ValueError(f"That file is {f['kind']}, not a video")
    meta = {
        "snippet": {
            "title": str(args.get("title") or f["filename"])[:100],
            "description": str(args.get("description") or "")[:5000],
            "tags": _as_list(args.get("tags"))[:30],
            "categoryId": str(args.get("category_id") or "22"),
        },
        "status": {
            "privacyStatus": str(args.get("privacy") or "private"),
            "selfDeclaredMadeForKids": bool(args.get("made_for_kids", False)),
        },
    }
    return {
        "method": "POST",
        "url": "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        "body": meta,
        "file": {"handle": f["id"], "path": f["path"], "mime": f["mime"], "size": f["size"]},
        "summary": f"Upload video '{meta['snippet']['title']}' ({f['size']} bytes)",
        "idempotent": False,
        "resumable": True,
    }


# ── Slack ─────────────────────────────────────────────────────────────────
@connector("slack")
def post_message(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    channel = str(args.get("channel") or "")
    text = str(args.get("text") or args.get("message") or "")
    if not channel or not text:
        raise ValueError("post_message requires 'channel' and 'text'")
    body: dict[str, Any] = {"channel": channel, "text": text}
    if args.get("thread_ts"):
        body["thread_ts"] = str(args["thread_ts"])
    handles = _as_list(args.get("files"))
    if handles:
        body["file_handles"] = [file_engine.resolve(h, workspace_id)["id"] for h in handles]
    return {"method": "POST", "url": "https://slack.com/api/chat.postMessage",
            "body": body, "summary": f"Slack message to {channel}", "idempotent": False}


@connector("slack")
def upload_file(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    handle = str(args.get("file") or "")
    if not handle:
        raise ValueError("upload_file requires a 'file' handle")
    f = file_engine.resolve(handle, workspace_id)
    return {
        "method": "GET",
        "url": "https://slack.com/api/files.getUploadURLExternal",
        "query": {"filename": f["filename"], "length": f["size"]},
        "file": {"handle": f["id"], "path": f["path"], "mime": f["mime"], "size": f["size"]},
        "summary": f"Request Slack upload slot for {f['filename']}",
        "idempotent": True,
    }


# ── GitHub ────────────────────────────────────────────────────────────────
@connector("github")
def create_issue(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    repo = str(args.get("repo") or "")
    title = str(args.get("title") or "")
    if not repo or not title:
        raise ValueError("create_issue requires 'repo' (owner/name) and 'title'")
    body: dict[str, Any] = {"title": title, "body": str(args.get("body") or "")}
    labels = _as_list(args.get("labels"))
    if labels:
        body["labels"] = labels
    assignees = _as_list(args.get("assignees"))
    if assignees:
        body["assignees"] = assignees
    return {"method": "POST", "url": f"https://api.github.com/repos/{repo}/issues",
            "body": body, "summary": f"Issue '{title}' in {repo}", "idempotent": False}


# ── LinkedIn / Facebook ───────────────────────────────────────────────────
@connector("linkedin")
def create_post(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    text = str(args.get("text") or args.get("content") or "")
    if not text:
        raise ValueError("create_post requires 'text'")
    author = str(args.get("author_urn") or "")
    if not author:
        raise ValueError("create_post requires 'author_urn' (urn:li:person:... or urn:li:organization:...)")
    body = {
        "author": author,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    return {"method": "POST", "url": "https://api.linkedin.com/v2/ugcPosts", "body": body,
            "summary": "LinkedIn post", "idempotent": False}


@connector("facebook")
def create_post(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    page = str(args.get("page_id") or "")
    text = str(args.get("text") or args.get("message") or "")
    if not page or not text:
        raise ValueError("create_post requires 'page_id' and 'text'")
    body: dict[str, Any] = {"message": text}
    handle = str(args.get("image") or "")
    if handle:
        f = file_engine.resolve(handle, workspace_id)
        body["file"] = {"handle": f["id"], "path": f["path"], "mime": f["mime"], "size": f["size"]}
        return {"method": "POST", "url": f"https://graph.facebook.com/v21.0/{page}/photos",
                "body": body, "summary": "Facebook photo post", "idempotent": False}
    return {"method": "POST", "url": f"https://graph.facebook.com/v21.0/{page}/feed",
            "body": body, "summary": "Facebook text post", "idempotent": False}


# ── Google Calendar ───────────────────────────────────────────────────────
@connector("googlecalendar")
def create_event(args: dict[str, Any], *, workspace_id: str | None = None) -> dict[str, Any]:
    start = str(args.get("start") or "")
    end = str(args.get("end") or "")
    if not start:
        raise ValueError("create_event requires 'start' (ISO 8601)")
    body: dict[str, Any] = {
        "summary": str(args.get("title") or "Untitled event"),
        "start": {"dateTime": start, "timeZone": str(args.get("timezone") or "UTC")},
        "end": {"dateTime": end or start, "timeZone": str(args.get("timezone") or "UTC")},
    }
    if args.get("description"):
        body["description"] = str(args["description"])
    attendees = _as_list(args.get("attendees"))
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    return {"method": "POST", "url": "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            "body": body, "summary": f"Calendar event '{body['summary']}'", "idempotent": False}


def describe() -> dict[str, Any]:
    return {app: sorted(actions) for app, actions in sorted(CONNECTORS.items())}
