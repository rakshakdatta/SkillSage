import time

import pytest

from app.errors import NotFound
from app.models import Session
from app.services.store import SessionStore


def make(**kw):
    return Session(role="QA", level="junior", total=3, resume_text="", provider_name="x", is_ai=False, **kw)


def test_get_and_missing():
    store = SessionStore()
    s = make()
    store.add(s)
    assert store.get(s.id) is s
    with pytest.raises(NotFound):
        store.get("missing")


def test_expiry():
    store = SessionStore(ttl_minutes=1)
    s = make()
    s.created_at = time.time() - 120
    store.add(s)
    with pytest.raises(NotFound):
        store.get(s.id)


def test_cap_evicts_oldest():
    store = SessionStore(max_sessions=3)
    sessions = []
    for i in range(5):
        s = make()
        s.created_at = time.time() + i
        store.add(s)
        sessions.append(s)
    assert len(store) == 3
    with pytest.raises(NotFound):
        store.get(sessions[0].id)
    assert store.get(sessions[4].id) is sessions[4]