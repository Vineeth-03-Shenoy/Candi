"""
Research Agent - Deep research for interview experiences and company info

Searches various sources for:
- Interview experiences (GeeksforGeeks, Glassdoor patterns)
- Company culture and values
- Role-specific requirements
"""
import os
import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
from typing import Optional


class ResearchAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def research_company(self, company_name: str, role: str) -> dict:
        """
        Research company interview patterns and culture.
        
        For now, uses LLM knowledge. Can be extended with web scraping.
        """
        prompt = f"""You are an expert career researcher. Provide detailed information about interviewing at {company_name} for a {role} position.

Include:
1. **Company Overview**: Brief description and culture
2. **Interview Process**: Typical number of rounds and types
3. **Common Topics**: What they usually focus on
4. **Tips**: Specific advice for this company

Be specific and actionable. If you don't have specific info about this company, provide general industry patterns."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.7
        )
        
        return {
            "company_name": company_name,
            "role": role,
            "research_summary": response.choices[0].message.content
        }
    
    async def search_interview_experiences(self, company_name: str, role: str) -> list:
        """
        Search for interview experiences.
        
        In production, this could scrape GeeksforGeeks, Glassdoor, etc.
        For now, generates synthetic experiences using LLM.
        """
        prompt = f"""Generate 3 realistic interview experience summaries for {role} position at {company_name} or similar companies.

For each experience, include:
- Round details (what type, duration)
- Questions asked
- Tips from the candidate
- Outcome

Format as a numbered list."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.8
        )
        
        return [{
            "source": "AI-Generated (Based on patterns)",
            "content": response.choices[0].message.content
        }]
    
    async def extract_jd_info(self, jd_text: str) -> dict:
        """
        Extract structured information from job description.
        """
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

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        
        return {
            "jd_analysis": response.choices[0].message.content,
            "raw_jd": jd_text[:1000]  # Store excerpt
        }
    
    async def extract_resume_info(self, resume_text: str) -> dict:
        """
        Extract structured information from resume.
        """
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

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        
        return {
            "resume_analysis": response.choices[0].message.content,
            "raw_resume": resume_text[:1000]  # Store excerpt
        }
    
    async def close(self):
        """Cleanup HTTP client."""
        await self.http_client.aclose()
