"""Saves interviews for signed-in users and turns them into progress statistics."""
from __future__ import annotations

import json
from collections import defaultdict

from ..db import AnswerRecord, InterviewRecord, db, utcnow
from ..models import DIMENSIONS, Session, Turn


def _iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


class HistoryService:
    # -- writing ----------------------------------------------------------------
    def create(self, session: Session) -> None:
        db.session.add(InterviewRecord(
            id=session.id, user_id=session.user_id, role=session.role, level=session.level, total=session.total,
            provider_name=session.provider_name, is_ai=session.is_ai, status="in_progress", started_at=utcnow()))
        db.session.commit()

    def add_answer(self, session: Session, position: int, turn: Turn) -> None:
        db.session.add(AnswerRecord(
            interview_id=session.id, position=position, question=turn.question.text, topic=turn.question.topic,
            answer=turn.answer, evaluation_json=json.dumps(turn.evaluation.to_dict())))
        db.session.commit()

    def finish(self, session: Session) -> None:
        record = db.session.get(InterviewRecord, session.id)
        if record is None:
            return
        record.status = "completed"
        record.overall = session.report["overall"]
        record.report_json = json.dumps(session.report)
        record.finished_at = utcnow()
        db.session.commit()

    def save_whole(self, session: Session) -> None:
        """Store an interview that was finished as a guest, once the visitor signs in."""
        self.create(session)
        for position, turn in enumerate(session.turns, 1):
            if turn.answer is not None and turn.evaluation is not None:
                self.add_answer(session, position, turn)
        self.finish(session)

    # -- reading ----------------------------------------------------------------
    @staticmethod
    def _summary(record: InterviewRecord) -> dict:
        return {"id": record.id, "role": record.role, "level": record.level, "total": record.total,
                "status": record.status, "overall": record.overall, "answered": len(record.answers),
                "provider": record.provider_name, "started_at": _iso(record.started_at),
                "finished_at": _iso(record.finished_at)}

    def list(self, user_id: int, limit: int = 50, offset: int = 0) -> list:
        rows = (InterviewRecord.query.filter_by(user_id=user_id)
                .order_by(InterviewRecord.started_at.desc()).offset(offset).limit(limit).all())
        return [self._summary(r) for r in rows]

    def get(self, user_id: int, interview_id: str) -> dict | None:
        record = InterviewRecord.query.filter_by(id=interview_id, user_id=user_id).first()
        if record is None:
            return None
        return {
            **self._summary(record),
            "finished": record.status == "completed",
            "provider": {"name": record.provider_name, "is_ai": record.is_ai},
            "current_question": None,
            "history": [{"index": a.position, "question": a.question, "topic": a.topic, "answer": a.answer,
                         "evaluation": json.loads(a.evaluation_json)} for a in record.answers],
            "report": json.loads(record.report_json) if record.report_json else None,
            "saved": True,
        }

    def stats(self, user_id: int) -> dict:
        rows = (InterviewRecord.query.filter_by(user_id=user_id, status="completed")
                .order_by(InterviewRecord.finished_at.asc()).all())
        in_progress = InterviewRecord.query.filter_by(user_id=user_id, status="in_progress").count()
        empty = {"completed": 0, "in_progress": in_progress, "average": None, "best": None, "latest": None,
                 "change": None, "trend": [], "skills": {}, "weakest": None, "strongest": None}
        if not rows:
            return empty

        scores = [r.overall for r in rows if r.overall is not None]
        per_skill = defaultdict(list)
        for r in rows:
            by_dim = (json.loads(r.report_json).get("by_dimension") if r.report_json else None) or {}
            for d in DIMENSIONS:
                if d in by_dim:
                    per_skill[d].append(by_dim[d])
        skills = {d: round(sum(v) / len(v), 1) for d, v in per_skill.items()}

        change = None
        if len(scores) >= 4:      # recent three vs the three before them
            recent, earlier = scores[-3:], scores[-6:-3]
            change = round(sum(recent) / len(recent) - sum(earlier) / len(earlier), 1)
        elif len(scores) >= 2:
            change = round(scores[-1] - scores[0], 1)

        return {
            "completed": len(rows), "in_progress": in_progress,
            "average": round(sum(scores) / len(scores), 1), "best": max(scores), "latest": scores[-1],
            "change": change,
            "trend": [{"id": r.id, "role": r.role, "date": _iso(r.finished_at), "overall": r.overall} for r in rows[-12:]],
            "skills": skills,
            "weakest": min(skills, key=skills.get) if skills else None,
            "strongest": max(skills, key=skills.get) if skills else None,
        }