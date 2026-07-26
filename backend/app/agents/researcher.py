"""
Research Agent - Deep research for interview experiences and company info
"""
import json
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from openai import AsyncOpenAI

from app.config import settings
from app.models.schemas import JDInfo, ResumeInfo
from app.utils.logger import get_logger
from app.utils.llm_logger import llm_call, llm_parse

log = get_logger(__name__)


# ------------------------------------------------------------------
# Web search logger
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


class ResearchAgent:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        log.debug("Initialising ResearchAgent")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.http_client = httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT},
        )

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    async def _search_duckduckgo(self, query: str, max_results: int = 5) -> list[dict]:
        log.debug("DuckDuckGo search | max_results=%d | query='%s'", max_results, query)
        try:
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
            response = await self.http_client.get(url)
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
                "query": query,
                "max_results": max_results,
                "results_count": len(results),
                "results": results,
            })
            return results
        except Exception as exc:
            log.warning("DuckDuckGo search failed | query='%s' | error=%s", query[:80], exc)
            return []

    async def _scrape_page(self, url: str, max_chars: int = 4000) -> str:
        log.debug("Scraping page | url='%s' | max_chars=%d", url, max_chars)
        try:
            if not url.startswith("http"):
                url = "https://" + url

            response = await self.http_client.get(url)
            log.debug("Page response | status=%d | url='%s'", response.status_code, url)

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
                "url": url,
                "content_length": len(content),
                "content_preview": content[:500],
            })
            return content
        except Exception as exc:
            log.warning("Page scrape failed | url='%s' | error=%s", url, exc)
            return ""

    # ------------------------------------------------------------------
    # Structured extraction renderers
    # ------------------------------------------------------------------
    # These render structured LLM output back into the markdown format that
    # downstream consumers (prompts, PDF generator, vector-store section
    # chunking) already expect. No regex parsing of LLM text anywhere.

    @staticmethod
    def _render_jd_analysis(info: JDInfo) -> str:
        resp  = "\n".join(f"- {r}" for r in info.key_responsibilities) or "- Not specified"
        focus = "\n".join(f"- {f}" for f in info.interview_focus_areas) or "- Not specified"
        return (
            f"1. **Company Name**: {info.company_name or 'Not mentioned'}\n"
            f"2. **Role Title**: {info.role_title or 'Not mentioned'}\n"
            f"3. **Experience Level**: {info.experience_level or 'Not specified'}\n"
            f"4. **Required Skills**: {', '.join(info.required_skills) or 'Not specified'}\n"
            f"5. **Nice-to-Have Skills**: {', '.join(info.nice_to_have_skills) or 'Not mentioned'}\n"
            f"6. **Key Responsibilities**:\n{resp}\n"
            f"7. **Interview Focus Areas**:\n{focus}"
        )

    @staticmethod
    def _render_resume_analysis(info: ResumeInfo) -> str:
        projects   = "\n".join(f"- {p}" for p in info.key_projects) or "- Not specified"
        strengths  = "\n".join(f"- {s}" for s in info.strengths_for_interviews) or "- Not specified"
        gaps       = "\n".join(f"- {g}" for g in info.potential_gaps) or "- Not specified"
        return (
            f"1. **Candidate Name**: {info.candidate_name or 'Not mentioned'}\n"
            f"2. **Experience Level**: {info.experience_level or 'Not specified'}\n"
            f"3. **Current/Latest Role**: {info.current_role or 'Not mentioned'}\n"
            f"4. **Top Skills**: {', '.join(info.top_skills) or 'Not specified'}\n"
            f"5. **Key Projects**:\n{projects}\n"
            f"6. **Education**: {info.education or 'Not mentioned'}\n"
            f"7. **Strengths for Interviews**:\n{strengths}\n"
            f"8. **Potential Gaps**:\n{gaps}"
        )

    # ------------------------------------------------------------------
    # Web research
    # ------------------------------------------------------------------

    async def research_company(self, company_name: str, role: str) -> dict:
        log.info("Starting company research | company='%s' | role='%s'", company_name, role)

        search1, search2 = await asyncio.gather(
            self._search_duckduckgo(
                f"{company_name} {role} interview process rounds 2024", max_results=4
            ),
            self._search_duckduckgo(
                f'"{company_name}" {role} interview questions asked experience', max_results=3
            ),
        )
        all_results = search1 + search2
        log.info("Company research DDG searches complete | total_results=%d", len(all_results))

        snippets = [
            f"[{r.get('url', 'Web')}] {r['title']}: {r['snippet']}"
            for r in all_results if r.get("snippet")
        ]

        urls_to_scrape = [
            r["url"] for r in all_results[:3]
            if r.get("url") and r["url"].startswith("http")
        ][:2]

        page_contents: list[str] = []
        if urls_to_scrape:
            page_contents = await asyncio.gather(
                *[self._scrape_page(u, max_chars=2500) for u in urls_to_scrape]
            )

        scraped_sections = list(snippets)
        for i, content in enumerate(page_contents):
            if content:
                scraped_sections.append(f"[Scraped – {urls_to_scrape[i]}]:\n{content}")

        web_context = "\n\n".join(scraped_sections) if scraped_sections else "No web data retrieved."
        log.info(
            "Company research web context assembled | sections=%d | total_chars=%d",
            len(scraped_sections), len(web_context),
        )

        prompt = f"""You are a career researcher. Synthesize the web-sourced data below about interviewing at {company_name} for a {role} position.

Web Research Data:
{web_context[:5000]}

Based on this data (supplement gaps with general patterns for this type of company and role), provide:
1. **Company Overview**: Culture and work environment
2. **Interview Process**: Actual number of rounds and their types
3. **Commonly Tested Topics**: Technical and behavioural areas they focus on
4. **Question Patterns**: Types of questions frequently asked
5. **Candidate Tips**: Practical advice from real experiences

Clearly note if specific data was limited."""

        model       = settings.researcher_company_model
        max_tokens  = settings.researcher_company_max_tokens
        temperature = settings.researcher_company_temperature
        log.debug("Calling %s to synthesise company research", model)
        response, tokens = await llm_call(
            self.client, __name__,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        summary = response.choices[0].message.content
        log.info(
            "Company research complete | company='%s' | summary_length=%d chars | sources=%d",
            company_name, len(summary), len([r for r in all_results if r.get("url")]),
        )

        return {
            "company_name": company_name,
            "role": role,
            "research_summary": summary,
            "sources": [r.get("url", "") for r in all_results if r.get("url")],
            "_tokens": tokens,
        }

    async def search_interview_experiences(self, company_name: str, role: str) -> list[dict]:
        log.info("Searching for interview experiences | company='%s' | role='%s'", company_name, role)

        gfg_results, general_results = await asyncio.gather(
            self._search_duckduckgo(
                f"{company_name} interview experience {role} site:geeksforgeeks.org",
                max_results=3,
            ),
            self._search_duckduckgo(
                f"{company_name} {role} interview experience questions asked",
                max_results=4,
            ),
        )
        log.info(
            "Interview experience searches complete | gfg_results=%d | general_results=%d",
            len(gfg_results), len(general_results),
        )

        experiences: list[dict] = []

        gfg_urls = [
            r["url"] for r in gfg_results[:2]
            if r.get("url") and "geeksforgeeks.org" in r["url"]
        ]

        if gfg_urls:
            contents = await asyncio.gather(
                *[self._scrape_page(u, max_chars=3000) for u in gfg_urls]
            )
            for url, content in zip(gfg_urls, contents):
                if content and len(content) > 200:
                    log.info("GFG interview experience scraped | url='%s' | length=%d", url, len(content))
                    experiences.append({"source": "GeeksforGeeks", "url": url, "content": content})

        snippets = [
            f"- {r['title']}: {r['snippet']}"
            for r in general_results if r.get("snippet")
        ]
        if snippets:
            experiences.append({"source": "Web Search", "content": "\n".join(snippets[:6])})

        if not experiences:
            log.warning(
                "No interview experience data found for '%s %s' — using fallback",
                company_name, role,
            )
            experiences.append({
                "source": "Limited Data",
                "content": (
                    f"Limited interview experience data found for {company_name} {role}. "
                    "Questions generated based on role requirements and industry patterns."
                ),
            })

        log.info("Interview experience search complete | sources=%d", len(experiences))
        return experiences

    async def fetch_technical_qa(self, skills: list[str], role: str) -> dict[str, str]:
        if not skills:
            log.info("fetch_technical_qa called with no skills — skipping")
            return {}

        log.info("Fetching technical Q&A | role='%s' | skills=%s", role, skills)

        async def _fetch_one(skill: str) -> tuple[str, str]:
            log.debug("Fetching Q&A for skill='%s'", skill)
            results = await self._search_duckduckgo(
                f"{skill} interview questions and answers "
                f"site:geeksforgeeks.org OR site:interviewbit.com",
                max_results=2,
            )
            for r in results:
                url = r.get("url", "")
                if url and ("geeksforgeeks.org" in url or "interviewbit.com" in url):
                    content = await self._scrape_page(url, max_chars=4000)
                    if content and len(content) > 300:
                        log.info("Technical Q&A fetched | skill='%s' | length=%d chars", skill, len(content))
                        return skill, content
            fallback = "\n".join(r.get("snippet", "") for r in results if r.get("snippet"))
            log.warning("No trusted source found for skill='%s' — using snippet fallback", skill)
            return skill, fallback

        pairs = await asyncio.gather(*[_fetch_one(s) for s in skills[:5]])
        technical_qa = {skill: content for skill, content in pairs if content}

        log.info(
            "Technical Q&A fetch complete | skills_with_data=%d / %d",
            len(technical_qa), len(skills[:5]),
        )
        return technical_qa

    # ------------------------------------------------------------------
    # Resume / JD analysis
    # ------------------------------------------------------------------

    async def extract_jd_info(self, jd_text: str) -> dict:
        log.info("Extracting JD info | jd_length=%d chars", len(jd_text))

        prompt = f"""Extract the structured fields from this job description.
Use "" for unknown strings and [] for unknown lists — never invent data.

Job Description:
{jd_text[:3000]}"""

        model       = settings.researcher_jd_model
        max_tokens  = settings.researcher_jd_max_tokens
        temperature = settings.researcher_jd_temperature
        log.debug("Calling %s to extract JD info (structured)", model)
        response, tokens = await llm_parse(
            self.client, __name__,
            response_format=JDInfo,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        info = response.choices[0].message.parsed or JDInfo(
            company_name="", role_title="", experience_level="",
            required_skills=[], nice_to_have_skills=[],
            key_responsibilities=[], interview_focus_areas=[],
        )
        log.info(
            "JD info extracted | company='%s' | role='%s' | skills=%d",
            info.company_name, info.role_title, len(info.required_skills),
        )

        return {
            "jd_analysis": self._render_jd_analysis(info),
            "jd_info":     info,
            "raw_jd":      jd_text[:1000],
            "_tokens":     tokens,
        }

    async def extract_resume_info(self, resume_text: str) -> dict:
        log.info("Extracting resume info | resume_length=%d chars", len(resume_text))

        prompt = f"""Extract the structured fields from this resume.
Use "" for unknown strings and [] for unknown lists — never invent data.

Resume:
{resume_text[:3000]}"""

        model       = settings.researcher_resume_model
        max_tokens  = settings.researcher_resume_max_tokens
        temperature = settings.researcher_resume_temperature
        log.debug("Calling %s to extract resume info (structured)", model)
        # This call intentionally receives the full unmasked resume (needed to
        # extract the candidate name) — withhold it from the JSONL log.
        response, tokens = await llm_parse(
            self.client, __name__,
            response_format=ResumeInfo,
            pii_masked=False,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        info = response.choices[0].message.parsed or ResumeInfo(
            candidate_name="", experience_level="", current_role="",
            top_skills=[], key_projects=[], education="",
            strengths_for_interviews=[], potential_gaps=[],
        )
        log.info(
            "Resume info extracted | name_found=%s | top_skills=%d",
            bool(info.candidate_name), len(info.top_skills),
        )

        return {
            "resume_analysis": self._render_resume_analysis(info),
            "resume_info":     info,
            "raw_resume":      resume_text[:1000],
            "_tokens":         tokens,
        }

    async def close(self):
        log.debug("Closing ResearchAgent HTTP client")
        await self.http_client.aclose()
