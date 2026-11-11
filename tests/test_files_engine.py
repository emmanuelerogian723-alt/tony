"""Universal file engine: handles, validation, isolation, signatures."""
import base64

import pytest

from tony import files as fe


def test_upload_returns_handle_and_metadata(ws):
    row = fe.store_bytes(workspace_id=ws, data=b"hello world", filename="note.txt",
                         mime="text/plain")
    assert row["id"].startswith("file_")
    assert row["size"] == 11 and row["status"] == "ready" and row["kind"] == "document"
    assert row["sha256"]


def test_presigned_flow_needs_size_and_finishes(ws):
    rec = fe.create_upload(workspace_id=ws, filename="clip.mp4", mime="video/mp4", size=1024)
    assert rec["status"] == "pending"
    assert rec["upload"]["method"] == "PUT"
    done = fe.write_content(rec["id"], b"x" * 1024, ws)
    assert done["status"] == "ready" and done["size"] == 1024


def test_rejects_empty_and_oversize(ws):
    with pytest.raises(fe.FileEngineError):
        fe.store_bytes(workspace_id=ws, data=b"", filename="a.txt", mime="text/plain")
    with pytest.raises(fe.FileEngineError):
        fe.create_upload(workspace_id=ws, filename="big.bin", mime="application/octet-stream",
                         size=fe.DEFAULT_MAX_BYTES + 1)


def test_mime_allowlist(ws):
    with pytest.raises(fe.FileEngineError):
        fe.store_bytes(workspace_id=ws, data=b"x", filename="a.exe", mime="application/pdf",
                       allow=["video/mp4"])


def test_tenant_isolation(ws):
    row = fe.store_bytes(workspace_id=ws, data=b"secret", filename="s.txt", mime="text/plain")
    with pytest.raises(fe.FileEngineError):
        fe.get(row["id"], "other-workspace")


def test_signed_url_roundtrip(ws):
    row = fe.store_bytes(workspace_id=ws, data=b"abc", filename="a.txt", mime="text/plain")
    link = fe.signed_url(row["id"], ws, 300)
    sig = link["url"].split("sig=")[1].split("&")[0]
    exp = link["url"].split("exp=")[1]
    assert fe.verify_signed(row["id"], sig, exp)
    assert not fe.verify_signed(row["id"], "bad", exp)


def test_kind_detection_and_dedupe(ws):
    a = fe.store_bytes(workspace_id=ws, data=b"same", filename="x.png", mime="image/png")
    b = fe.store_bytes(workspace_id=ws, data=b"same", filename="y.png", mime="image/png")
    assert a["kind"] == "image" and a["id"] == b["id"]


def test_delete_removes_and_404s(ws):
    row = fe.store_bytes(workspace_id=ws, data=b"bye", filename="b.txt", mime="text/plain")
    assert fe.delete(row["id"], ws)
    with pytest.raises(fe.FileEngineError):
        fe.get(row["id"], ws)
