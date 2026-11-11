"""The proxy can take any verb; the manifest default must not win.

Before this fix build_request() computed the override and then returned
action.method anyway, so `{"path": "/gists", "method": "POST"}` was sent as a
GET: it wrote nothing and still reported success.
"""
import pytest

from tony.catalog import catalog
from tony.executor import build_request, validate_args


def _build(method, body=None):
    spec, act = catalog.find_action("proxy.request")
    args = {"path": "/v1/things", "method": method}
    if body is not None:
        args["body"] = body
    creds = {"base_url": "https://api.example.com", "api_key": "k"}
    return build_request(spec, act, validate_args(act, args), creds)


@pytest.mark.parametrize("verb", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_verb_is_honoured(verb):
    url, method, headers, query, payload = _build(verb, {"a": 1})
    assert method == verb
    assert url == "https://api.example.com/v1/things"


def test_write_verbs_carry_the_body():
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        _, method, _, _, payload = _build(verb, {"name": "x"})
        assert payload == {"name": "x"}, verb


def test_read_verbs_never_send_a_body():
    _, method, _, _, payload = _build("GET", {"ignored": True})
    assert method == "GET"
    assert payload is None


def test_a_bad_verb_is_refused_clearly():
    """Validation wins over guessing: "post" is rejected, not silently run."""
    from tony.executor import ExecutionError

    with pytest.raises(ExecutionError) as err:
        _build("post", {"a": 1})
    assert "method" in str(err.value)
