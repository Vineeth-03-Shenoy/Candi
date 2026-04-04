"""
LLM Interaction Logger

Wraps every OpenAI API call to capture and persist:
  - Model used
  - Full input messages
  - Full output text
  - Token counts (prompt / completion / total)
  - Time taken
  - Call settings (temperature, max_tokens, etc.)

Log file location:
    backend/Logs/<YYYY>/<MonthName>/llm_interactions_<YYYY-MM-DD>.jsonl

Each line in the file is a self-contained JSON object (JSONL format).
"""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

log = get_logger(__name__)


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
        path = _llm_log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("Failed to write LLM interaction log | error=%s", exc)


def llm_call(client: Any, module_name: str, **kwargs) -> tuple[Any, dict]:
    """
    Drop-in replacement for client.chat.completions.create().

    Usage:
        response, tokens = llm_call(self.client, __name__,
                                    model="gpt-4o-mini",
                                    messages=[...],
                                    temperature=0.7,
                                    max_tokens=500)

    Returns:
        response   — the raw OpenAI response object
        tokens     — dict with prompt_tokens, completion_tokens, total_tokens
    """
    model    = kwargs.get("model", "unknown")
    messages = kwargs.get("messages", [])
    settings = {k: v for k, v in kwargs.items() if k not in ("model", "messages")}

    log.debug(
        "LLM call starting | module=%s | model=%s | messages=%d | settings=%s",
        module_name, model, len(messages), settings,
    )

    start    = time.perf_counter()
    response = client.chat.completions.create(**kwargs)
    elapsed  = round(time.perf_counter() - start, 3)

    usage = response.usage
    tokens = {
        "prompt_tokens":     usage.prompt_tokens     if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens":      usage.total_tokens      if usage else 0,
    }

    output_text = response.choices[0].message.content if response.choices else ""

    log.info(
        "LLM call complete | module=%s | model=%s | prompt_tokens=%d | completion_tokens=%d | time=%.3fs",
        module_name, model,
        tokens["prompt_tokens"], tokens["completion_tokens"], elapsed,
    )

    entry = {
        "timestamp":           datetime.now().isoformat(),
        "module":              module_name,
        "model":               model,
        "settings":            settings,
        "input_messages":      messages,
        "output":              output_text,
        "input_tokens":        tokens["prompt_tokens"],
        "output_tokens":       tokens["completion_tokens"],
        "total_tokens":        tokens["total_tokens"],
        "time_taken_seconds":  elapsed,
    }
    _write_llm_log(entry)

    return response, tokens
