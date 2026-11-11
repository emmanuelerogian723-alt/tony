"""Typed connectors build real provider payloads from friendly arguments."""
import base64

import pytest

from tony import connectors as cx
from tony import files as fe


def test_gmail_send_builds_real_mime(ws):
    plan = cx.build("gmail", "send_email", {
        "to": "customer@example.com", "subject": "Your order", "body": "Shipped today."},
        workspace_id=ws)
    assert plan["method"] == "POST" and "messages/send" in plan["url"]
    raw = plan["body"]["raw"]
    padded = raw + "=" * (-len(raw) % 4)
    decoded = base64.urlsafe_b64decode(padded).decode()
    assert "To: customer@example.com" in decoded
    assert "Subject: Your order" in decoded
    assert "Shipped today." in decoded


def test_gmail_attachments_use_file_handles(ws):
    f = fe.store_bytes(workspace_id=ws, data=b"%PDF-1.4 fake", filename="invoice.pdf",
                       mime="application/pdf")
    plan = cx.build("gmail", "send_email", {
        "to": "a@b.com", "subject": "Invoice", "body": "See attached",
        "attachments": [f["id"]]}, workspace_id=ws)
    raw = plan["body"]["raw"]
    decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode(errors="replace")
    assert "invoice.pdf" in decoded


def test_gmail_requires_recipient():
    with pytest.raises(ValueError):
        cx.build("gmail", "send_email", {"subject": "x"})


def test_youtube_upload_accepts_handle(ws):
    f = fe.store_bytes(workspace_id=ws, data=b"\x00" * 2048, filename="trip.mp4", mime="video/mp4")
    plan = cx.build("youtube", "upload_video", {"file": f["id"], "title": "My trip",
                                                "privacy": "public"}, workspace_id=ws)
    assert "uploadType=resumable" in plan["url"]
    assert plan["body"]["snippet"]["title"] == "My trip"
    assert plan["body"]["status"]["privacyStatus"] == "public"
    assert plan["file"]["size"] == 2048


def test_youtube_rejects_non_video(ws):
    f = fe.store_bytes(workspace_id=ws, data=b"text", filename="a.txt", mime="text/plain")
    with pytest.raises(ValueError):
        cx.build("youtube", "upload_video", {"file": f["id"]}, workspace_id=ws)


def test_slack_github_calendar_shapes():
    assert "chat.postMessage" in cx.build("slack", "post_message",
                                          {"channel": "#ops", "text": "hi"})["url"]
    issue = cx.build("github", "create_issue", {"repo": "o/r", "title": "Bug", "labels": ["p1"]})
    assert issue["body"]["labels"] == ["p1"]
    ev = cx.build("googlecalendar", "create_event",
                  {"title": "Standup", "start": "2026-01-01T09:00:00Z",
                   "end": "2026-01-01T09:15:00Z", "attendees": "a@b.com,b@c.com"})
    assert ev["body"]["attendees"] == [{"email": "a@b.com"}, {"email": "b@c.com"}]


def test_registry_lists_connectors():
    d = cx.describe()
    assert "gmail" in d and "send_email" in d["gmail"]
    assert "youtube" in d and "upload_video" in d["youtube"]
