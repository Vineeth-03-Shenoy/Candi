"""
LLM client abstraction — single interface, pluggable backends (B.7).

OpenAILLMClient: uses the official OpenAI SDK.
OllamaLLMClient:  uses Ollama's OpenAI-compatible API endpoint.
                  Chat works today; parse() uses JSON schema (experimental).

Agents interact only through `llm_call()` / `llm_parse()` in `llm_logger.py`;
those helpers delegate here. Swapping the provider (OpenAI → Ollama) is a
one-line change in `create_llm_client()`.

Every chat() / parse() call is wrapped with exponential-backoff retries (B.8)
so transient network errors, 429 rate limits, and 5xx server errors don't
fail the whole pipeline — three attempts spaced 1s → 2s → 4s.
"""
import json
from abc import ABC, abstractmethod
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


class LLMClient(ABC):
    """
    One interface for every LLM call in Candi.

    Return contract for all methods:
        (content_or_parsed, token_usage)
        token_usage = {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
    """

    provider_name: str

    @abstractmethod
    async def chat(
        self,
        *,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **opts,
    ) -> tuple[str, dict]:
        """Plain chat completion. Returns (content_text, token_usage)."""

    @abstractmethod
    async def parse(
        self,
        *,
        messages: list[dict],
        response_format: type,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **opts,
    ) -> tuple[Any, dict]:
        """
        Structured output. Returns (parsed_pydantic_model, token_usage).
        The OpenAI implementation uses native `chat.completions.parse()`;
        the Ollama implementation falls back to `create()` with a JSON schema.
        """


class OpenAILLMClient(LLMClient):
    provider_name = "openai"

    def __init__(self, api_key: str):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def chat(self, *, messages, model, temperature=0.7, max_tokens=512, **opts):
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **opts,
        )
        content = response.choices[0].message.content if response.choices else ""
        tokens = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        return content, tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def parse(self, *, messages, response_format, model, temperature=0.7, max_tokens=512, **opts):
        response = await self._client.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=response_format,
            temperature=temperature,
            max_tokens=max_tokens,
            **opts,
        )
        parsed = response.choices[0].message.parsed if response.choices else None
        tokens = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        return parsed, tokens


class OllamaLLMClient(LLMClient):
    provider_name = "ollama"

    def __init__(self, base_url: str):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(base_url=base_url, api_key="ollama")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def chat(self, *, messages, model, temperature=0.7, max_tokens=512, **opts):
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **opts,
        )
        content = response.choices[0].message.content if response.choices else ""
        tokens = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        return content, tokens

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def parse(self, *, messages, response_format, model, temperature=0.7, max_tokens=512, **opts):
        """
        Ollama's OpenAI-compatible API supports JSON schema in response_format.
        We build the schema from the Pydantic model, call create() (not parse()),
        and manually validate the returned JSON string.
        """
        try:
            schema = response_format.model_json_schema()
        except Exception:
            schema = {}

        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": getattr(response_format, "__name__", "response"),
                    "schema": schema,
                    "strict": True,
                },
            },
            **opts,
        )
        raw_content = response.choices[0].message.content if response.choices else "{}"
        try:
            data = json.loads(raw_content)
            parsed = response_format.model_validate(data)
        except Exception:
            log.warning("Ollama parse validation failed | raw=%s", raw_content[:200])
            parsed = None

        tokens = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        return parsed, tokens


from typing import Optional


def create_llm_client(provider: Optional[str] = None) -> LLMClient:
    """Build the configured LLM client. provider overrides the env default."""
    target = (provider or settings.llm_provider).strip().lower()
    if target == "ollama":
        log.info("LLM provider: Ollama | base_url=%s", settings.ollama_base_url)
        return OllamaLLMClient(base_url=settings.ollama_base_url)

    log.debug("LLM provider: OpenAI")
    return OpenAILLMClient(api_key=settings.openai_api_key)
