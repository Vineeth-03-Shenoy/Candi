"""
Search providers — pluggable web search for the research pipeline (B.7).

Two backends behind one interface:

  DuckDuckGoProvider — free, no API key. Scrapes DDG's HTML endpoint with
      BeautifulSoup. $0 forever, but brittle if DuckDuckGo changes its markup.

  TavilyProvider — Tavily Search API. 1,000 free credits/month (basic search
      = 1 credit). Clean structured JSON, no scraping fragility.

Only the *search* step differs between providers. Deep-reading specific URLs
afterwards (scrape_page) is shared — plain HTTP + BeautifulSoup either way.

The frontend picks the provider per preparation run (PrepareRequest.search_provider);
when absent, SEARCH_PROVIDER from .env is the default.

Web search activity is logged to:
    backend/Logs/<YYYY>/<Month>/web_search_<YYYY-MM-DD>.jsonl
"""
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


# ------------------------------------------------------------------
# Web search JSONL logger
# ------------------------------------------------------------------

def _web_search_log_path() -> Path:
    """Return path to today's web search JSONL log, creating dirs as needed."""
    now = datetime.now()
    backend_root = Path(__file__).resolve().parents[2]
    log_dir = backend_root / "Logs" / now.strftime("%Y") / now.strftime("%B")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"web_search_{now.strftime('%Y-%m-%d')}.jsonl"


def _log_web_search(entry: dict) -> None:
    """Append a single JSON entry to today's web search JSONL log."""
    try:
        path = _web_search_log_path()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("Failed to write web search log | error=%s", exc)


# ------------------------------------------------------------------
# Provider interface
# ------------------------------------------------------------------

class SearchProvider(ABC):
    """One search interface; swap backends via get_search_provider()."""

    name: str = "abstract"

    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Run a web search. Returns [{"title": ..., "snippet": ..., "url": ...}, ...]."""

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def scrape_page(self, url: str, max_chars: int = 4000) -> str:
        """Fetch and clean a page's main text. Shared by all providers (it's free)."""
        log.debug("Scraping page | url='%s' | max_chars=%d", url, max_chars)
        try:
            if not url.startswith("http"):
                url = "https://" + url

            response = await self._http.get(url)
            log.debug("Page response | status=%d | url='%s'", response.status_code, url)

            ct = response.headers.get("content-type", "")
            if response.status_code != 200 or not ct or "html" not in ct.lower():
                log.info("Skipping non-HTML page | url='%s' | content_type='%s'", url, ct)
                return ""

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            container = (
                soup.select_one("article")
                or soup.select_one(".article-body")
                or soup.select_one("main")
                or soup
            )

            text = container.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 20]
            content = "\n".join(lines)[:max_chars]

            log.info("Scraped page | url='%s' | content_length=%d chars", url, len(content))
            _log_web_search({
                "timestamp": datetime.now().isoformat(),
                "type": "page_scrape",
                "provider": self.name,
                "url": url,
                "content_length": len(content),
                "content_preview": content[:500],
            })
            return content
        except Exception as exc:
            log.warning("Page scrape failed | url='%s' | error=%s", url, exc)
            return ""


# ------------------------------------------------------------------
# DuckDuckGo (free, keyless, HTML scraping)
# ------------------------------------------------------------------

class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        log.debug("DuckDuckGo search | max_results=%d | query='%s'", max_results, query)
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            response = await self._http.get(url)
            log.debug("DuckDuckGo response | status=%d", response.status_code)

            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for el in soup.select(".result")[:max_results]:
                title_el   = el.select_one(".result__a")
                snippet_el = el.select_one(".result__snippet")
                url_el     = el.select_one(".result__url")

                title   = title_el.get_text(strip=True)   if title_el   else ""
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                href    = title_el.get("href", "")         if title_el   else ""
                raw_url = url_el.get_text(strip=True)      if url_el     else href

                if title or snippet:
                    results.append({"title": title, "snippet": snippet, "url": raw_url})

            log.info("DuckDuckGo search returned %d results | query='%s'", len(results), query[:80])
            _log_web_search({
                "timestamp": datetime.now().isoformat(),
                "type": "ddg_search",
                "provider": self.name,
                "query": query,
                "max_results": max_results,
                "results_count": len(results),
                "results": results,
            })
            return results
        except Exception as exc:
            log.warning("DuckDuckGo search failed | query='%s' | error=%s", query[:80], exc)
            return []


# ------------------------------------------------------------------
# Tavily (API key, 1,000 free credits/month)
# ------------------------------------------------------------------

class TavilyProvider(SearchProvider):
    name = "tavily"
    ENDPOINT = "https://api.tavily.com/search"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        log.debug("Tavily search | max_results=%d | query='%s'", max_results, query)
        payload = {
            # Body key is the long-standing contract; the Bearer header is the
            # newer documented style. Sending both keeps every API version happy.
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",   # 1 credit/request ("advanced" costs 2)
            "include_answer": False,
        }
        headers = {"Authorization": f"Bearer {settings.tavily_api_key}"}
        try:
            response = await self._http.post(self.ENDPOINT, json=payload, headers=headers)
            if response.status_code != 200:
                log.warning(
                    "Tavily search failed | status=%d | query='%s' | body=%s",
                    response.status_code, query[:80], response.text[:200],
                )
                return []

            data = response.json()
            results = [
                {
                    "title":   r.get("title", ""),
                    "snippet": r.get("content", ""),
                    "url":     r.get("url", ""),
                }
                for r in data.get("results", [])
            ][:max_results]

            log.info("Tavily search returned %d results | query='%s'", len(results), query[:80])
            _log_web_search({
                "timestamp": datetime.now().isoformat(),
                "type": "tavily_search",
                "provider": self.name,
                "query": query,
                "max_results": max_results,
                "results_count": len(results),
                "results": results,
            })
            return results
        except Exception as exc:
            log.warning("Tavily search failed | query='%s' | error=%s", query[:80], exc)
            return []


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def get_search_provider(name: str | None, http_client: httpx.AsyncClient) -> SearchProvider:
    """
    Build the requested search provider. name=None falls back to the
    SEARCH_PROVIDER env default. Raises ValueError with a user-friendly
    message when the choice isn't usable (unknown name / missing API key).
    """
    provider = (name or settings.search_provider).strip().lower()

    if provider == "duckduckgo":
        log.info("Search provider selected: DuckDuckGo (free)")
        return DuckDuckGoProvider(http_client)

    if provider == "tavily":
        if not settings.tavily_api_key.strip():
            raise ValueError(
                "Tavily was selected but TAVILY_API_KEY is not set. "
                "Add it to .env, or choose DuckDuckGo (free) instead."
            )
        log.info("Search provider selected: Tavily")
        return TavilyProvider(http_client)

    raise ValueError(f"Unknown search provider '{provider}' — expected 'duckduckgo' or 'tavily'.")
