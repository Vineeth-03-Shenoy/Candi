from pydantic import BaseModel
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
