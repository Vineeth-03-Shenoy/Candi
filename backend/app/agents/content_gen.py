"""
Content Generator Agent - Generates interview questions and answers
grounded in real company research and technical Q&A from trusted sources.
"""
import os
from openai import OpenAI

from app.utils.logger import get_logger
from app.utils.llm_logger import llm_call

log = get_logger(__name__)


def _sum_tokens(*token_dicts: dict) -> dict:
    """Merge multiple token-count dicts into one cumulative total."""
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for t in token_dicts:
        if t:
            total["prompt_tokens"]     += t.get("prompt_tokens", 0)
            total["completion_tokens"] += t.get("completion_tokens", 0)
            total["total_tokens"]      += t.get("total_tokens", 0)
    return total


class ContentGenAgent:
    def __init__(self):
        log.debug("Initialising ContentGenAgent")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _company_research_context(
        self,
        company_research: dict | None,
        interview_experiences: list[dict] | None,
    ) -> str:
        parts: list[str] = []

        if company_research and company_research.get("research_summary"):
            parts.append(
                "Company Research (web-sourced):\n"
                + company_research["research_summary"][:800]
            )
            log.debug("Research context: company research included (%d chars)",
                      len(company_research["research_summary"][:800]))

        if interview_experiences:
            exp_lines: list[str] = []
            for exp in interview_experiences[:3]:
                source  = exp.get("source", "Unknown")
                content = exp.get("content", "")[:600]
                if content:
                    exp_lines.append(f"[{source}]: {content}")
            if exp_lines:
                parts.append("Real Interview Experiences:\n" + "\n\n".join(exp_lines))
                log.debug("Research context: %d interview experience entries included", len(exp_lines))

        return ("\n\n" + "\n\n".join(parts)) if parts else ""

    def _technical_qa_context(self, technical_qa: dict[str, str] | None) -> str:
        if not technical_qa:
            log.debug("No technical Q&A context available")
            return ""
        lines: list[str] = []
        for skill, content in list(technical_qa.items())[:4]:
            lines.append(
                f"### {skill} (sourced from GeeksforGeeks / InterviewBit):\n{content[:1200]}"
            )
        log.debug("Technical Q&A context built for %d skills", len(lines))
        return "\n\n" + "\n\n".join(lines) if lines else ""

    # ------------------------------------------------------------------
    # Public generation methods
    # ------------------------------------------------------------------

    async def generate_questions_for_round(
        self,
        round_info: str,
        jd_analysis: dict,
        resume_analysis: dict,
        company_research: dict | None = None,
        interview_experiences: list[dict] | None = None,
    ) -> dict:
        log.info(
            "Generating questions for round | has_research=%s | has_experiences=%s",
            bool(company_research), bool(interview_experiences),
        )

        research_ctx = self._company_research_context(company_research, interview_experiences)

        prompt = f"""Generate interview questions for this round:

Round Details:
{round_info}

Job Requirements:
{jd_analysis.get('jd_analysis', 'Not available')[:800]}

Candidate Background:
{resume_analysis.get('resume_analysis', 'Not available')[:800]}
{research_ctx}

For each question, provide:
1. **Question**: The actual question (prioritise questions reported at this company)
2. **Why They Ask This**: What they're testing
3. **Key Points to Cover**: What a good answer includes
4. **Sample Answer Framework**: Structure for answering
5. **Common Mistakes**: What to avoid

Generate 5-8 questions relevant to this round type."""

        log.debug("Calling OpenAI gpt-4o for round question generation")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )

        result = response.choices[0].message.content
        log.info("Round questions generated | length=%d chars", len(result))
        return {"round_questions": result, "_tokens": tokens}

    async def generate_all_questions(
        self,
        rounds: dict,
        jd_analysis: dict,
        resume_analysis: dict,
        company_research: dict | None = None,
        interview_experiences: list[dict] | None = None,
    ) -> dict:
        log.info(
            "Generating all questions | rounds=%s | has_research=%s | has_experiences=%s",
            rounds.get("estimated_rounds"), bool(company_research), bool(interview_experiences),
        )

        rounds_text  = rounds.get("rounds_breakdown", "")
        research_ctx = self._company_research_context(company_research, interview_experiences)

        prompt = f"""Generate a complete interview preparation guide with questions and answers.

Interview Rounds:
{rounds_text}

Job Requirements:
{jd_analysis.get('jd_analysis', 'Not available')[:1000]}

Candidate Background:
{resume_analysis.get('resume_analysis', 'Not available')[:1000]}
{research_ctx}

Instructions:
- For EACH round type mentioned, generate 5-7 questions.
- Prioritise questions that have been actually reported at this company (use the research data above).
- For every question provide: the question, expected answer framework, and tips for answering.
- Organise clearly by round.
- Be thorough and specific to this role and company."""

        log.debug("Calling OpenAI gpt-4o for comprehensive question generation")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.7,
        )

        result = response.choices[0].message.content
        log.info("All questions generated | length=%d chars", len(result))
        return {"comprehensive_questions": result, "_tokens": tokens}

    async def generate_behavioral_questions(
        self,
        resume_analysis: dict,
        interview_experiences: list[dict] | None = None,
        company_research: dict | None = None,
    ) -> dict:
        log.info(
            "Generating behavioral questions | has_research=%s | has_experiences=%s",
            bool(company_research), bool(interview_experiences),
        )

        research_ctx = self._company_research_context(company_research, interview_experiences)

        prompt = f"""Based on this candidate's background and company research, generate behavioral interview questions.

Candidate Background:
{resume_analysis.get('resume_analysis', 'Not available')}
{research_ctx}

Generate 8 behavioral questions using the STAR method:
- Reference the candidate's specific experiences where possible.
- Align questions with this company's known culture and values (use research data above).
- Include follow-up probes interviewers might ask.
- Provide guidance on structuring the answer.

Focus on: Leadership, Conflict Resolution, Problem Solving, Teamwork, Failure/Learning."""

        log.debug("Calling OpenAI gpt-4o-mini for behavioral question generation")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7,
        )

        result = response.choices[0].message.content
        log.info("Behavioral questions generated | length=%d chars", len(result))
        return {"behavioral_questions": result, "_tokens": tokens}

    async def generate_technical_deep_dives(
        self,
        jd_analysis: dict,
        resume_analysis: dict,
        technical_qa: dict[str, str] | None = None,
    ) -> dict:
        log.info(
            "Generating technical deep dives | skills_with_data=%d",
            len(technical_qa) if technical_qa else 0,
        )

        tech_ctx = self._technical_qa_context(technical_qa)

        prompt = f"""Generate deep technical interview questions with accurate, complete answers.

Required Skills from JD:
{jd_analysis.get('jd_analysis', 'Not available')[:800]}

Candidate's Technical Background:
{resume_analysis.get('resume_analysis', 'Not available')[:800]}
{tech_ctx}

Instructions:
- For the top 5 required technical skills, generate 3 progressively harder questions
  (Basic → Intermediate → Advanced).
- Base your answers on the sourced Q&A data above wherever available — do NOT fabricate
  technical details. If the sourced data covers a concept, use it directly.
- Include accurate, complete answers with code snippets or examples where relevant.
- Add 1 "gotcha" question per skill that interviewers commonly use to trip candidates.
- Be technically precise."""

        log.debug("Calling OpenAI gpt-4o for technical deep dive generation")
        response, tokens = llm_call(
            self.client, __name__,
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.5,
        )

        result = response.choices[0].message.content
        log.info("Technical deep dives generated | length=%d chars", len(result))
        return {"technical_questions": result, "_tokens": tokens}
