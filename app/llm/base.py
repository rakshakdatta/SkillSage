"""Provider interface and the shared logic for providers that return JSON text."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..errors import LLMAuthError, LLMError, LLMRateLimitError
from ..models import Context, Evaluation, Question
from . import parsing, prompts


class LLMProvider(ABC):
    name = "provider"
    is_ai = True

    @abstractmethod
    def first_question(self, ctx: Context) -> Question: ...

    @abstractmethod
    def review_answer(self, ctx: Context, question: Question, answer: str, want_next: bool) -> tuple[Evaluation, Question | None]: ...

    @abstractmethod
    def final_report(self, ctx: Context) -> dict: ...


class JsonLLMProvider(LLMProvider):
    """Base for hosted models: subclasses only implement `_complete(system, user) -> str`."""

    attempts = 2  # one retry when the model returns unusable JSON

    @abstractmethod
    def _complete(self, system: str, user: str) -> str: ...

    def _ask(self, user: str, parse):
        last: LLMError | None = None
        for _ in range(self.attempts):
            try:
                return parse(parsing.extract_json(self._complete(prompts.SYSTEM, user)))
            except (LLMAuthError, LLMRateLimitError):
                raise                      # retrying will not help
            except LLMError as exc:
                last = exc                 # bad JSON / empty answer: try once more
        raise last or LLMError("The model could not produce a usable answer.")

    def first_question(self, ctx: Context) -> Question:
        return self._ask(prompts.first_question_prompt(ctx), parsing.parse_question)

    def review_answer(self, ctx, question, answer, want_next):
        def parse(data):
            evaluation = parsing.parse_evaluation(data)
            nxt = parsing.parse_question(data.get("next_question")) if want_next else None
            return evaluation, nxt
        return self._ask(prompts.review_prompt(ctx, question.text, answer, want_next), parse)

    def final_report(self, ctx: Context) -> dict:
        return self._ask(prompts.report_prompt(ctx), parsing.parse_report)