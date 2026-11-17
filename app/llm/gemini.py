"""Google Gemini (free tier) over its REST API. No SDK needed."""
from __future__ import annotations

import requests

from ..errors import LLMAuthError, LLMError, LLMRateLimitError
from .base import JsonLLMProvider

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider(JsonLLMProvider):
    is_ai = True

    def __init__(self, api_key: str, model: str, timeout: int = 45):
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.name = f"Gemini ({model})"

    def _complete(self, system: str, user: str) -> str:
        try:
            resp = requests.post(
                ENDPOINT.format(model=self.model),
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
                },
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise LLMError("The AI service took too long to respond. Please try again.") from exc
        except requests.RequestException as exc:
            raise LLMError("Could not reach the AI service.") from exc

        if resp.status_code == 429:
            raise LLMRateLimitError("The free AI quota was reached. Wait a minute and try again.")
        if resp.status_code in (401, 403) or (resp.status_code == 400 and "API key" in resp.text):
            raise LLMAuthError("The AI service rejected the server's API key. Check GEMINI_API_KEY.")
        if resp.status_code >= 400:
            raise LLMError(f"The AI service returned an error (HTTP {resp.status_code}).")

        try:
            parts = resp.json()["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("The AI service returned no content (the request may have been blocked).") from exc