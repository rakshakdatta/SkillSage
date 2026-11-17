"""Use a hosted model first and fall back to a local one when it fails (quota used up, key rejected, outage)."""
from __future__ import annotations

import logging
import time

from ..errors import LLMError
from ..models import Context, Question
from .base import LLMProvider

log = logging.getLogger(__name__)


class FallbackProvider(LLMProvider):
    is_ai = True

    def __init__(self, primary: LLMProvider, backup: LLMProvider, cooldown_seconds: int = 60, clock=time.monotonic):
        self.primary, self.backup = primary, backup
        self.cooldown = cooldown_seconds
        self._clock = clock
        self._skip_primary_until = 0.0
        self.name = f"{primary.name} + backup {backup.name}"

    def _run(self, method: str, *args):
        if self._clock() >= self._skip_primary_until:
            try:
                return getattr(self.primary, method)(*args)
            except LLMError as exc:
                # skip the hosted model for a minute so every request is not slowed by a doomed call
                self._skip_primary_until = self._clock() + self.cooldown
                log.warning("%s failed (%s); using %s", self.primary.name, type(exc).__name__, self.backup.name)
        return getattr(self.backup, method)(*args)

    def first_question(self, ctx: Context) -> Question:
        return self._run("first_question", ctx)

    def review_answer(self, ctx, question, answer, want_next):
        return self._run("review_answer", ctx, question, answer, want_next)

    def final_report(self, ctx: Context) -> dict:
        return self._run("final_report", ctx)
