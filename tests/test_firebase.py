from tony import firebase


def test_project_id_derivation(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "ominiassist-ai")
    assert firebase.project_id() == "ominiassist-ai"
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "ominiassist-ai.firebaseapp.com")
    monkeypatch.delenv("FIREBASE_PROJECT_ID")
    assert firebase.project_id() == "ominiassist-ai"


def test_verify_rejects_empty():
    try:
        firebase.verify("")
    except ValueError as exc:
        assert "Missing" in str(exc)
    else:
        raise AssertionError("expected a rejection")


def test_status_route(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "x")
    d = client.get("/v1/account/firebase/status").json()
    assert d["enabled"] is True and d["project"]


def test_firebase_login_rejects_bad_token(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "x")
    r = client.post("/v1/account/firebase", json={"id_token": "not-a-token"})
    assert r.status_code == 401
