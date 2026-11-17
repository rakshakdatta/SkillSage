"""A model running on your own machine, through an OpenAI-compatible server.

Works with Ollama (http://127.0.0.1:11434/v1), llama.cpp's `llama-server`
(http://127.0.0.1:8080/v1) and LM Studio. Needs no API key and sends nothing off the machine.
"""
from __future__ import annotations

from urllib.parse import urlparse

import requests

from ..errors import LLMError
from .base import JsonLLMProvider


class LocalProvider(JsonLLMProvider):
    is_ai = True

    def __init__(self, base_url: str, model: str, timeout: int = 120, api_key: str = ""):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("LOCAL_LLM_URL must start with http:// or https://")
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self._api_key = api_key
        self.name = f"Local ({model})"

    def _complete(self, system: str, user: str) -> str:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            resp = requests.post(
                self.endpoint,
                headers=headers,
                json={
                    "model": self.model,
                    "temperature": 0.3,
                    "stream": False,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:  # includes connect timeouts
            raise LLMError("Could not reach the local model server. Is Ollama (or llama.cpp) running?") from exc
        except requests.Timeout as exc:
            raise LLMError("The local model took too long. Try a smaller model or raise LOCAL_LLM_TIMEOUT_SECONDS.") from exc
        except requests.RequestException as exc:
            raise LLMError("Could not reach the local model server. Is Ollama (or llama.cpp) running?") from exc

        if resp.status_code == 404:
            raise LLMError(f"The local server does not have the model '{self.model}'. Pull or load it first.")
        if resp.status_code >= 400:
            raise LLMError(f"The local model server returned an error (HTTP {resp.status_code}).")
        try:
            return resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError("The local model returned no content.") from exc
