"""
Strategist Agent - Determines interview rounds and preparation strategy
"""
import os
import re
from openai import OpenAI

from app.utils.logger import get_logger

log = get_logger(__name__)


class StrategistAgent:
    def __init__(self):
        log.debug("Initialising StrategistAgent")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def identify_rounds(self, jd_analysis: dict, company_research: dict) -> dict:
        """Predict the likely interview rounds based on company and role."""
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

        log.debug("Calling OpenAI gpt-4o-mini to identify interview rounds")
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.6,
        )

        rounds_text = response.choices[0].message.content
        estimated = self._count_rounds(rounds_text)

        log.info(
            "Interview rounds identified | estimated_rounds=%d | response_length=%d chars",
            estimated, len(rounds_text),
        )

        return {
            "rounds_breakdown": rounds_text,
            "estimated_rounds": estimated,
        }

    def _count_rounds(self, text: str) -> int:
        """Estimate number of rounds from text."""
        matches = re.findall(
            r'(?:Round|Stage|Interview)\s*\d+|^\d+\.', text, re.MULTILINE | re.IGNORECASE
        )
        count = max(len(matches), 4)
        log.debug("Round count heuristic | regex_matches=%d | final_count=%d", len(matches), count)
        return count

    async def analyze_role_seniority(
        self, resume_analysis: dict, jd_analysis: dict
    ) -> dict:
        """Determine if this is a fresher role or experienced position."""
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

        log.debug("Calling OpenAI gpt-4o-mini for seniority analysis")
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5,
        )

        analysis_text = response.choices[0].message.content
        is_fresher = "fresher" in analysis_text.lower()
        log.info("Seniority analysis complete | is_fresher=%s", is_fresher)

        return {
            "seniority_analysis": analysis_text,
            "is_fresher": is_fresher,
        }

    async def generate_preparation_strategy(
        self,
        rounds: dict,
        resume_analysis: dict,
        jd_analysis: dict,
    ) -> dict:
        """Create a personalised preparation strategy."""
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

        log.debug("Calling OpenAI gpt-4o to generate preparation strategy")
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7,
        )

        strategy_text = response.choices[0].message.content
        log.info(
            "Preparation strategy generated | strategy_length=%d chars", len(strategy_text)
        )

        return {"preparation_strategy": strategy_text}
