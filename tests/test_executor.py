"""Request building, validation, auth injection and response shaping."""

import pytest

from tony.catalog import ActionSpec, AppSpec, AuthSpec
from tony.executor import (
    ExecutionError,
    assert_safe_url,
    build_request,
    dig,
    shape_response,
    validate_args,
)


def make_app(auth=None, actions=None, headers=None):
    return AppSpec(
        slug="demo", name="Demo", category="Test", description="", docs="", logo="",
        auth=AuthSpec(**(auth or {})), actions=actions or [], default_headers=headers or {},
    )


def make_action(**kw):
    base = dict(slug="do", name="Do", description="", method="GET", url="https://api.test/x")
    base.update(kw)
    return ActionSpec(**base)


def test_query_params_for_get():
    app = make_app()
    act = make_action(params={"a": {"type": "string"}, "n": {"type": "integer"}})
    args = validate_args(act, {"a": "hello", "n": "3"})
    url, method, headers, query, body = build_request(app, act, args, None)
    assert query == {"a": "hello", "n": 3}
    assert body is None


def test_body_params_for_post():
    app = make_app()
    act = make_action(method="POST", params={"title": {"type": "string"}})
    args = validate_args(act, {"title": "hi"})
    url, method, headers, query, body = build_request(app, act, args, None)
    assert method == "POST"
    assert body == {"title": "hi"}
    assert query == {}


def test_path_placeholder_is_encoded():
    app = make_app()
    act = make_action(url="https://api.test/items/{name}", params={"name": {"type": "string", "in": "path"}})
    args = validate_args(act, {"name": "a b/c"})
    url, *_ = build_request(app, act, args, None)
    assert url == "https://api.test/items/a%20b%2Fc"


def test_absolute_url_param_is_not_encoded():
    app = make_app()
    act = make_action(url="{url}", params={"url": {"type": "string", "in": "path"}})
    args = validate_args(act, {"url": "https://example.com/a?b=1"})
    url, *_ = build_request(app, act, args, None)
    assert url == "https://example.com/a?b=1"


def test_unknown_argument_rejected():
    act = make_action(params={"a": {"type": "string"}})
    with pytest.raises(ExecutionError, match="Unknown argument"):
        validate_args(act, {"b": "x"})


def test_required_argument_enforced():
    act = make_action(params={"a": {"type": "string"}}, required=["a"])
    with pytest.raises(ExecutionError, match="Missing required"):
        validate_args(act, {})


def test_enum_enforced():
    act = make_action(params={"state": {"type": "string", "enum": ["open", "closed"]}})
    with pytest.raises(ExecutionError, match="must be one of"):
        validate_args(act, {"state": "nope"})


def test_bearer_auth_injected():
    app = make_app(auth={"type": "bearer"})
    act = make_action()
    url, method, headers, query, body = build_request(app, act, {}, {"access_token": "tok123"})
    assert headers["Authorization"] == "Bearer tok123"


def test_api_key_in_query():
    app = make_app(auth={"type": "api_key", "query_name": "apiKey", "header_name": ""})
    act = make_action()
    _, _, headers, query, _ = build_request(app, act, {}, {"api_key": "k1"})
    assert query["apiKey"] == "k1"
    assert "Authorization" not in headers


def test_api_key_in_header_with_template():
    app = make_app(auth={"type": "api_key", "header_name": "X-Token", "value_template": "{token}"})
    act = make_action()
    _, _, headers, _, _ = build_request(app, act, {}, {"api_key": "k2"})
    assert headers["X-Token"] == "k2"


def test_twilio_style_credentials_fill_url():
    app = make_app(auth={"type": "basic"})
    act = make_action(url="https://api.test/Accounts/{account_sid}/Messages.json",
                      params={"account_sid": {"type": "string", "in": "path"}})
    creds = {"account_sid": "AC123", "username": "AC123", "password": "secret"}
    url, _, headers, _, _ = build_request(app, act, {"account_sid": "AC123"}, creds)
    assert url.endswith("/Accounts/AC123/Messages.json")
    assert headers["Authorization"].startswith("Basic ")


def test_dig_dot_path():
    data = {"a": {"b": [{"c": 1}]}}
    assert dig(data, "a.b.0.c") == 1
    assert dig(data, "$.a.b") == [{"c": 1}]
    assert dig(data, "missing") is None


def test_shape_response_path_and_cap():
    act = make_action(response={"path": "items", "max_items": 2})
    data, meta = shape_response(act, {"items": [1, 2, 3, 4]})
    assert data == [1, 2]
    assert meta["truncated"] is True


def test_shape_response_budget_keeps_structure():
    act = make_action(response={"max_chars": 400})
    payload = {"a": "x" * 2000, "b": 2, "c": [1, 2, 3]}
    data, meta = shape_response(act, payload)
    assert isinstance(data, dict)
    assert meta["truncated"] is True


def test_html_text_transform():
    act = make_action(response={"transform": "html_text"})
    html = "<html><head><title>T</title></head><body><script>x()</script><p>Hello  world</p></body></html>"
    data, _ = shape_response(act, {"text": html})
    assert data["title"] == "T"
    assert "Hello world" in data["text"]
    assert "x()" not in data["text"]


def test_rss_transform():
    act = make_action(response={"transform": "rss"})
    xml = "<rss><channel><item><title>One</title><link>https://a</link></item></channel></rss>"
    data, _ = shape_response(act, {"text": xml})
    assert data["items"][0]["title"] == "One"


def test_ssrf_guard_blocks_localhost():
    with pytest.raises(ExecutionError, match="private network"):
        assert_safe_url("http://127.0.0.1:8000/admin")


def test_ssrf_guard_blocks_metadata():
    with pytest.raises(ExecutionError):
        assert_safe_url("http://169.254.169.254/latest/meta-data/")
