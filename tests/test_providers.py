import json

import pytest
import requests

from app.errors import LLMAuthError, LLMError, LLMRateLimitError
from app.llm import parsing
from app.llm.parsing import WEIGHTS
from app.llm.factory import build_provider
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider
from app.llm.offline import OfflineProvider
from app.config import Settings
from app.models import Context, Question

CTX = Context(role="Backend Developer", level="junior", total=3, index=0, seed=1, resume_text="Built APIs.")
SECRET = "sk-test-SECRET-1234567890"

REVIEW = {
    "scores": {"relevance": 8, "depth": 7, "clarity": 9, "structure": 6, "grammar": 7},
    "feedback": "Solid answer. Add a measurable result.",
    "strengths": ["Clear"], "improvements": ["Add numbers"], "sample_answer": "A stronger answer.",
    "grammar_issues": [{"original": "he dont know", "suggestion": "he doesn't know", "note": "agreement"}],
    "next_question": {"question": "How do you design a rate limiter?", "topic": "System design"},
}


class FakeResp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def gemini_reply(text):
    return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


def groq_reply(text):
    return FakeResp(200, {"choices": [{"message": {"content": text}}]})


@pytest.fixture
def post(monkeypatch):
    """Queue fake HTTP responses for requests.post and record what was sent."""
    queue, sent = [], []

    def fake_post(url, **kwargs):
        sent.append({"url": url, **kwargs})
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(requests, "post", fake_post)
    return queue, sent


def test_gemini_review_parses_scores_and_next_question(post):
    queue, sent = post
    queue.append(gemini_reply(json.dumps(REVIEW)))
    provider = GeminiProvider(SECRET, "gemini-test")
    evaluation, nxt = provider.review_answer(CTX, Question("What is an index?", "DB"), "It speeds up reads.", want_next=True)
    assert evaluation.scores == {"relevance": 8, "depth": 7, "clarity": 9, "structure": 6, "grammar": 7}
    assert evaluation.grammar_issues == [{"original": "he dont know", "suggestion": "he doesn't know", "note": "agreement", "kind": "grammar"}]
    assert evaluation.overall == round(sum(s * WEIGHTS[d] for d, s in evaluation.scores.items()), 1)
    assert nxt.text.startswith("How do you design")
    # the key travels in a header, never in the URL, and the answer is fenced as data
    assert SECRET not in sent[0]["url"] and sent[0]["headers"]["x-goog-api-key"] == SECRET
    prompt = sent[0]["json"]["contents"][0]["parts"][0]["text"]
    assert "<candidate_answer>\nIt speeds up reads.\n</candidate_answer>" in prompt
    assert "untrusted" in sent[0]["json"]["systemInstruction"]["parts"][0]["text"]


def test_code_fences_and_prose_are_tolerated(post):
    queue, _ = post
    queue.append(gemini_reply("Here you go:\n```json\n" + json.dumps({"question": "Explain REST in one minute.", "topic": "APIs"}) + "\n```"))
    assert GeminiProvider(SECRET, "m").first_question(CTX).topic == "APIs"


def test_invalid_json_is_retried_once(post):
    queue, sent = post
    queue += [gemini_reply("sorry, I cannot do that"), gemini_reply(json.dumps({"question": "Explain REST in one minute.", "topic": "APIs"}))]
    assert GeminiProvider(SECRET, "m").first_question(CTX).text.startswith("Explain REST")
    assert len(sent) == 2


def test_gives_up_after_two_bad_replies(post):
    queue, sent = post
    queue += [gemini_reply("nope"), gemini_reply("still nope")]
    with pytest.raises(LLMError):
        GeminiProvider(SECRET, "m").first_question(CTX)
    assert len(sent) == 2


def test_rate_limit_is_not_retried(post):
    queue, sent = post
    queue.append(FakeResp(429, text="quota"))
    with pytest.raises(LLMRateLimitError):
        GeminiProvider(SECRET, "m").first_question(CTX)
    assert len(sent) == 1


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_is_reported_without_leaking_it(post, status):
    queue, _ = post
    queue.append(FakeResp(status, text=f"bad key {SECRET}"))
    with pytest.raises(LLMAuthError) as info:
        GeminiProvider(SECRET, "m").first_question(CTX)
    assert SECRET not in str(info.value)


def test_timeout_and_connection_errors_become_llm_errors(post):
    queue, _ = post
    queue.append(requests.Timeout("slow"))
    queue.append(requests.ConnectionError("down"))
    provider = GeminiProvider(SECRET, "m")
    with pytest.raises(LLMError):
        provider._complete("s", "u")
    with pytest.raises(LLMError):
        provider._complete("s", "u")


def test_blocked_or_empty_candidates(post):
    queue, _ = post
    queue.append(FakeResp(200, {"candidates": []}))
    with pytest.raises(LLMError):
        GeminiProvider(SECRET, "m")._complete("s", "u")


def test_groq_openai_style_response(post):
    queue, sent = post
    queue.append(groq_reply(json.dumps(REVIEW)))
    evaluation, nxt = GroqProvider(SECRET, "llama-test").review_answer(CTX, Question("What is an index?", "DB"), "answer", True)
    assert evaluation.overall > 0 and nxt is not None
    assert sent[0]["headers"]["Authorization"] == f"Bearer {SECRET}"
    assert sent[0]["json"]["response_format"] == {"type": "json_object"}


def test_scores_are_clamped_and_validated():
    ev = parsing.parse_evaluation({"scores": {"relevance": 15, "depth": "7", "clarity": 0, "structure": 5.6, "grammar": 99}, "feedback": "ok"})
    assert ev.scores == {"relevance": 10, "depth": 7, "clarity": 1, "structure": 6, "grammar": 10}
    with pytest.raises(LLMError):
        parsing.parse_evaluation({"scores": {"relevance": "high"}, "feedback": "x"})
    with pytest.raises(LLMError):
        parsing.parse_evaluation({"feedback": "x"})
    with pytest.raises(LLMError):
        parsing.parse_question({"question": "?"})


def test_model_text_is_length_limited():
    ev = parsing.parse_evaluation({"scores": {d: 5 for d in ("relevance", "depth", "clarity", "structure", "grammar")},
                                   "feedback": "x" * 5000, "strengths": ["a"] * 20})
    assert len(ev.feedback) <= 900 and len(ev.strengths) <= 4


def test_report_parsing():
    r = parsing.parse_report({"summary": "Good.", "strengths": ["a"], "weaknesses": ["b"],
                              "practice_plan": [{"focus": "SQL", "action": "Do 5 joins"}, {"focus": "", "action": "dropped"}, "junk"]})
    assert r["practice_plan"] == [{"focus": "SQL", "action": "Do 5 joins"}]


def test_factory_selection():
    assert isinstance(build_provider(Settings()), OfflineProvider)
    assert isinstance(build_provider(Settings(gemini_api_key="k")), GeminiProvider)
    assert isinstance(build_provider(Settings(groq_api_key="k")), GroqProvider)
    assert isinstance(build_provider(Settings(gemini_api_key="k", groq_api_key="k")), GeminiProvider)
    assert isinstance(build_provider(Settings(llm_provider="offline", gemini_api_key="k")), OfflineProvider)
    with pytest.raises(Exception):
        build_provider(Settings(llm_provider="gemini"))
    with pytest.raises(Exception):
        build_provider(Settings(llm_provider="nonsense"))