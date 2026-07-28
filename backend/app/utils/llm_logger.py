"""
LLM Interaction Logger

Wraps every LLM call (chat or structured parse) to capture and persist:
  - Model used
  - Input messages (PII-sanitised; withheld entirely for unmasked calls)
  - Output text (PII-sanitised)
  - Token counts (prompt / completion / total)
  - Time taken
  - Call settings (temperature, max_tokens, etc.)

Log file location:
    backend/Logs/<YYYY>/<MonthName>/llm_interactions_<YYYY-MM-DD>.jsonl

Each line in the file is a self-contained JSON object (JSONL format).
"""
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.llm_client import LLMClient
from app.utils import pii_masker
from app.utils.logger import get_logger

log = get_logger(__name__)


# ------------------------------------------------------------------
# Log helpers
# ------------------------------------------------------------------

def _llm_log_path() -> Path:
    """Return the path to today's JSONL log file, creating directories as needed."""
    now   = datetime.now()
    year  = now.strftime("%Y")
    month = now.strftime("%B")
    date  = now.strftime("%Y-%m-%d")

    # This file: backend/app/utils/llm_logger.py  →  parents[2] = backend/
    backend_root = Path(__file__).resolve().parents[2]
    log_dir = backend_root / "Logs" / year / month
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"llm_interactions_{date}.jsonl"


def _write_llm_log(entry: dict) -> None:
    """Append a single JSON entry to today's JSONL interaction log."""
    try:
        import json
        path = _llm_log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("Failed to write LLM interaction log | error=%s", exc)


def _sanitize_messages(messages: list) -> list:
    """Return a copy of the messages with email/phone PII masked for logging."""
    sanitized = []
    for msg in messages:
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            sanitized.append({**msg, "content": pii_masker.mask_pii(msg["content"])})
        else:
            sanitized.append(msg)
    return sanitized


def _log_interaction(
    module_name: str,
    model: str,
    messages: list,
    settings: dict,
    output_text: str,
    tokens: dict,
    elapsed: float,
    pii_masked: bool,
) -> None:
    """Log a completed LLM interaction to console + JSONL."""
    log.info(
        "LLM call complete | module=%s | model=%s | prompt_tokens=%d | completion_tokens=%d | time=%.3fs",
        module_name, model,
        tokens["prompt_tokens"], tokens["completion_tokens"], elapsed,
    )

    # Never persist raw PII. Unmasked calls have their content withheld
    # entirely; masked calls are still defensively re-sanitised before
    # hitting disk.
    if pii_masked:
        logged_input  = _sanitize_messages(messages)
        logged_output = pii_masker.mask_pii(output_text or "")
    else:
        logged_input  = "[withheld — input contains unmasked PII]"
        logged_output = "[withheld — output may contain unmasked PII]"

    entry = {
        "timestamp":           datetime.now().isoformat(),
        "module":              module_name,
        "model":               model,
        "settings":            settings,
        "pii_masked":          pii_masked,
        "input_messages":      logged_input,
        "output":              logged_output,
        "input_tokens":        tokens["prompt_tokens"],
        "output_tokens":       tokens["completion_tokens"],
        "total_tokens":        tokens["total_tokens"],
        "time_taken_seconds":  elapsed,
    }
    _write_llm_log(entry)


# ------------------------------------------------------------------
# Public wrappers
# ------------------------------------------------------------------

async def llm_call(
    client: LLMClient,
    module_name: str,
    pii_masked: bool = True,
    **kwargs,
) -> tuple[str, dict]:
    """
    Async wrapper around LLMClient.chat().

    Usage:
        content, tokens = await llm_call(self.client, __name__,
                                          model="gpt-4o-mini",
                                          messages=[...],
                                          temperature=0.7,
                                          max_tokens=500)

    Args:
        pii_masked — set False when the input intentionally contains unmasked
                     PII (e.g. the initial resume parse); the JSONL log then
                     withholds the content instead of persisting it.

    Returns:
        content  — the LLM's text response
        tokens   — dict with prompt_tokens, completion_tokens, total_tokens
    """
    model    = kwargs.get("model", "unknown")
    messages = kwargs.get("messages", [])
    settings = {k: v for k, v in kwargs.items() if k not in ("model", "messages")}

    log.debug(
        "LLM call starting | module=%s | model=%s | messages=%d | settings=%s",
        module_name, model, len(messages), settings,
    )

    start    = time.perf_counter()
    content, tokens = await client.chat(**kwargs)
    elapsed  = round(time.perf_counter() - start, 3)

    _log_interaction(module_name, model, messages, settings, content, tokens, elapsed, pii_masked)
    return content, tokens


async def llm_parse(
    client: LLMClient,
    module_name: str,
    response_format: Any,
    pii_masked: bool = True,
    **kwargs,
) -> tuple[Any, dict]:
    """
    Structured Outputs variant — wrapper around LLMClient.parse().

    Usage:
        parsed, tokens = await llm_parse(self.client, __name__,
                                        response_format=JDInfo,
                                        model="gpt-4o-mini",
                                        messages=[...])

    Returns:
        parsed  — the validated Pydantic model instance (or None on failure)
        tokens  — dict with prompt_tokens, completion_tokens, total_tokens
    """
    model    = kwargs.get("model", "unknown")
    messages = kwargs.get("messages", [])
    settings = {k: v for k, v in kwargs.items() if k not in ("model", "messages")}
    settings["response_format"] = getattr(response_format, "__name__", str(response_format))

    log.debug(
        "LLM parse starting | module=%s | model=%s | schema=%s | messages=%d",
        module_name, model, settings["response_format"], len(messages),
    )

    start    = time.perf_counter()
    parsed, tokens = await client.parse(response_format=response_format, **kwargs)
    elapsed  = round(time.perf_counter() - start, 3)

    _log_interaction(
        module_name, model, messages, settings,
        str(parsed) if parsed else "", tokens, elapsed, pii_masked,
    )
    return parsed, tokens
