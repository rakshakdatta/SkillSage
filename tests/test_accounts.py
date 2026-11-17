import pytest

from app import create_app
from app.db import InterviewRecord, User, db
from app.llm.offline import OfflineProvider

from .conftest import PASSWORD, finish_interview, make_settings, signup


def test_register_signs_you_in_and_hashes_the_password(app, client):
    user = signup(client)
    assert user["email"] == "ann@example.com" and "password" not in user
    assert client.get("/api/auth/me").get_json()["user"]["name"] == "Ann"
    with app.app_context():
        stored = User.query.one()
        assert PASSWORD not in stored.password_hash and stored.password_hash.startswith(("scrypt:", "pbkdf2:"))


@pytest.mark.parametrize("payload, status", [
    ({"email": "not-an-email", "name": "A", "password": PASSWORD}, 400),
    ({"email": "a@example.com", "name": "", "password": PASSWORD}, 400),
    ({"email": "a@example.com", "name": "A", "password": "short"}, 400),
    ({"email": "a@example.com", "name": "A", "password": "password"}, 400),
    ({"email": "a@example.com", "name": "A", "password": "x" * 200}, 400),
    ({"email": ["a@example.com"], "name": "A", "password": PASSWORD}, 400),
    ({"email": "a@example.com", "name": "A", "password": 12345678}, 400),
])
def test_registration_validation(client, payload, status):
    assert client.post("/api/auth/register", json=payload).status_code == status


def test_duplicate_email_is_rejected_case_insensitively(client):
    signup(client, email="ann@example.com")
    other = client.application.test_client()
    resp = other.post("/api/auth/register", json={"email": "ANN@Example.com", "name": "X", "password": PASSWORD})
    assert resp.status_code == 409


def test_login_logout_flow(client):
    signup(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").get_json()["user"] is None
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}).status_code == 401
    ok = client.post("/api/auth/login", json={"email": " ANN@example.com ", "password": PASSWORD})
    assert ok.status_code == 200 and client.get("/api/auth/me").get_json()["user"]["email"] == "ann@example.com"


def test_wrong_password_and_unknown_user_look_identical(client):
    signup(client)
    a = client.post("/api/auth/login", json={"email": "ann@example.com", "password": "nope-nope-nope"})
    b = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401 and a.get_json() == b.get_json()


def test_session_cookie_is_httponly_and_samesite(client):
    resp = client.post("/api/auth/register", json={"email": "c@example.com", "name": "C", "password": PASSWORD})
    cookie = resp.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie


def test_auth_endpoints_are_rate_limited():
    client = create_app(make_settings(auth_rate_limit=4), OfflineProvider()).test_client()
    codes = [client.post("/api/auth/login", json={"email": "x@example.com", "password": "whatever1"}).status_code for _ in range(6)]
    assert codes[:4] == [401] * 4 and codes[4:] == [429, 429]


def test_cross_site_requests_are_blocked_but_same_site_works(client):
    signup(client)
    evil = client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert client.get("/api/auth/me").get_json()["user"] is not None          # still signed in
    ok = client.post("/api/auth/logout", headers={"Origin": "http://localhost"})
    assert ok.status_code == 200


def test_profile_requires_sign_in(client):
    for method, path in [("get", "/api/profile"), ("get", "/api/history"), ("patch", "/api/profile")]:
        assert getattr(client, method)(path, json={}).status_code == 401


def test_profile_update_and_validation(client):
    signup(client)
    ok = client.patch("/api/profile", json={"name": "Ann Lee", "target_role": "Data Analyst", "level": "mid"})
    assert ok.status_code == 200 and ok.get_json()["user"]["target_role"] == "Data Analyst"
    assert client.patch("/api/profile", json={"level": "wizard"}).status_code == 400
    assert client.patch("/api/profile", json={"name": ""}).status_code == 400
    assert client.patch("/api/profile", json={"target_role": "<script>"}).status_code == 400


def test_change_password(client):
    signup(client)
    assert client.post("/api/profile/password", json={"current_password": "wrong", "new_password": "An0ther!passphrase"}).status_code == 403
    assert client.post("/api/profile/password", json={"current_password": PASSWORD, "new_password": "short"}).status_code == 400
    assert client.post("/api/profile/password", json={"current_password": PASSWORD, "new_password": "An0ther!passphrase"}).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ann@example.com", "password": "An0ther!passphrase"}).status_code == 200


def test_delete_account_removes_the_user_and_their_interviews(app, client, provider):
    signup(client)
    finish_interview(client, provider)
    assert client.delete("/api/profile", json={"password": "wrong"}).status_code == 403
    assert client.delete("/api/profile", json={"password": PASSWORD}).status_code == 200
    assert client.get("/api/auth/me").get_json()["user"] is None
    with app.app_context():
        assert User.query.count() == 0 and InterviewRecord.query.count() == 0
        assert db.session.execute(db.text("select count(*) from answers")).scalar() == 0


def test_pages_redirect_anonymous_visitors_to_sign_in(client):
    for path in ("/profile", "/history/0123456789abcdef"):
        resp = client.get(path)
        assert resp.status_code == 302 and "/login" in resp.headers["Location"]


def test_signed_in_visitors_skip_the_login_page(client):
    signup(client)
    assert client.get("/login").status_code == 302
    assert client.get("/profile").status_code == 200