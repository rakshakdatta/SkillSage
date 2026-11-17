"""Groq (free tier) through its OpenAI-compatible endpoint."""
from __future__ import annotations

import requests

from ..errors import LLMAuthError, LLMError, LLMRateLimitError
from .base import JsonLLMProvider

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(JsonLLMProvider):
    is_ai = True

    def __init__(self, api_key: str, model: str, timeout: int = 45):
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = f"Groq ({model})"

    def _complete(self, system: str, user: str) -> str:
        try:
            resp = requests.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise LLMError("The AI service took too long to respond. Please try again.") from exc
        except requests.RequestException as exc:
            raise LLMError("Could not reach the AI service.") from exc

        if resp.status_code == 429:
            raise LLMRateLimitError("The free AI quota was reached. Wait a minute and try again.")
        if resp.status_code in (401, 403):
            raise LLMAuthError("The AI service rejected the server's API key. Check GROQ_API_KEY.")
        if resp.status_code >= 400:
            raise LLMError(f"The AI service returned an error (HTTP {resp.status_code}).")

        try:
            return resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("The AI service returned no content.") from exc