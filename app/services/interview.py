"""Interview orchestration: validation, session state, persistence and calls to the provider."""
from __future__ import annotations

import logging
import re

from .. import grammar
from ..config import Settings
from ..db import db
from ..errors import ApiError, Conflict, LLMError, NotFound
from ..llm.base import LLMProvider
from ..models import DIMENSIONS, LEVELS, Context, Question, Session, Turn
from .history import HistoryService
from .resume import clean
from .store import SessionStore

log = logging.getLogger("skillsage")

_ROLE_OK = re.compile(r"^[\w .,/&+#()\-]{2,60}$")


def _public_question(session: Session) -> dict | None:
    if session.finished or not session.turns:
        return None
    turn = session.turns[-1]
    if turn.answer is not None:
        return None
    return {"index": len(session.turns), **turn.question.to_dict()}


class InterviewService:
    def __init__(self, store: SessionStore, provider: LLMProvider, settings: Settings, history: HistoryService | None = None):
        self.store = store
        self.provider = provider
        self.settings = settings
        self.history = history

    # -- helpers --------------------------------------------------------------
    def _owned(self, session_id: str, user_id: int | None) -> Session:
        """A signed-in user's interview is private to them. Guest interviews are reachable by their id."""
        session = self.store.get(session_id)
        if session.user_id is not None and session.user_id != user_id:
            raise NotFound("This interview was not found. It may have expired; please start a new one.")
        return session

    def _save(self, action) -> None:
        """Saving history must never break a live interview."""
        if self.history is None:
            return
        try:
            action()
        except Exception:  # noqa: BLE001 - deliberate: log and carry on
            log.exception("Could not save interview history")
            db.session.rollback()

    def _context(self, session: Session) -> Context:
        history = [
            {"question": t.question.text, "topic": t.question.topic, "answer": t.answer, "overall": t.evaluation.overall}
            for t in session.turns if t.answer is not None and t.evaluation is not None
        ]
        return Context(role=session.role, level=session.level, total=session.total, index=len(history),
                       seed=session.seed, resume_text=session.resume_text, history=history)

    def serialize(self, session: Session) -> dict:
        answered = sum(1 for t in session.turns if t.answer is not None)
        return {
            "id": session.id,
            "role": session.role,
            "level": session.level,
            "total": session.total,
            "answered": answered,
            "finished": session.finished,
            "provider": {"name": session.provider_name, "is_ai": session.is_ai},
            "current_question": _public_question(session),
            "history": [
                {"index": i + 1, "question": t.question.text, "topic": t.question.topic, "answer": t.answer,
                 "evaluation": t.evaluation.to_dict() if t.evaluation else None}
                for i, t in enumerate(session.turns) if t.answer is not None
            ],
            "report": session.report,
            "saved": session.user_id is not None,
        }

    # -- use cases ------------------------------------------------------------
    def start(self, role: str, level: str, total, resume_text: str = "", user_id: int | None = None) -> dict:
        role = (role or "").strip() if isinstance(role, str) else ""
        if not _ROLE_OK.match(role):
            raise ApiError("Enter a role such as 'Backend Developer' (2 to 60 characters, letters and numbers).")
        level = (level or "junior").strip().lower() if isinstance(level, str) else "junior"
        if level not in LEVELS:
            raise ApiError(f"Level must be one of: {', '.join(LEVELS)}.")
        try:
            total = int(total)
        except (TypeError, ValueError):
            raise ApiError("The number of questions must be a number.")
        if not 3 <= total <= 10:
            raise ApiError("Choose between 3 and 10 questions.")
        resume_text = clean(resume_text if isinstance(resume_text, str) else "", self.settings.max_resume_chars)

        session = Session(role=role, level=level, total=total, resume_text=resume_text,
                          provider_name=self.provider.name, is_ai=self.provider.is_ai, user_id=user_id)
        question = self.provider.first_question(self._context(session))
        session.turns.append(Turn(question=question))
        self.store.add(session)
        if user_id is not None:
            self._save(lambda: self.history.create(session))
        return self.serialize(session)

    def get(self, session_id: str, user_id: int | None = None) -> dict:
        return self.serialize(self._owned(session_id, user_id))

    def answer(self, session_id: str, answer, user_id: int | None = None) -> dict:
        session = self._owned(session_id, user_id)
        answer = answer.strip() if isinstance(answer, str) else ""
        if not answer:
            raise ApiError("Write an answer before submitting.")
        if len(answer) > self.settings.max_answer_chars:
            raise ApiError(f"Please keep answers under {self.settings.max_answer_chars} characters.", 413)

        with session.lock:
            if session.finished:
                raise Conflict("This interview is already finished.")
            turn = session.turns[-1]
            if turn.answer is not None:
                raise Conflict("That question was already answered.")

            ctx = self._context(session)
            is_last = ctx.index + 1 >= session.total
            evaluation, nxt = self.provider.review_answer(ctx, turn.question, answer, want_next=not is_last)
            evaluation.delivery = grammar.delivery(answer)      # plain facts, the same for every provider

            turn.answer = answer
            turn.evaluation = evaluation
            position = len(session.turns)
            if session.user_id is not None:
                self._save(lambda: self.history.add_answer(session, position, turn))
            if is_last:
                session.report = self._build_report(session)
                session.finished = True
                if session.user_id is not None:
                    self._save(lambda: self.history.finish(session))
            else:
                session.turns.append(Turn(question=nxt or Question("Tell me more about your experience.", "General")))

            result = self.serialize(session)
        result["evaluation"] = evaluation.to_dict()
        return result

    def report(self, session_id: str, user_id: int | None = None) -> dict:
        session = self._owned(session_id, user_id)
        if not session.finished or session.report is None:
            raise Conflict("The report is available once every question has been answered.")
        return self.serialize(session)

    def claim(self, session_id: str, user_id: int) -> dict:
        """Attach a finished guest interview to the account that just signed in."""
        session = self.store.get(session_id)
        if session.user_id is not None:
            if session.user_id == user_id:
                return self.serialize(session)
            raise NotFound("This interview was not found.")
        if not session.finished:
            raise Conflict("Finish the interview before saving it.")
        with session.lock:
            session.user_id = user_id
            self._save(lambda: self.history.save_whole(session))
        return self.serialize(session)

    # -- report ---------------------------------------------------------------
    def _build_report(self, session: Session) -> dict:
        ctx = self._context(session)
        answered = [t for t in session.turns if t.evaluation is not None]
        overall = round(sum(t.evaluation.overall for t in answered) / max(1, len(answered)), 1)
        by_dimension = {
            d: round(sum(t.evaluation.scores[d] for t in answered) / max(1, len(answered)), 1) for d in DIMENSIONS
        }
        issues = sum(len(t.evaluation.grammar_issues) for t in answered)
        fillers = sum(t.evaluation.delivery.get("filler_total", 0) for t in answered)
        try:
            narrative = self.provider.final_report(ctx)
            degraded = False
        except LLMError:
            # The answers are already scored; never lose the results because the summary call failed.
            narrative = self._score_based_narrative(ctx, overall)
            degraded = True
        return {"overall": overall, "by_dimension": by_dimension, "summary_degraded": degraded,
                "grammar_issue_count": issues, "filler_total": fillers, **narrative}

    @staticmethod
    def _score_based_narrative(ctx: Context, overall: float) -> dict:
        ranked = sorted(ctx.history, key=lambda h: h["overall"])
        weakest = [h for h in ranked if h["overall"] < 6][:3]
        strongest = [h for h in reversed(ranked) if h["overall"] >= 7][:3]
        return {
            "summary": (f"You answered {len(ctx.history)} questions with an average of {overall}/10. "
                        "The written coaching summary could not be generated this time, but every answer above "
                        "has its own score and feedback."),
            "strengths": [f"{h['topic']} ({h['overall']}/10)" for h in strongest],
            "weaknesses": [f"{h['topic']} ({h['overall']}/10)" for h in weakest],
            "practice_plan": [{"focus": h["topic"], "action": "Re-answer this question aloud in under two minutes and compare with the sample answer."}
                              for h in weakest] or [{"focus": "Polish", "action": "Repeat the interview with a stricter time limit and add one measurable result to each answer."}],
        }