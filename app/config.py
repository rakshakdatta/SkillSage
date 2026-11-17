"""Application settings, read from environment variables (optionally a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "auto"          # auto | gemini | groq | offline
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout: int = 45
    local_llm_url: str = "http://127.0.0.1:11434/v1"   # Ollama; llama.cpp is usually http://127.0.0.1:8080/v1
    local_llm_model: str = ""                         # e.g. gemma2:2b, llama3.2:3b, llama3.1:8b
    local_llm_timeout: int = 180                      # small CPU-only models can be slow
    port: int = 5055

    # accounts and history
    database_url: str = ""              # empty = a SQLite file in ./instance
    secret_key: str = ""                # empty = generated once and kept in ./instance/.secret_key
    cookie_secure: bool = False         # set true when served over HTTPS
    auth_rate_limit: int = 10           # sign-in / sign-up attempts per 5 minutes per visitor

    max_answer_chars: int = 4000
    max_resume_chars: int = 12000
    max_upload_bytes: int = 5 * 1024 * 1024
    max_pdf_pages: int = 10

    session_ttl_minutes: int = 180
    max_sessions: int = 500
    rate_limit_per_minute: int = 40

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "auto").strip().lower() or "auto",
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash",
            groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
            groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile",
            llm_timeout=_int("LLM_TIMEOUT_SECONDS", 45),
            local_llm_url=os.getenv("LOCAL_LLM_URL", "").strip() or "http://127.0.0.1:11434/v1",
            local_llm_model=os.getenv("LOCAL_LLM_MODEL", "").strip(),
            local_llm_timeout=_int("LOCAL_LLM_TIMEOUT_SECONDS", 180),
            port=_int("PORT", 5055),
            database_url=os.getenv("DATABASE_URL", "").strip(),
            secret_key=os.getenv("SECRET_KEY", "").strip(),
            cookie_secure=_bool("COOKIE_SECURE"),
            auth_rate_limit=_int("AUTH_RATE_LIMIT", 10),
            rate_limit_per_minute=_int("RATE_LIMIT_PER_MINUTE", 40),
        )