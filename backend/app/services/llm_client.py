"""
LLM client factory — single place that decides which LLM backend agents use.

Today: OpenAI (default). Later: Ollama via its OpenAI-compatible API — flip
LLM_PROVIDER=ollama in .env and every agent talks to the local server instead
(free, offline; note structured-output extraction via llm_parse is OpenAI-only).

All agents construct their client through create_llm_client() so the switch
lives here and nowhere else.
"""
from openai import AsyncOpenAI

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


def create_llm_client() -> AsyncOpenAI:
    """Return an async chat-completions client for the configured provider."""
    if settings.llm_provider == "ollama":
        log.info("LLM provider: Ollama | base_url=%s", settings.ollama_base_url)
        return AsyncOpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",  # Ollama ignores the key; the SDK requires one
        )

    log.debug("LLM provider: OpenAI")
    return AsyncOpenAI(api_key=settings.openai_api_key)
