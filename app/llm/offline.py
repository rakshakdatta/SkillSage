"""Offline practice mode: no AI and no network.

Questions come from a built-in bank. Answers are scored with transparent rules:
  relevance  - how many of the question's key ideas the answer mentions
  depth      - length, concrete examples and numbers
  clarity    - sentence length and filler words
  structure  - linking words and a logical shape (first/then/because/result ...)
This is deliberately simple and honest about it: it rewards covering the right ideas,
it cannot judge whether the ideas are correct. The AI providers do that.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from .. import grammar
from ..models import DIMENSIONS, Context, Evaluation, Question
from .base import LLMProvider
from .parsing import clamp_score, overall_score

_DATA = Path(__file__).resolve().parent.parent / "data" / "questions.json"

_TRACK_HINTS = (
    ("frontend", ("front", "ui developer", "react", "angular", "vue", "web developer")),
    ("fullstack", ("full", "mern", "mean")),
    ("backend", ("back", "java", "spring", "node", "django", "api", "server")),
    ("data", ("data", "analyst", "analytics", "bi ", "business intelligence", "sql")),
    ("devops", ("devops", "sre", "cloud", "infra", "platform", "site reliability")),
    ("qa", ("qa", "test", "quality", "sdet")),
)

_EXAMPLE_MARKERS = ("for example", "for instance", "e.g", "such as", "in my project", "i built", "i worked",
                    "i used", "i implemented", "in my last", "at my internship", "i led", "i fixed")
_LINKING = ("first", "second", "third", "then", "next", "finally", "lastly", "because", "therefore", "so", "which",
            "while", "since", "however", "but", "also", "instead", "after", "before", "when", "if", "overall",
            "as a result", "for example", "for instance", "in conclusion", "to summarize", "situation", "task",
            "action", "result", "this means", "in practice")
_FILLERS = ("um", "uh", "like", "basically", "actually", "you know", "kind of", "sort of", "stuff", "things")

_ADVICE = {
    "relevance": "Answer the exact question first, then add detail. Mention the key concepts an interviewer expects.",
    "depth": "Go deeper: add a concrete example from your own project and, where you can, a number or result.",
    "clarity": "Use shorter sentences and cut filler words so each point lands clearly.",
    "structure": "Give it a shape: a one-line answer, then 2-3 supporting points, then a short conclusion (STAR for behavioural questions).",
    "grammar": "Tighten your sentence formation: finish each thought in a complete sentence and fix the points listed below.",
}
_PRAISE = {
    "relevance": "You stayed on the question and covered its key ideas.",
    "depth": "Good level of detail and concrete substance.",
    "clarity": "Clear, easy-to-follow wording.",
    "structure": "Well organised, with a logical flow.",
    "grammar": "Your sentences were well formed and easy to follow.",
}


def _load() -> dict:
    with _DATA.open(encoding="utf-8") as fh:
        return json.load(fh)


def track_for(role: str) -> str:
    text = f" {role.lower()} "
    for track, hints in _TRACK_HINTS:
        if any(h in text for h in hints):
            return track
    return "general"


def _words(text: str) -> list:
    return re.findall(r"[a-z0-9][a-z0-9'+#.\-]*", text.lower())


def _count_terms(text: str, terms) -> int:
    padded = f" {re.sub(r'[^a-z0-9 ]', ' ', text.lower())} "
    return sum(len(re.findall(rf"(?<![a-z]){re.escape(t)}(?![a-z])", padded)) for t in terms)


def _stem(word: str) -> str:
    """Crude stemmer so 'improved' also matches 'improve' and 'improving'."""
    for suffix in ("ing", "ed", "es", "s", "e"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _mentions(low: str, keyword: str) -> bool:
    if " " in keyword or not keyword.isalpha() or len(keyword) < 5:
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", low) is not None
    return re.search(rf"(?<![a-z0-9]){re.escape(_stem(keyword))}[a-z]*", low) is not None


def score_answer(entry: dict, answer: str) -> tuple[dict, list]:
    """Return ({dimension: 1-10}, [missing keywords])."""
    text = answer.strip()
    low = text.lower()
    words = _words(text)
    n = len(words)

    keywords = [k.lower() for k in entry["keywords"]]
    hits = [k for k in keywords if _mentions(low, k)]
    missing = [k for k in keywords if k not in hits]
    coverage = len(hits) / len(keywords)
    relevance = clamp_score(1 + 9 * min(1.0, coverage / 0.45))      # about half the key ideas = full marks

    depth = 1 if n < 10 else 2 if n < 25 else 4 if n < 45 else 6 if n < 90 else 7 if n < 170 else 8
    if any(m in low for m in _EXAMPLE_MARKERS):
        depth += 1
    if re.search(r"\d", text):
        depth += 1
    if relevance <= 3:
        depth = min(depth, 4)
    depth = clamp_score(depth)

    sentences = [s for s in re.split(r"[.!?\n]+", text) if s.strip()]
    avg = n / max(1, len(sentences))
    clarity = 8 if 7 <= avg <= 26 else 6 if avg < 7 or avg <= 34 else 4
    if n < 10:
        clarity = 2
    fillers_per_100 = 100 * _count_terms(low, _FILLERS) / max(1, n)
    if fillers_per_100 > 4:
        clarity -= 2
    elif fillers_per_100 > 2:
        clarity -= 1
    clarity = clamp_score(clarity)

    linking = sum(1 for m in _LINKING if re.search(rf"(?<![a-z]){re.escape(m)}(?![a-z])", low))
    sequences = sum(1 for s in sentences if s.count(",") >= 2)       # a step-by-step list inside one sentence
    has_example = any(m in low for m in _EXAMPLE_MARKERS) or bool(re.search(r"\d", text))
    structure = (3 + min(4, linking + min(2, sequences))
                 + (1 if len(sentences) >= 3 else 0) + (1 if len(sentences) >= 4 else 0) + (1 if has_example else 0))
    if n < 15:
        structure = min(structure, 3)
    structure = clamp_score(structure)

    return {"relevance": relevance, "depth": depth, "clarity": clarity, "structure": structure}, missing

def _overall(scores: dict) -> float:
    return overall_score(scores)


class OfflineProvider(LLMProvider):
    name = "Offline practice mode"
    is_ai = False

    def __init__(self):
        self._data = _load()
        self._by_text = {}
        for track in self._data["tracks"].values():
            for e in track["questions"]:
                self._by_text[e["q"]] = e
        for e in self._data["behavioral"]:
            self._by_text[e["q"]] = e

    # -- planning -------------------------------------------------------------
    def _plan(self, ctx: Context) -> list:
        rng = random.Random(f"{ctx.seed}-{ctx.role.lower()}-{ctx.total}")
        technical = list(self._data["tracks"][track_for(ctx.role)]["questions"])
        behavioral = list(self._data["behavioral"])
        rng.shuffle(technical)
        rng.shuffle(behavioral)
        n_beh = 0 if ctx.total <= 2 else 1 if ctx.total < 6 else 2
        n_tech = ctx.total - n_beh
        plan = technical[:n_tech]
        # pad from behavioural questions if the technical bank is smaller than the interview
        extra = behavioral[n_beh:]
        while len(plan) < n_tech and extra:
            plan.append(extra.pop())
        plan += behavioral[:n_beh]
        return plan[: ctx.total]

    def _question_at(self, ctx: Context) -> Question:
        plan = self._plan(ctx)
        entry = plan[min(ctx.index, len(plan) - 1)]
        return Question(text=entry["q"], topic=entry["topic"])

    # -- provider interface ---------------------------------------------------
    def first_question(self, ctx: Context) -> Question:
        return self._question_at(ctx)

    def review_answer(self, ctx, question, answer, want_next):
        entry = self._by_text.get(question.text) or {"keywords": [], "ideal": ""}
        if not entry["keywords"]:
            entry = {"keywords": ["example", "because", "result"], "ideal": "Give a direct answer, a concrete example and the result."}
        scores, missing = score_answer(entry, answer)
        language = grammar.analyze(answer)
        scores["grammar"] = language["score"]
        overall = _overall(scores)

        strengths = [_PRAISE[d] for d in DIMENSIONS if scores[d] >= 7][:3]
        weak = sorted((d for d in DIMENSIONS if scores[d] <= 5), key=lambda d: scores[d])
        improvements = [_ADVICE[d] for d in weak][:3]
        if missing and scores["relevance"] < 9:
            improvements.append("Key ideas missing from your answer: " + ", ".join(missing[:4]) + ".")

        if overall >= 8:
            lead = "Strong answer."
        elif overall >= 6:
            lead = "Solid answer with room to sharpen it."
        elif overall >= 4:
            lead = "A reasonable start, but it needs more substance."
        else:
            lead = "This answer is too thin to be convincing yet."
        weakest_dim = min(DIMENSIONS, key=lambda d: scores[d])
        feedback = lead if scores[weakest_dim] >= 8 else f"{lead} Biggest gap: {weakest_dim}."

        evaluation = Evaluation(scores=scores, overall=overall, feedback=feedback, strengths=strengths,
                                improvements=improvements, sample_answer=entry["ideal"],
                                grammar_issues=language["issues"])
        nxt = None
        if want_next:
            ahead = Context(role=ctx.role, level=ctx.level, total=ctx.total, index=ctx.index + 1,
                            seed=ctx.seed, resume_text=ctx.resume_text, history=ctx.history)
            nxt = self._question_at(ahead)
        return evaluation, nxt

    def final_report(self, ctx: Context) -> dict:
        history = ctx.history
        ranked = sorted(history, key=lambda h: h["overall"])
        mean = sum(h["overall"] for h in history) / max(1, len(history))
        summary = (
            f"You completed {len(history)} questions for a {ctx.level} {ctx.role} interview with an average score of {mean:.1f}/10. "
            "This was scored by Offline practice mode, which measures how many key ideas you covered, plus detail, clarity and structure. "
            "Use a connected AI model for deeper, answer-specific coaching."
        )
        # Clear split so an answer never appears as both a strength and a weakness.
        strong = [h for h in reversed(ranked) if h["overall"] >= 7][:2]
        weak = [h for h in ranked if h["overall"] < 7][:2]
        strengths = [f"{h['topic']}: scored {h['overall']}/10" for h in strong]
        if not strengths and history:
            best = ranked[-1]
            strengths = [f"{best['topic']}: your best answer so far ({best['overall']}/10)"]
        weaknesses = [f"{h['topic']}: scored {h['overall']}/10" for h in weak if h not in strong]
        plan = [{"focus": h["topic"], "action": "Re-answer this question aloud in under two minutes, covering the missing key ideas, then compare with the sample answer."}
                for h in weak]
        if not plan:
            plan = [{"focus": "Polish", "action": "Practise the same questions with a stricter time limit and add one measurable result to each answer."}]
        return {"summary": summary, "strengths": strengths, "weaknesses": weaknesses, "practice_plan": plan[:4]}