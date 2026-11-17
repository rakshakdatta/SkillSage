import pytest

from app import create_app
from app.errors import LLMError
from app.llm.offline import OfflineProvider

from .conftest import make_pdf, make_settings, start


def test_health_roles_and_pages(client):
    assert client.get("/api/health").get_json() == {"status": "ok", "provider": "Offline practice mode", "is_ai": False}
    assert "Backend Developer" in client.get("/api/roles").get_json()["roles"]
    home = client.get("/")
    assert home.status_code == 200 and b"Offline practice mode" in home.data
    assert client.get("/interview/not-a-valid-id").status_code == 404


def test_security_headers(client):
    resp = client.get("/")
    assert "script-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/health").headers["Cache-Control"] == "no-store"


def test_full_interview_flow(client, provider):
    state = start(client, total=3)
    assert state["current_question"]["index"] == 1 and not state["finished"]
    sid = state["id"]

    for expected_done in (1, 2, 3):
        question = state["current_question"]["text"]
        ideal = provider._by_text[question]["ideal"]
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": ideal})
        assert resp.status_code == 200
        state = resp.get_json()
        assert state["answered"] == expected_done
        assert 1 <= state["evaluation"]["overall"] <= 10
        # the model answer should do well on its own question
        assert state["evaluation"]["overall"] >= 6

    assert state["finished"] and state["current_question"] is None
    report = client.get(f"/api/sessions/{sid}/report").get_json()["report"]
    assert 1 <= report["overall"] <= 10
    assert set(report["by_dimension"]) == {"relevance", "depth", "clarity", "structure", "grammar"}
    assert report["summary"] and report["practice_plan"]
    assert len(client.get(f"/api/sessions/{sid}").get_json()["history"]) == 3

    again = client.post(f"/api/sessions/{sid}/answer", json={"answer": "more"})
    assert again.status_code == 409


def test_session_can_be_resumed_by_id(client):
    sid = start(client)["id"]
    resumed = client.get(f"/api/sessions/{sid}").get_json()
    assert resumed["current_question"]["index"] == 1


@pytest.mark.parametrize("payload", [
    {"role": "", "level": "junior", "total": 5},
    {"role": "<script>alert(1)</script>", "level": "junior", "total": 5},
    {"role": "x" * 80, "level": "junior", "total": 5},
    {"role": "Backend Developer", "level": "wizard", "total": 5},
    {"role": "Backend Developer", "level": "junior", "total": 2},
    {"role": "Backend Developer", "level": "junior", "total": 99},
    {"role": "Backend Developer", "level": "junior", "total": "lots"},
])
def test_start_validation(client, payload):
    resp = client.post("/api/sessions", json=payload)
    assert resp.status_code == 400 and resp.get_json()["error"]


def test_bad_requests(client):
    assert client.post("/api/sessions", data="not json").status_code == 400
    sid = start(client)["id"]
    assert client.post(f"/api/sessions/{sid}/answer", json={"answer": "   "}).status_code == 400
    assert client.post(f"/api/sessions/{sid}/answer", json={"answer": "a" * 4001}).status_code == 413
    assert client.get("/api/sessions/0123456789abcdef").status_code == 404
    assert client.get(f"/api/sessions/{sid}/report").status_code == 409
    assert client.get("/api/does-not-exist").status_code == 404


def test_rate_limit():
    app = create_app(make_settings(rate_limit_per_minute=3), OfflineProvider())
    client = app.test_client()
    codes = [client.post("/api/sessions", json={"role": "QA Engineer", "total": 3}).status_code for _ in range(5)]
    assert codes[:3] == [201, 201, 201] and codes[3:] == [429, 429]


def test_report_survives_ai_summary_failure(settings):
    class FlakySummary(OfflineProvider):
        def final_report(self, ctx):
            raise LLMError("summary model down")

    client = create_app(settings, FlakySummary()).test_client()
    state = start(client, total=3)
    for _ in range(3):
        resp = client.post(f"/api/sessions/{state['id']}/answer", json={"answer": "I would explain it with an example."})
        state = resp.get_json()
    assert state["finished"]
    assert state["report"]["summary_degraded"] is True and state["report"]["summary"]


def test_ai_failure_on_a_question_does_not_corrupt_the_session(settings):
    class FailsOnce(OfflineProvider):
        calls = 0

        def review_answer(self, ctx, question, answer, want_next):
            FailsOnce.calls += 1
            if FailsOnce.calls == 1:
                raise LLMError("temporary failure")
            return super().review_answer(ctx, question, answer, want_next)

    client = create_app(settings, FailsOnce()).test_client()
    sid = start(client)["id"]
    assert client.post(f"/api/sessions/{sid}/answer", json={"answer": "first try"}).status_code == 502
    assert client.get(f"/api/sessions/{sid}").get_json()["answered"] == 0     # nothing was recorded
    assert client.post(f"/api/sessions/{sid}/answer", json={"answer": "second try"}).status_code == 200


def test_resume_upload_scrubs_contact_details(client):
    text = ("Jane Doe jane.doe@example.com +91 98765 43210 https://linkedin.com/in/jane\n"
            "Built a REST API in Spring Boot and a React dashboard for a campus startup.").encode()
    resp = client.post("/api/resume", data={"file": (__import__("io").BytesIO(text), "cv.txt")})
    assert resp.status_code == 200
    body = resp.get_json()["text"]
    assert "jane.doe@example.com" not in body and "98765" not in body and "linkedin.com" not in body
    assert "Spring Boot" in body


def test_resume_pdf_and_rejections(client):
    import io
    pdf = make_pdf("Backend developer with two years building Spring Boot services and REST APIs")
    ok = client.post("/api/resume", data={"file": (io.BytesIO(pdf), "cv.pdf")})
    assert ok.status_code == 200 and "Spring Boot" in ok.get_json()["text"]
    assert client.post("/api/resume", data={"file": (io.BytesIO(b"MZ not a pdf"), "cv.pdf")}).status_code == 400
    assert client.post("/api/resume", data={"file": (io.BytesIO(b"x"), "cv.exe")}).status_code == 400
    assert client.post("/api/resume", data={}).status_code == 400


def test_resume_text_is_scrubbed_when_starting_a_session(client, app):
    resp = client.post("/api/sessions", json={"role": "QA Engineer", "total": 3,
                                                "resume_text": "Reach me at me@site.com or 9876543210."})
    sid = resp.get_json()["id"]
    stored = app.extensions["skillsage"]["service"].store.get(sid).resume_text
    assert "me@site.com" not in stored and "9876543210" not in stored

def test_every_page_renders_and_obeys_the_content_security_policy(client):
    import re
    from .conftest import signup

    pages = ["/", "/login", "/register"]
    for path in pages:
        html = client.get(path).get_data(as_text=True)
        assert 'style="' not in html, f"inline style attribute on {path} would be blocked by the CSP"
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f"inline <script> on {path}"
        assert " onclick=" not in html and " onsubmit=" not in html

    signup(client)
    sid = client.post("/api/sessions", json={"role": "QA Engineer", "total": 3}).get_json()["id"]
    for path in ["/", "/profile", f"/interview/{sid}", f"/history/{sid}"]:
        resp = client.get(path)
        assert resp.status_code == 200, path
        html = resp.get_data(as_text=True)
        assert 'style="' not in html and not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), path


def test_front_end_scripts_never_insert_html():
    """Model output and user text must only ever be inserted as plain text."""
    from pathlib import Path
    banned = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "setAttribute('style'", "cssText")
    for js in Path(__file__).resolve().parent.parent.joinpath("app", "static", "js").glob("*.js"):
        source = js.read_text(encoding="utf-8")
        for token in banned:
            assert token not in source, f"{js.name} uses {token}"