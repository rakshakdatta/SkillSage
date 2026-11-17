import pytest

from app.db import InterviewRecord
from app.services.history import HistoryService

from .conftest import finish_interview, make_settings, signup, start

THIN = "It is fast."
GOOD = None   # use the model answer


def test_signed_in_interviews_are_saved_with_full_detail(client, provider):
    signup(client)
    state = finish_interview(client, provider, total=3)
    listing = client.get("/api/history").get_json()["interviews"]
    assert len(listing) == 1
    item = listing[0]
    assert item["id"] == state["id"] and item["status"] == "completed" and item["answered"] == 3
    assert item["overall"] == state["report"]["overall"]

    detail = client.get(f"/api/history/{state['id']}").get_json()
    assert detail["finished"] and detail["report"]["summary"] and len(detail["history"]) == 3
    first = detail["history"][0]["evaluation"]
    assert set(first["scores"]) == {"relevance", "depth", "clarity", "structure", "grammar"}
    assert "grammar_issues" in first and first["delivery"]["words"] > 0


def test_grammar_issues_and_delivery_are_stored_per_answer(client, provider):
    signup(client)
    messy = "Last year I build an api. He dont know why. We working on it since 2 years."
    state = finish_interview(client, provider, total=3, answer_of=lambda q: messy)
    detail = client.get(f"/api/history/{state['id']}").get_json()
    evaluation = detail["history"][0]["evaluation"]
    assert evaluation["scores"]["grammar"] <= 5
    assert {i["kind"] for i in evaluation["grammar_issues"]} >= {"tense", "agreement"}
    assert detail["report"]["grammar_issue_count"] >= 6


def test_grammar_is_part_of_the_overall_score(client, provider):
    signup(client)
    clean = finish_interview(client, provider, total=3, answer_of=lambda q: provider._by_text[q["text"]]["ideal"])
    messy = finish_interview(client, provider, total=3,
                             answer_of=lambda q: "Last year I build it. " + provider._by_text[q["text"]]["ideal"].replace("I ", "He dont ", 1))
    assert messy["report"]["by_dimension"]["grammar"] < clean["report"]["by_dimension"]["grammar"]


def test_in_progress_interview_is_listed_as_in_progress(client):
    signup(client)
    state = start(client)
    item = client.get("/api/history").get_json()["interviews"][0]
    assert item["id"] == state["id"] and item["status"] == "in_progress" and item["overall"] is None


def test_other_users_cannot_see_or_touch_an_interview(app, client, provider):
    signup(client, email="ann@example.com")
    state = finish_interview(client, provider)
    intruder = app.test_client()
    signup(intruder, email="eve@example.com", name="Eve")
    assert intruder.get(f"/api/history/{state['id']}").status_code == 404
    assert intruder.get(f"/api/sessions/{state['id']}").status_code == 404
    assert intruder.get(f"/api/sessions/{state['id']}/report").status_code == 404
    assert intruder.post(f"/api/sessions/{state['id']}/answer", json={"answer": "hi"}).status_code == 404
    assert intruder.get("/api/history").get_json()["interviews"] == []
    anonymous = app.test_client()
    assert anonymous.get(f"/api/sessions/{state['id']}").status_code == 404


def test_guest_interviews_still_work_without_an_account(client, provider):
    state = finish_interview(client, provider)
    assert state["saved"] is False and client.get("/api/history").status_code == 401


def test_guest_can_save_a_finished_interview_after_signing_in(client, provider):
    state = finish_interview(client, provider)          # as a guest
    signup(client)
    assert client.get("/api/history").get_json()["interviews"] == []
    saved = client.post(f"/api/sessions/{state['id']}/save")
    assert saved.status_code == 200 and saved.get_json()["saved"] is True
    detail = client.get(f"/api/history/{state['id']}").get_json()
    assert len(detail["history"]) == 3 and detail["report"]["overall"] == state["report"]["overall"]
    assert client.post(f"/api/sessions/{state['id']}/save").status_code == 200       # idempotent


def test_unfinished_or_foreign_interviews_cannot_be_claimed(app, client, provider):
    signup(client)
    unfinished = start(client)
    assert client.post(f"/api/sessions/{unfinished['id']}/save").status_code in (200, 409)
    guest = app.test_client()
    finished_guest = finish_interview(guest, provider)
    other = app.test_client()
    signup(other, email="bob@example.com", name="Bob")
    assert other.post(f"/api/sessions/{finished_guest['id']}/save").status_code == 200
    third = app.test_client()
    signup(third, email="cat@example.com", name="Cat")
    assert third.post(f"/api/sessions/{finished_guest['id']}/save").status_code == 404     # already owned by Bob
    fresh = start(guest)
    owner = app.test_client()
    signup(owner, email="dan@example.com", name="Dan")
    assert owner.post(f"/api/sessions/{fresh['id']}/save").status_code == 409                # not finished


def test_a_database_failure_never_breaks_the_live_interview(client, provider, monkeypatch, caplog):
    signup(client)
    monkeypatch.setattr(HistoryService, "add_answer", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    state = start(client)
    resp = client.post(f"/api/sessions/{state['id']}/answer", json={"answer": "I would use an index."})
    assert resp.status_code == 200 and resp.get_json()["answered"] == 1
    assert "Could not save interview history" in caplog.text


def test_stats_summarise_progress(client, provider):
    signup(client)
    empty = client.get("/api/profile").get_json()["stats"]
    assert empty["completed"] == 0 and empty["average"] is None and empty["trend"] == []

    finish_interview(client, provider, answer_of=lambda q: THIN)                              # weak first
    finish_interview(client, provider, answer_of=lambda q: provider._by_text[q["text"]]["ideal"])   # strong second
    profile = client.get("/api/profile").get_json()
    stats = profile["stats"]
    assert stats["completed"] == 2 and len(stats["trend"]) == 2 and len(profile["recent"]) == 2
    assert stats["trend"][0]["overall"] < stats["trend"][1]["overall"]
    assert stats["best"] == stats["trend"][1]["overall"] and stats["latest"] == stats["trend"][1]["overall"]
    assert stats["change"] > 0
    assert set(stats["skills"]) == {"relevance", "depth", "clarity", "structure", "grammar"}
    assert stats["weakest"] in stats["skills"] and stats["strongest"] in stats["skills"]


def test_history_pagination_inputs_are_validated(client):
    signup(client)
    assert client.get("/api/history?limit=abc").status_code == 400
    assert client.get("/api/history?limit=1000&offset=-5").status_code == 200


def test_history_survives_a_new_app_instance(tmp_path, provider):
    """Saved interviews live in the database, not in memory."""
    from app import create_app
    from app.llm.offline import OfflineProvider
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    first = create_app(make_settings(database_url=url), OfflineProvider()).test_client()
    signup(first)
    state = finish_interview(first, provider)
    second = create_app(make_settings(database_url=url), OfflineProvider()).test_client()      # "restart"
    assert second.post("/api/auth/login", json={"email": "ann@example.com", "password": "Str0ng!passphrase"}).status_code == 200
    assert second.get(f"/api/history/{state['id']}").get_json()["report"]["overall"] == state["report"]["overall"]
    assert second.get(f"/api/sessions/{state['id']}").status_code == 404        # live copy is gone, saved copy remains