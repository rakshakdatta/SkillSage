"""Database models. SQLite by default; set DATABASE_URL for MySQL or PostgreSQL."""
from __future__ import annotations

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> datetime:
    """Naive UTC timestamps keep SQLite and server databases consistent."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    target_role = db.Column(db.String(60), nullable=False, default="")
    level = db.Column(db.String(10), nullable=False, default="junior")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    interviews = db.relationship("InterviewRecord", back_populates="user", cascade="all, delete-orphan",
                                 order_by="InterviewRecord.started_at.desc()")


class InterviewRecord(db.Model):
    __tablename__ = "interviews"

    id = db.Column(db.String(32), primary_key=True)                       # same id as the live session
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(60), nullable=False)
    level = db.Column(db.String(10), nullable=False)
    total = db.Column(db.Integer, nullable=False)
    provider_name = db.Column(db.String(80), nullable=False)
    is_ai = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(12), nullable=False, default="in_progress")   # in_progress | completed
    overall = db.Column(db.Float)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime)
    report_json = db.Column(db.Text)

    user = db.relationship("User", back_populates="interviews")
    answers = db.relationship("AnswerRecord", back_populates="interview", cascade="all, delete-orphan",
                              order_by="AnswerRecord.position")


class AnswerRecord(db.Model):
    __tablename__ = "answers"

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.String(32), db.ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)                      # 1-based question number
    question = db.Column(db.Text, nullable=False)
    topic = db.Column(db.String(60), nullable=False, default="General")
    answer = db.Column(db.Text, nullable=False)
    evaluation_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    interview = db.relationship("InterviewRecord", back_populates="answers")