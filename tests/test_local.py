"""The local-model provider, tested against a real HTTP server that speaks the Ollama/OpenAI protocol.

The server is a tiny stand-in (no model), so this proves the wire format, error handling and the
full interview flow, not the quality of any particular model.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import create_app
from app.config import Settings
from app.errors import LLMError
from app.llm.factory import build_provider
from app.llm.local import LocalProvider
from app.llm.offline import OfflineProvider
from app.models import Context, Question
from .conftest import make_settings, start

CTX = Context(role="Backend Developer", level="junior", total=2, index=0, seed=1, resume_text="")

# One reply that satisfies every parser (question, review and report).
REPLY = {
    "question": "How would you design a rate limiter?", "topic": "System design",
    "scores": {"relevance": 8, "depth": 6, "clarity": 7, "structure": 7, "grammar": 9},
    "feedback": "Good start. Add numbers.", "strengths": ["Clear"], "improvements": ["Add a metric"],
    "sample_answer": "A stronger answer.", "grammar_issues": [],
    "next_question": {"question": "What is an index?", "topic": "Databases"},
    "summary": "Solid.", "weaknesses": ["Depth"], "practice_plan": [{"focus": "SQL", "action": "Do 5 joins"}],
}


class Fake:
    """Holds what the fake server should do and what it received."""
    def __init__(self):
        self.mode = "ok"      # ok | bad_json | missing_model | error | slow
        self.requests = []


@pytest.fixture
def server():
    fake = Fake()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            fake.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
            if fake.mode == "missing_model":
                return self._send(404, {"error": "model not found"})
            if fake.mode == "error":
                return self._send(500, {"error": "boom"})
            content = "I think the answer is..." if fake.mode == "bad_json" else json.dumps(REPLY)
            self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}]})

        def _send(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    fake.url = f"http://127.0.0.1:{httpd.server_port}/v1"
    yield fake
    httpd.shutdown()


def test_review_over_real_http(server):
    provider = LocalProvider(server.url, "gemma2:2b", timeout=5)
    evaluation, nxt = provider.review_answer(CTX, Question("What is an index?", "DB"), "It speeds up reads.", want_next=True)
    assert evaluation.scores["grammar"] == 9 and nxt.text == "What is an index?"
    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions"
    assert sent["body"]["model"] == "gemma2:2b" and sent["body"]["stream"] is False
    assert "Authorization" not in sent["headers"]  # local servers need no key
    assert "<candidate_answer>\nIt speeds up reads.\n</candidate_answer>" in sent["body"]["messages"][1]["content"]


def test_bad_json_from_a_small_model_is_retried_then_reported(server):
    server.mode = "bad_json"
    with pytest.raises(LLMError):
        LocalProvider(server.url, "m", timeout=5).first_question(CTX)
    assert len(server.requests) == 2  # one retry


def test_missing_model_and_server_errors_have_clear_messages(server):
    server.mode = "missing_model"
    with pytest.raises(LLMError, match="does not have the model"):
        LocalProvider(server.url, "nope", timeout=5)._complete("s", "u")
    server.mode = "error"
    with pytest.raises(LLMError, match="HTTP 500"):
        LocalProvider(server.url, "m", timeout=5)._complete("s", "u")


def test_server_not_running_says_so():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]          # a port nothing listens on
    with pytest.raises(LLMError, match="Is Ollama"):
        LocalProvider(f"http://127.0.0.1:{port}/v1", "m", timeout=2)._complete("s", "u")


def test_full_interview_with_the_local_provider(server):
    provider = LocalProvider(server.url, "gemma2:2b", timeout=5)
    client = create_app(make_settings(llm_provider="local"), provider).test_client()
    state = start(client, total=3)
    sid = state["id"]
    for _ in range(3):
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "I would use a token bucket stored in Redis."})
        assert resp.status_code == 200, resp.get_json()
    body = client.get(f"/api/sessions/{sid}/report").get_json()
    report = body.get("report", body)
    assert report["overall"] > 0 and report["practice_plan"] and report["summary_degraded"] is False


def test_backup_takes_over_when_the_free_api_quota_is_used_up(server, monkeypatch):
    import requests
    from app.llm.fallback import FallbackProvider
    from app.llm.groq import GroqProvider

    class Quota:  # the hosted API answers 429 every time
        status_code, text = 429, "quota"

    hosted_calls = []
    real_post = requests.post

    def post(url, **kw):
        if "groq.com" in url:
            hosted_calls.append(url)
            return Quota()
        return real_post(url, **kw)

    monkeypatch.setattr(requests, "post", post)
    now = [0.0]
    provider = FallbackProvider(GroqProvider("k", "m"), LocalProvider(server.url, "gemma2:2b", timeout=5), clock=lambda: now[0])
    assert provider.first_question(CTX).text                       # served by the local model
    assert len(hosted_calls) == 1 and len(server.requests) == 1
    provider.final_report(CTX)                                     # within the cool-down: hosted is not retried
    assert len(hosted_calls) == 1 and len(server.requests) == 2
    now[0] = 61                                                    # cool-down over: hosted is tried again
    provider.first_question(CTX)
    assert len(hosted_calls) == 2


def test_backup_is_not_used_for_a_healthy_primary(server):
    from app.llm.fallback import FallbackProvider
    primary = LocalProvider(server.url, "primary", timeout=5)
    provider = FallbackProvider(primary, LocalProvider("http://127.0.0.1:9/v1", "backup", timeout=2))
    assert provider.first_question(CTX).text
    assert [r["body"]["model"] for r in server.requests] == ["primary"]


def test_factory_wires_the_backup():
    from app.llm.fallback import FallbackProvider
    p = build_provider(Settings(groq_api_key="k", local_llm_model="gemma2:2b"))
    assert isinstance(p, FallbackProvider) and "backup Local (gemma2:2b)" in p.name
    assert isinstance(build_provider(Settings(groq_api_key="k")), type(build_provider(Settings(groq_api_key="k"))))


def test_factory_and_validation():
    s = Settings(llm_provider="local", local_llm_model="llama3.2:3b")
    assert isinstance(build_provider(s), LocalProvider) and build_provider(s).name == "Local (llama3.2:3b)"
    assert isinstance(build_provider(Settings(local_llm_model="gemma2:2b")), LocalProvider)  # auto, chosen on purpose
    assert isinstance(build_provider(Settings()), OfflineProvider)                            # nothing is probed
    with pytest.raises(Exception):
        build_provider(Settings(llm_provider="local"))                                         # no model named
    with pytest.raises(Exception):
        build_provider(Settings(llm_provider="local", local_llm_model="m", local_llm_url="file:///etc/passwd"))
