"""
Strategist Agent - Determines interview rounds and preparation strategy
"""
import os
from openai import OpenAI


class StrategistAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def identify_rounds(self, jd_analysis: dict, company_research: dict) -> list:
        """
        Predict the likely interview rounds based on company and role.
        """
        context = f"""
JD Analysis:
{jd_analysis.get('jd_analysis', 'Not available')}

Company Research:
{company_research.get('research_summary', 'Not available')}
"""
        
        prompt = f"""Based on this information, predict the interview rounds for this position:

{context}

For each round, provide:
1. **Round Name**: (e.g., "Online Assessment", "Technical Round 1")
2. **Type**: (Coding/DSA/System Design/Behavioral/HR)
3. **Duration**: (estimated time)
4. **Format**: (Phone/Video/Onsite/Take-home)
5. **Focus Areas**: (what they'll test)

Return 4-6 likely rounds in order. Be specific to the role and company."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.6
        )
        
        # Parse the response into structured rounds
        rounds_text = response.choices[0].message.content
        
        return {
            "rounds_breakdown": rounds_text,
            "estimated_rounds": self._count_rounds(rounds_text)
        }
    
    def _count_rounds(self, text: str) -> int:
        """Estimate number of rounds from text."""
        # Simple heuristic - count numbered items
        import re
        matches = re.findall(r'(?:Round|Stage|Interview)\s*\d+|^\d+\.', text, re.MULTILINE | re.IGNORECASE)
        return max(len(matches), 4)  # At least 4 rounds
    
    async def analyze_role_seniority(self, resume_analysis: dict, jd_analysis: dict) -> dict:
        """
        Determine if this is a fresher role or experienced position.
        """
        context = f"""
Resume Analysis:
{resume_analysis.get('resume_analysis', 'Not available')[:1000]}

JD Analysis:
{jd_analysis.get('jd_analysis', 'Not available')[:1000]}
"""
        
        prompt = f"""Analyze the candidate's experience level vs job requirements:

{context}

Determine:
1. **Candidate Level**: (Fresher/Junior/Mid/Senior/Lead)
2. **Role Level**: (Entry/Mid/Senior/Lead/Executive)
3. **Match Assessment**: (Underqualified/Good Match/Overqualified)
4. **Salary Negotiation Advice**: (Should they negotiate? Strategy tips)
5. **Key Talking Points**: (What to emphasize given the gap/match)

Be practical and actionable."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.5
        )
        
        return {
            "seniority_analysis": response.choices[0].message.content,
            "is_fresher": "fresher" in response.choices[0].message.content.lower()
        }
    
    async def generate_preparation_strategy(
        self, 
        rounds: dict, 
        resume_analysis: dict, 
        jd_analysis: dict
    ) -> dict:
        """
        Create a personalized preparation strategy.
        """
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

        response = self.client.chat.completions.create(
            model="gpt-4o",  # Use better model for strategy
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        
        return {
            "preparation_strategy": response.choices[0].message.content
        }
