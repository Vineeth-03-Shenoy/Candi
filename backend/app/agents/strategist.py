"""
Strategist Agent - Determines interview rounds and preparation strategy
"""
import os
import re
from openai import AsyncOpenAI

from app.utils.logger import get_logger
from app.utils.llm_logger import llm_call

log = get_logger(__name__)


class StrategistAgent:
    def __init__(self):
        log.debug("Initialising StrategistAgent")
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def identify_rounds(self, jd_analysis: dict, company_research: dict) -> dict:
        company = company_research.get("company_name", "the company")
        role    = company_research.get("role", "the role")
        log.info("Identifying interview rounds | company='%s' | role='%s'", company, role)

        context = (
            f"JD Analysis:\n{jd_analysis.get('jd_analysis', 'Not available')}\n\n"
            f"Company Research:\n{company_research.get('research_summary', 'Not available')}"
        )

        prompt = f"""Based on this information, predict the interview rounds for this position:

{context}

For each round, provide:
1. **Round Name**: (e.g., "Online Assessment", "Technical Round 1")
2. **Type**: (Coding/DSA/System Design/Behavioral/HR)
3. **Duration**: (estimated time)
4. **Format**: (Phone/Video/Onsite/Take-home)
5. **Focus Areas**: (what they'll test)

Return 4-6 likely rounds in order. Be specific to the role and company."""

        model       = os.getenv("STRATEGIST_ROUNDS_MODEL",       "gpt-4o-mini")
        max_tokens  = int(os.getenv("STRATEGIST_ROUNDS_MAX_TOKENS",  "1200"))
        temperature = float(os.getenv("STRATEGIST_ROUNDS_TEMPERATURE", "0.6"))
        log.debug("Calling %s to identify interview rounds", model)
        response, tokens = await llm_call(
            self.client, __name__,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        rounds_text = response.choices[0].message.content
        estimated   = self._count_rounds(rounds_text)

        log.info(
            "Interview rounds identified | estimated_rounds=%d | response_length=%d chars",
            estimated, len(rounds_text),
        )

        return {
            "rounds_breakdown": rounds_text,
            "estimated_rounds": estimated,
            "_tokens": tokens,
        }

    def _count_rounds(self, text: str) -> int:
        matches = re.findall(
            r'(?:Round|Stage|Interview)\s*\d+|^\d+\.', text, re.MULTILINE | re.IGNORECASE
        )
        # Report the actual count found; only fall back to 4 when nothing matched
        count = len(matches) if matches else 4
        log.debug("Round count heuristic | regex_matches=%d | final_count=%d", len(matches), count)
        return count

    async def analyze_role_seniority(
        self, resume_analysis: dict, jd_analysis: dict
    ) -> dict:
        log.info("Analysing role seniority")

        context = (
            f"Resume Analysis:\n{resume_analysis.get('resume_analysis', 'Not available')[:1000]}\n\n"
            f"JD Analysis:\n{jd_analysis.get('jd_analysis', 'Not available')[:1000]}"
        )

        prompt = f"""Analyze the candidate's experience level vs job requirements:

{context}

Determine:
1. **Candidate Level**: (Fresher/Junior/Mid/Senior/Lead)
2. **Role Level**: (Entry/Mid/Senior/Lead/Executive)
3. **Match Assessment**: (Underqualified/Good Match/Overqualified)
4. **Salary Negotiation Advice**: (Should they negotiate? Strategy tips)
5. **Key Talking Points**: (What to emphasize given the gap/match)

Be practical and actionable."""

        model       = os.getenv("STRATEGIST_SENIORITY_MODEL",       "gpt-4o-mini")
        max_tokens  = int(os.getenv("STRATEGIST_SENIORITY_MAX_TOKENS",  "800"))
        temperature = float(os.getenv("STRATEGIST_SENIORITY_TEMPERATURE", "0.5"))
        log.debug("Calling %s for seniority analysis", model)
        response, tokens = await llm_call(
            self.client, __name__,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        analysis_text = response.choices[0].message.content
        is_fresher    = "fresher" in analysis_text.lower()
        log.info("Seniority analysis complete | is_fresher=%s", is_fresher)

        return {
            "seniority_analysis": analysis_text,
            "is_fresher": is_fresher,
            "_tokens": tokens,
        }

    async def generate_preparation_strategy(
        self,
        rounds: dict,
        resume_analysis: dict,
        jd_analysis: dict,
    ) -> dict:
        log.info(
            "Generating preparation strategy | estimated_rounds=%s",
            rounds.get("estimated_rounds"),
        )

        prompt = f"""Create a personalized interview preparation strategy.

Candidate Profile:
{resume_analysis.get('resume_analysis', 'Not available')[:800]}

Job Requirements:
{jd_analysis.get('jd_analysis', 'Not available')[:800]}

Interview Rounds:
{rounds.get('rounds_breakdown', 'Not available')[:800]}

Provide:
1. **Week-by-Week Timeline**: (assuming 2 weeks to prepare)
2. **Priority Topics**: (rank by importance)
3. **Resources**: (what to study)
4. **Daily Practice Plan**: (specific actions)
5. **Confidence Boosters**: (what they're already strong in)

Be specific and actionable for THIS candidate and THIS role."""

        model       = os.getenv("STRATEGIST_STRATEGY_MODEL",       "gpt-4o")
        max_tokens  = int(os.getenv("STRATEGIST_STRATEGY_MAX_TOKENS",  "1500"))
        temperature = float(os.getenv("STRATEGIST_STRATEGY_TEMPERATURE", "0.7"))
        log.debug("Calling %s to generate preparation strategy", model)
        response, tokens = await llm_call(
            self.client, __name__,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        strategy_text = response.choices[0].message.content
        log.info("Preparation strategy generated | strategy_length=%d chars", len(strategy_text))

        return {
            "preparation_strategy": strategy_text,
            "_tokens": tokens,
        }
