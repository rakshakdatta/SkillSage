import pytest

from app import create_app
from app.config import Settings
from app.llm.offline import OfflineProvider


def make_settings(**overrides) -> Settings:
    base = dict(llm_provider="offline", rate_limit_per_minute=1000, auth_rate_limit=1000, database_url="sqlite://", secret_key="test-secret")
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings():
    return make_settings()


@pytest.fixture
def provider():
    return OfflineProvider()


@pytest.fixture
def app(settings, provider):
    return create_app(settings, provider)


@pytest.fixture
def client(app):
    return app.test_client()


def start(client, role="Backend Developer", total=3, level="junior"):
    resp = client.post("/api/sessions", json={"role": role, "level": level, "total": total})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def make_pdf(text: str) -> bytes:
    """A minimal single-page PDF containing `text`, built by hand (no extra dependency)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out

PASSWORD = "Str0ng!passphrase"


def signup(client, email="ann@example.com", name="Ann", password=PASSWORD):
    resp = client.post("/api/auth/register", json={"email": email, "name": name, "password": password})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["user"]


def finish_interview(client, provider, total=3, role="Backend Developer", answer_of=None):
    """Run a whole interview. answer_of(question_dict) -> answer text (default: the model answer)."""
    state = start(client, role=role, total=total)
    sid = state["id"]
    while not state["finished"]:
        question = state["current_question"]
        text = answer_of(question) if answer_of else provider._by_text[question["text"]]["ideal"]
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": text})
        assert resp.status_code == 200, resp.get_json()
        state = resp.get_json()
    return state