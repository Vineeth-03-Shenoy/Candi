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
from typing import Literal

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# This file: backend/app/config.py  →  parents[2] = repo root (where .env lives)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # tolerate unrelated vars in .env
    )

    # ── LLM Provider ─────────────────────────────────────────────────
    # "openai" uses the OpenAI API (requires openai_api_key).
    # "ollama" points at a local Ollama server via its OpenAI-compatible API
    # (experimental: plain chat works; structured-output extraction does not).
    llm_provider: Literal["openai", "ollama"] = "openai"
    ollama_base_url: str = "http://localhost:11434/v1"

    # ── API Keys ─────────────────────────────────────────────────────
    # Required when llm_provider="openai" (enforced by the validator below,
    # so Ollama-only setups can run key-free).
    openai_api_key: str = ""

    # ── Web Search Provider ──────────────────────────────────────────
    # Used by the prep pipeline's research step. "duckduckgo" is free and
    # keyless; "tavily" needs an API key (1,000 free credits/month).
    # The frontend can override this per preparation run.
    search_provider: Literal["duckduckgo", "tavily"] = "duckduckgo"
    tavily_api_key: str = ""

    # ── Sessions ─────────────────────────────────────────────────────
    # How long a session (chat history + prep data) is kept before startup
    # cleanup deletes it along with its Chroma vector-store collection.
    session_ttl_days: int = 7

    # ── Research Cache (B.9) ─────────────────────────────────────────
    # Web research results (company info, interview experiences, per-skill
    # technical Q&A) are cached in SQLite for this many days. Repeat
    # preparations for the same company or overlapping skillsets become
    # near-instant and cost $0.
    cache_ttl_days: int = 7

    # ── Embeddings (vector store) ────────────────────────────────────
    # "local" uses ChromaDB's free all-MiniLM-L6-v2 ONNX model (default).
    # Set to an OpenAI model name (e.g. "text-embedding-3-small") to use
    # the OpenAI API instead (costs ~$0.00002 per 1K tokens).
    embedding_model: str = "local"

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

    # ── Researcher — resume improvement (NEW) ───────────────────────
    researcher_resume_improve_model: str = "gpt-4o-mini"
    researcher_resume_improve_max_tokens: int = 800
    researcher_resume_improve_temperature: float = 0.4

    # ── Researcher — salary research (NEW) ──────────────────────────
    researcher_salary_model: str = "gpt-4o-mini"
    researcher_salary_max_tokens: int = 500
    researcher_salary_temperature: float = 0.3

    @model_validator(mode="after")
    def _require_openai_key_for_openai_provider(self) -> "Settings":
        if self.llm_provider == "openai" and not self.openai_api_key.strip():
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai "
                "(copy .env.example to .env and set your key)"
            )
        return self


try:
    settings = Settings()
except ValidationError as exc:
    problems = []
    for e in exc.errors():
        field = str(e["loc"][0]).upper() if e["loc"] else "CONFIG"
        problems.append(field if e["type"] == "missing" else f"{field} - {e['msg']}")
    raise SystemExit(
        "\n" + "=" * 64 + "\n"
        " Candi cannot start - invalid configuration:\n   "
        + "\n   ".join(problems)
        + "\n\n See .env.example (repo root) for the full reference.\n"
        + "=" * 64
    ) from exc
