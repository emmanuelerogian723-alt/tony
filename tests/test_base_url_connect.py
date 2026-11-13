"""Directory apps need a host: validation, storage and clear failures."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tony.api import normalise_base_url
from tony.catalog import catalog
from tony.main import app


def a_directory_slug() -> str:
    for spec in catalog.apps.values():
        if spec.tier == "directory":
            return spec.slug
    raise AssertionError("no directory apps in the registry")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TONY_DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        yield c


def test_normalise_adds_scheme_and_strips_slash():
    assert normalise_base_url("api.example.com/") == "https://api.example.com"
    assert normalise_base_url("https://api.example.com/v2/") == "https://api.example.com/v2"


@pytest.mark.parametrize("bad", ["", "ftp://api.example.com", "http://localhost:8080",
                                 "http://127.0.0.1", "https://10.0.0.4", "not a host"])
def test_normalise_rejects_bad_hosts(bad):
    with pytest.raises(Exception):
        normalise_base_url(bad)


def test_directory_app_advertises_base_url_requirement(client):
    slug = a_directory_slug()
    detail = client.get(f"/v1/apps/{slug}").json()
    assert detail["needs_base_url"] is True


def test_connect_directory_app_needs_base_url(client):
    slug = a_directory_slug()
    r = client.post(f"/v1/connections/{slug}/key", json={"values": {"api_key": "sk-test"}})
    assert r.status_code == 400
    assert "base url" in r.json()["detail"].lower()


def test_connect_directory_app_stores_host(client):
    slug = a_directory_slug()
    r = client.post(f"/v1/connections/{slug}/key",
                    json={"values": {"base_url": "https://api.example.com/v1/", "api_key": "sk-test"}})
    assert r.status_code == 200, r.text
    assert r.json()["connection"]["base_url"] == "https://api.example.com/v1"


def test_missing_host_gives_actionable_error(client):
    """A token saved without a host (legacy rows) must explain the fix, not fail opaquely."""
    from tony.db import session
    from tony.oauth import store_api_key

    slug = a_directory_slug()
    # The client's own private demo room: the demo is no longer one shared workspace.
    ws_id = client.get("/v1/demo/session").json()["workspace_id"]
    with session() as s:
        store_api_key(ws_id, "default", catalog.get(slug), {"api_key": "sk-test"}, "legacy")
    r = client.post("/v1/execute", json={"action": f"{slug}.request", "args": {"path": "/v1/me"},
                                         "approved": True})
    assert r.status_code == 200, r.text
    assert "base url" in str(r.json()).lower()
