"""
Application configuration — single source of truth.

All settings are validated ONCE at startup by pydantic-settings. Values come
from environment variables or the repo-root .env file (see .env.example for
the full reference). The app refuses to start if OPENAI_API_KEY is missing.

Usage:
    from app.config import settings
    model = settings.researcher_company_model
"""
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# This file: backend/app/config.py  →  parents[2] = repo root (where .env lives)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # tolerate unrelated vars in .env
    )

    # ── API Keys (required — fail-fast) ──────────────────────────────
    openai_api_key: str

    # ── Sessions ─────────────────────────────────────────────────────
    # How long a session (chat history + prep data) is kept before startup
    # cleanup deletes it along with its Chroma vector-store collection.
    session_ttl_days: int = 7

    # ── Router Agent ─────────────────────────────────────────────────
    router_simple_chat_model: str = "gpt-4o-mini"
    router_simple_chat_max_tokens: int = 500
    router_simple_chat_temperature: float = 0.7

    router_quick_qa_model: str = "gpt-4o-mini"
    router_quick_qa_max_tokens: int = 1200
    router_quick_qa_temperature: float = 0.7

    # ── Research Agent ───────────────────────────────────────────────
    researcher_resume_model: str = "gpt-4o-mini"
    researcher_resume_max_tokens: int = 1000
    researcher_resume_temperature: float = 0.3

    researcher_jd_model: str = "gpt-4o-mini"
    researcher_jd_max_tokens: int = 1000
    researcher_jd_temperature: float = 0.3

    researcher_company_model: str = "gpt-4o-mini"
    researcher_company_max_tokens: int = 1200
    researcher_company_temperature: float = 0.3

    # ── Strategist Agent ─────────────────────────────────────────────
    strategist_rounds_model: str = "gpt-4o-mini"
    strategist_rounds_max_tokens: int = 1200
    strategist_rounds_temperature: float = 0.6

    strategist_seniority_model: str = "gpt-4o-mini"
    strategist_seniority_max_tokens: int = 800
    strategist_seniority_temperature: float = 0.5

    strategist_strategy_model: str = "gpt-4o"
    strategist_strategy_max_tokens: int = 1500
    strategist_strategy_temperature: float = 0.7

    # ── Content Gen Agent ────────────────────────────────────────────
    content_round_questions_model: str = "gpt-4o"
    content_round_questions_max_tokens: int = 2000
    content_round_questions_temperature: float = 0.7

    content_all_questions_model: str = "gpt-4o"
    content_all_questions_max_tokens: int = 4000
    content_all_questions_temperature: float = 0.7

    content_behavioral_model: str = "gpt-4o-mini"
    content_behavioral_max_tokens: int = 1500
    content_behavioral_temperature: float = 0.7

    content_technical_model: str = "gpt-4o"
    content_technical_max_tokens: int = 3000
    content_technical_temperature: float = 0.5


try:
    settings = Settings()
except ValidationError as exc:
    missing = [str(e["loc"][0]).upper() for e in exc.errors() if e["type"] == "missing"]
    raise SystemExit(
        "\n" + "=" * 64 + "\n"
        " Candi cannot start - missing required configuration:\n"
        f"   {', '.join(missing)}\n\n"
        " Copy .env.example to .env (repo root) and set your key.\n"
        + "=" * 64
    ) from exc
