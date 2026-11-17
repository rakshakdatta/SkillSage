"""Turn raw model text into validated objects. Anything malformed raises LLMError."""
from __future__ import annotations

import json
import re

from ..errors import LLMError
from ..models import DIMENSIONS, Evaluation, Question

WEIGHTS = {"relevance": 0.30, "depth": 0.25, "clarity": 0.15, "structure": 0.15, "grammar": 0.15}

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and stray prose."""
    if not isinstance(text, str) or not text.strip():
        raise LLMError("The model returned an empty response.")
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("The model did not return JSON.")
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("The model returned malformed JSON.") from exc
    if not isinstance(data, dict):
        raise LLMError("The model returned an unexpected JSON shape.")
    return data


def _text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _items(value, limit: int = 220, count: int = 4) -> list:
    if not isinstance(value, list):
        return []
    return [s for s in (_text(v, limit) for v in value) if s][:count]


def overall_score(scores: dict) -> float:
    """Weighted average over whichever dimensions are present."""
    total = sum(WEIGHTS[d] for d in scores if d in WEIGHTS)
    return round(sum(scores[d] * WEIGHTS[d] for d in scores if d in WEIGHTS) / total, 1)


def parse_grammar_issues(value) -> list:
    if not isinstance(value, list):
        return []
    issues = []
    for item in value:
        if not isinstance(item, dict):
            continue
        original, suggestion = _text(item.get("original"), 200), _text(item.get("suggestion"), 200)
        if original and suggestion and original != suggestion:
            issues.append({"original": original, "suggestion": suggestion,
                           "note": _text(item.get("note"), 160), "kind": _text(item.get("kind"), 20) or "grammar"})
    return issues[:5]


def clamp_score(value) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        raise LLMError("The model returned a non-numeric score.")
    return max(1, min(10, number))


def parse_question(obj) -> Question:
    if not isinstance(obj, dict):
        raise LLMError("The model did not return a question.")
    text = _text(obj.get("question"), 600)
    if len(text) < 8:
        raise LLMError("The model returned an empty question.")
    return Question(text=text, topic=_text(obj.get("topic"), 40) or "General")


def parse_evaluation(data: dict) -> Evaluation:
    raw = data.get("scores")
    if not isinstance(raw, dict):
        raise LLMError("The model did not return scores.")
    scores = {d: clamp_score(raw.get(d)) for d in DIMENSIONS}
    overall = overall_score(scores)
    feedback = _text(data.get("feedback"), 900)
    if not feedback:
        raise LLMError("The model returned no feedback.")
    return Evaluation(
        scores=scores,
        overall=overall,
        feedback=feedback,
        strengths=_items(data.get("strengths")),
        improvements=_items(data.get("improvements")),
        sample_answer=_text(data.get("sample_answer"), 1200),
        grammar_issues=parse_grammar_issues(data.get("grammar_issues")),
    )


def parse_report(data: dict) -> dict:
    plan = []
    for entry in data.get("practice_plan") or []:
        if isinstance(entry, dict):
            focus, action = _text(entry.get("focus"), 80), _text(entry.get("action"), 260)
            if focus and action:
                plan.append({"focus": focus, "action": action})
    summary = _text(data.get("summary"), 1200)
    if not summary:
        raise LLMError("The model returned no summary.")
    return {
        "summary": summary,
        "strengths": _items(data.get("strengths")),
        "weaknesses": _items(data.get("weaknesses")),
        "practice_plan": plan[:4],
    }