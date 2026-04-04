"""
Research Agent - Deep research for interview experiences and company info
"""
import os
import re
import asyncio
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from openai import OpenAI

from app.utils.logger import get_logger
from app.utils.llm_logger import llm_call

log = get_logger(__name__)


class ResearchAgent:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        log.debug("Initialising ResearchAgent")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
            return content
        except Exception as exc:
            log.warning("Page scrape failed | url='%s' | error=%s", url, exc)
            return ""

    # ------------------------------------------------------------------
    # Parsing helpers (synchronous)
    # ------------------------------------------------------------------

    def _extract_company_role(self, jd_analysis_text: str) -> tuple[str, str]:
        log.debug("Extracting company and role from JD analysis text")
        company = "Target Company"
        role    = "Software Engineer"

        company_match = re.search(
            r'\*\*Company Name\*\*[:\s]+([^\n*]+)', jd_analysis_text, re.IGNORECASE
        )
        if company_match:
            val = company_match.group(1).strip().strip("*").strip()
            if val and val.lower() not in {
                "not mentioned", "not specified", "n/a", "-", "not provided", ""
            }:
                company = val

        role_match = re.search(
            r'\*\*Role Title\*\*[:\s]+([^\n*]+)', jd_analysis_text, re.IGNORECASE
        )
        if role_match:
            val = role_match.group(1).strip().strip("*").strip()
            if val:
                role = val

        log.info("Extracted from JD | company='%s' | role='%s'", company, role)
        return company, role

    def _extract_skills_from_jd(self, jd_analysis_text: str) -> list[str]:
        log.debug("Extracting required skills from JD analysis text")
        match = re.search(
            r'\*\*Required Skills\*\*[:\s]+(.*?)(?=\n\d+\.|\n\*\*|\Z)',
            jd_analysis_text,
            re.DOTALL | re.IGNORECASE,
        )
        if not match:
            log.warning("Could not find Required Skills section in JD analysis")
            return []

        skills_text = match.group(1)
        raw = re.findall(
            r'[-•*\d.]\s*([A-Za-z][A-Za-z0-9\s+#./]+?)(?:[,\n]|$)', skills_text
        )
        cleaned = [s.strip().strip("*").strip() for s in raw if 2 < len(s.strip()) < 35]

        seen: set[str] = set()
        unique: list[str] = []
        for s in cleaned:
            if s.lower() not in seen:
                seen.add(s.lower())
                unique.append(s)
        skills = unique[:6]

        log.info("Extracted %d skills from JD: %s", len(skills), skills)
        return skills

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

        log.debug("Calling OpenAI gpt-4o-mini to synthesise company research")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.3,
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

        prompt = f"""Analyze this job description and extract:

1. **Company Name**: (if mentioned)
2. **Role Title**:
3. **Experience Level**: (Fresher/1-3 years/3-5 years/5+ years/Senior)
4. **Required Skills**: (list the top 10)
5. **Nice-to-Have Skills**: (list any mentioned)
6. **Key Responsibilities**: (summarize in 5 points)
7. **Interview Focus Areas**: (what they'll likely test based on requirements)

Job Description:
{jd_text[:3000]}

Respond in a structured format."""

        log.debug("Calling OpenAI gpt-4o-mini to extract JD info")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        result = {
            "jd_analysis": response.choices[0].message.content,
            "raw_jd": jd_text[:1000],
            "_tokens": tokens,
        }
        log.info("JD info extracted | analysis_length=%d chars", len(result["jd_analysis"]))
        return result

    async def extract_resume_info(self, resume_text: str) -> dict:
        log.info("Extracting resume info | resume_length=%d chars", len(resume_text))

        prompt = f"""Analyze this resume and extract:

1. **Candidate Name**: (if mentioned)
2. **Experience Level**: (total years)
3. **Current/Latest Role**:
4. **Top Skills**: (list the main technical skills)
5. **Key Projects**: (summarize 2-3 notable projects)
6. **Education**:
7. **Strengths for Interviews**: (what to highlight)
8. **Potential Gaps**: (areas to prepare for tough questions)

Resume:
{resume_text[:3000]}

Respond in a structured format."""

        log.debug("Calling OpenAI gpt-4o-mini to extract resume info")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        result = {
            "resume_analysis": response.choices[0].message.content,
            "raw_resume": resume_text[:1000],
            "_tokens": tokens,
        }
        log.info("Resume info extracted | analysis_length=%d chars", len(result["resume_analysis"]))
        return result

    async def close(self):
        log.debug("Closing ResearchAgent HTTP client")
        await self.http_client.aclose()
