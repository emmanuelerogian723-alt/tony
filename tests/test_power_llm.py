

def test_groq_ladder_is_ordered_and_live_first(monkeypatch):
    """The first attempt must be a model Groq actually serves on a free tier."""
    from tony import power

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.delenv("TONY_GROQ_MODELS", raising=False)
    monkeypatch.setenv("TONY_AGENT_MODEL", "openai/gpt-oss-120b")
    chain = power._llm_targets()
    models = [m for url, m, _ in chain if "groq" in url]
    assert models[0] == "openai/gpt-oss-20b", models
    assert "qwen/qwen3.8-27b" in models


def test_retry_after_is_read_from_header_and_message():
    from tony import power

    class Resp:
        def __init__(self, headers, body):
            self.headers = headers
            self._body = body

        def json(self):
            return self._body

    assert power._retry_after_seconds(Resp({"retry-after": "2"}, {})) == 2.0
    body = {"error": {"message": "Rate limit reached ... Please try again in 850ms."}}
    assert power._retry_after_seconds(Resp({}, body)) == 0.85
    assert power._retry_after_seconds(Resp({}, {"error": {"message": "nope"}})) is None
