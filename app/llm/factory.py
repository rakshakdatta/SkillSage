"""Choose the provider from settings.

A hosted model (Gemini or Groq) is the main choice. If LOCAL_LLM_MODEL is also set, that local model
becomes the backup that takes over when the hosted one fails or its free quota runs out.
"""
from __future__ import annotations

from ..config import Settings
from ..errors import ApiError
from .base import LLMProvider
from .fallback import FallbackProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .local import LocalProvider
from .offline import OfflineProvider


def _gemini(s: Settings) -> LLMProvider:
    return GeminiProvider(s.gemini_api_key, s.gemini_model, s.llm_timeout)


def _groq(s: Settings) -> LLMProvider:
    return GroqProvider(s.groq_api_key, s.groq_model, s.llm_timeout)


def _local(s: Settings) -> LLMProvider:
    if not s.local_llm_model:
        raise ApiError("LLM_PROVIDER=local but LOCAL_LLM_MODEL is not set (for example gemma2:2b).", 500)
    try:
        return LocalProvider(s.local_llm_url, s.local_llm_model, max(s.llm_timeout, s.local_llm_timeout))
    except ValueError as exc:
        raise ApiError(str(exc), 500) from exc


def _with_backup(main: LLMProvider, s: Settings) -> LLMProvider:
    return FallbackProvider(main, _local(s)) if s.local_llm_model else main


def build_provider(settings: Settings) -> LLMProvider:
    choice = settings.llm_provider
    if choice == "gemini":
        if not settings.gemini_api_key:
            raise ApiError("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set.", 500)
        return _with_backup(_gemini(settings), settings)
    if choice == "groq":
        if not settings.groq_api_key:
            raise ApiError("LLM_PROVIDER=groq but GROQ_API_KEY is not set.", 500)
        return _with_backup(_groq(settings), settings)
    if choice == "local":
        return _local(settings)
    if choice == "offline":
        return OfflineProvider()
    if choice == "auto":
        if settings.gemini_api_key:
            return _with_backup(_gemini(settings), settings)
        if settings.groq_api_key:
            return _with_backup(_groq(settings), settings)
        if settings.local_llm_model:  # only when you chose a model on purpose; nothing is probed
            return _local(settings)
        return OfflineProvider()
    raise ApiError(f"Unknown LLM_PROVIDER '{choice}'. Use auto, gemini, groq, local or offline.", 500)
