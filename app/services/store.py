"""In-memory session store with expiry and a hard cap, so memory use stays bounded."""
from __future__ import annotations

import threading
import time

from ..errors import NotFound
from ..models import Session


class SessionStore:
    def __init__(self, ttl_minutes: int = 180, max_sessions: int = 500):
        self._ttl = ttl_minutes * 60
        self._max = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def add(self, session: Session) -> None:
        with self._lock:
            self._purge_expired()
            while len(self._sessions) >= self._max:
                oldest = min(self._sessions.values(), key=lambda s: s.created_at)
                del self._sessions[oldest.id]
            self._sessions[session.id] = session

    def get(self, session_id: str) -> Session:
        with self._lock:
            self._purge_expired()
            session = self._sessions.get(session_id)
        if session is None:
            raise NotFound("This interview was not found. It may have expired; please start a new one.")
        return session

    def _purge_expired(self) -> None:
        cutoff = time.time() - self._ttl
        for sid in [sid for sid, s in self._sessions.items() if s.created_at < cutoff]:
            del self._sessions[sid]

    def __len__(self) -> int:
        return len(self._sessions)