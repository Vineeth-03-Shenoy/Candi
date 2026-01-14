"""
Content Generator Agent - Generates interview questions and answers
"""
import os
from openai import OpenAI


class ContentGenAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    async def generate_questions_for_round(
        self, 
        round_info: str,
        jd_analysis: dict,
        resume_analysis: dict
    ) -> dict:
        """
        Generate specific questions for a given interview round.
        """
        prompt = f"""Generate interview questions for this round:

Round Details:
{round_info}

Job Requirements:
{jd_analysis.get('jd_analysis', 'Not available')[:800]}

Candidate Background:
{resume_analysis.get('resume_analysis', 'Not available')[:800]}

For each question, provide:
1. **Question**: The actual question
2. **Why They Ask This**: What they're testing
3. **Key Points to Cover**: What a good answer includes
4. **Sample Answer Framework**: Structure for answering
5. **Common Mistakes**: What to avoid

Generate 5-8 questions relevant to this round type."""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7
        )
        
        return {
            "round_questions": response.choices[0].message.content
        }
    
    async def generate_all_questions(
        self,
        rounds: dict,
        jd_analysis: dict,
        resume_analysis: dict
    ) -> list:
        """
        Generate questions for all interview rounds.
        """
        all_questions = []
        rounds_text = rounds.get("rounds_breakdown", "")
        
        # Parse rounds and generate questions for each
        # For now, generate a comprehensive set
        prompt = f"""Generate a complete interview preparation guide with questions and answers.

Interview Rounds:
{rounds_text}

Job Requirements:
{jd_analysis.get('jd_analysis', 'Not available')[:1000]}

Candidate Background:
{resume_analysis.get('resume_analysis', 'Not available')[:1000]}

For EACH round type mentioned, generate 5-7 questions with:
- The question itself
- Expected answer framework
- Tips for answering effectively

Organize by round. Be thorough and specific to this role."""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.7
        )
        
        return {
            "comprehensive_questions": response.choices[0].message.content
        }
    
    async def generate_behavioral_questions(self, resume_analysis: dict) -> dict:
        """
        Generate behavioral questions based on resume experiences.
        """
        prompt = f"""Based on this candidate's background, generate behavioral interview questions:

Candidate Background:
{resume_analysis.get('resume_analysis', 'Not available')}

Generate 8 behavioral questions using the STAR method format:
- Questions should reference their specific experiences
- Include follow-up probes interviewers might ask
- Provide guidance on structuring the answer

Focus on: Leadership, Conflict Resolution, Problem Solving, Teamwork, Failure/Learning."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7
        )
        
        return {
            "behavioral_questions": response.choices[0].message.content
        }
    
    async def generate_technical_deep_dives(
        self, 
        jd_analysis: dict, 
        resume_analysis: dict
    ) -> dict:
        """
        Generate deep technical questions on key skills.
        """
        prompt = f"""Generate deep technical interview questions.

Required Skills from JD:
{jd_analysis.get('jd_analysis', 'Not available')[:800]}

Candidate's Technical Background:
{resume_analysis.get('resume_analysis', 'Not available')[:800]}

For the top 5 required technical skills:
1. Generate 3 progressively harder questions (Basic → Intermediate → Advanced)
2. Include expected answers/key points
3. Add "gotcha" questions they might face
4. Provide study resources for each topic

Be specific and practical."""

        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500,
            temperature=0.6
        )
        
        return {
            "technical_questions": response.choices[0].message.content
        }
