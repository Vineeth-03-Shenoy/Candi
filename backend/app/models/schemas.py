from pydantic import BaseModel, Field
from typing import Optional, List


class PrepareRequest(BaseModel):
    """Request model for interview preparation"""
    resume_text: str
    jd_text: str
    linkedin_url: Optional[str] = None
    is_fresher: bool = True


class Question(BaseModel):
    """A single interview question with answer"""
    question: str
    answer: str
    strategy: str


class InterviewRound(BaseModel):
    """A single interview round"""
    round_name: str
    round_type: str
    questions: List[Question]


class PrepareResponse(BaseModel):
    """Response model for interview preparation"""
    summary: str
    company_name: str
    role_name: str
    rounds: List[InterviewRound]
    negotiation_tips: Optional[str] = None
    pdf_path: Optional[str] = None


# ------------------------------------------------------------------
# Structured Outputs schemas (OpenAI chat.completions.parse)
# Field names/comments double as extraction instructions for the model.
# Use "" for unknown strings and [] for unknown lists — never invent data.
# ------------------------------------------------------------------

class JDInfo(BaseModel):
    """Structured extraction of a job description."""
    company_name: str = Field(description="Company name, or '' if not mentioned")
    role_title: str = Field(description="Job title / role name")
    experience_level: str = Field(
        description="One of: Fresher / 1-3 years / 3-5 years / 5+ years / Senior, or '' if unclear"
    )
    required_skills: List[str] = Field(description="Top 10 must-have technical skills")
    nice_to_have_skills: List[str] = Field(description="Any mentioned nice-to-have skills, [] if none")
    key_responsibilities: List[str] = Field(description="Up to 5 key responsibilities, summarised")
    interview_focus_areas: List[str] = Field(
        description="Areas they will likely test, based on the requirements"
    )


class ResumeInfo(BaseModel):
    """Structured extraction of a candidate resume."""
    candidate_name: str = Field(description="Candidate's full name, or '' if not mentioned")
    experience_level: str = Field(description="Total years of experience, e.g. '3 years' or 'Fresher'")
    current_role: str = Field(description="Current or most recent job title, or '' if none")
    top_skills: List[str] = Field(description="Main technical skills")
    key_projects: List[str] = Field(description="2-3 notable projects, briefly summarised")
    education: str = Field(description="Highest qualification and institution, or '' if not mentioned")
    strengths_for_interviews: List[str] = Field(description="What the candidate should highlight")
    potential_gaps: List[str] = Field(description="Areas to prepare for tough questions")
