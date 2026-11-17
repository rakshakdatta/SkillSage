"""Plain data classes shared by the services and the LLM providers."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

DIMENSIONS = ("relevance", "depth", "clarity", "structure", "grammar")
LEVELS = ("intern", "junior", "mid", "senior")


@dataclass
class Question:
    text: str
    topic: str = "General"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Evaluation:
    scores: dict            # one 1-10 integer per dimension (see DIMENSIONS)
    overall: float          # weighted average, one decimal
    feedback: str
    strengths: list
    improvements: list
    sample_answer: str
    grammar_issues: list = field(default_factory=list)   # [{original, suggestion, note, kind}]
    delivery: dict = field(default_factory=dict)         # words, filler words, speaking time ...

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Turn:
    question: Question
    answer: str | None = None
    evaluation: Evaluation | None = None


@dataclass
class Context:
    """Everything a provider needs to know about the interview so far."""
    role: str
    level: str
    total: int
    index: int                      # number of questions already answered
    seed: int
    resume_text: str = ""
    history: list = field(default_factory=list)   # [{question, topic, answer, overall}]


@dataclass
class Session:
    role: str
    level: str
    total: int
    resume_text: str
    provider_name: str
    is_ai: bool
    seed: int = field(default_factory=lambda: uuid.uuid4().int % 1_000_000)
    user_id: int | None = None          # set when a signed-in user owns the interview
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    turns: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished: bool = False
    report: dict | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)