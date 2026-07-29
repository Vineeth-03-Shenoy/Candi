"""
ATS Keyword-Match Scorer — pure Python, zero LLM cost (D.10).

Computes the overlap between resume and JD keywords to give a quick
"how well does this resume match this job?" signal before running the
full preparation pipeline.

Strategy:
  - Parse resume text for skills (common tech terms, years patterns)
  - Parse JD text for required skills (same extraction)
  - Compute overlap percentage + list matched and missing skills
"""
import re
from typing import Optional

from app.utils.logger import get_logger

log = get_logger(__name__)

_TECH_SKILLS = {
    "python", "java", "javascript", "typescript", "go", "golang", "rust",
    "c++", "c#", ".net", "ruby", "php", "swift", "kotlin", "scala",
    "react", "angular", "vue", "svelte", "next.js", "nextjs", "node.js",
    "nodejs", "django", "flask", "fastapi", "spring", "express", "rails",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "graphql", "rest", "grpc", "docker", "kubernetes", "k8s", "aws",
    "azure", "gcp", "terraform", "ansible", "jenkins", "ci/cd",
    "git", "github", "gitlab", "linux", "unix", "bash", "shell",
    "machine learning", "deep learning", "nlp", "computer vision",
    "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn",
    "agile", "scrum", "kanban", "jira", "confluence", "figma",
    "html", "css", "sass", "tailwind", "bootstrap", "redux",
    "microservices", "api", "saas", "cloud", "devops", "sre",
    "spark", "hadoop", "kafka", "rabbitmq", "airflow",
    "security", "oauth", "jwt", "sso", "encryption",
    "testing", "unit test", "integration test", "e2e", "selenium",
    "c", "r", "matlab", "tableau", "power bi", "excel",
    "leadership", "mentoring", "communication", "problem-solving",
    "data structures", "algorithms", "system design", "oop",
    "functional programming", "tdd", "ddd", "solid",
    "blockchain", "web3", "solidity", "ios", "android", "flutter",
    "react native", "electron", "three.js", "webgl", "opengl",
}

_SKILL_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(s) for s in sorted(_TECH_SKILLS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

def _extract_skills(text: str) -> set[str]:
    """Extract known tech terms from text (lowercased for comparison)."""
    found = set()
    if not text:
        return found
    for match in _SKILL_PATTERN.finditer(text):
        found.add(match.group(0).lower())
    return found


def _extract_years(text: str) -> Optional[str]:
    """Heuristically extract years of experience."""
    patterns = [
        r"(\d+[+]*)\s*(?:years?|yrs?)\s*(?:of\s+)?experience",
        r"experience\s*(?:of\s+)?(\d+[+]*)\s*(?:years?|yrs?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def compute_ats_score(resume_text: str, jd_text: str) -> dict:
    """
    Compute ATS keyword match score between resume and JD.

    Returns:
        {
            "score": float,              # 0-100 percentage
            "matched_skills": [str],     # skills present in both
            "missing_skills": [str],     # skills in JD but not in resume
            "jd_skills_count": int,
            "resume_years": str | None,  # years extracted from resume
            "jd_years": str | None,      # years required per JD
        }
    """
    log.info("Computing ATS score | resume_length=%d | jd_length=%d",
             len(resume_text), len(jd_text))

    resume_skills = _extract_skills(resume_text)
    jd_skills     = _extract_skills(jd_text)

    matched        = sorted(jd_skills & resume_skills)
    missing        = sorted(jd_skills - resume_skills)
    jd_count       = len(jd_skills)
    score          = round((len(matched) / jd_count * 100), 1) if jd_count else 0.0

    resume_years = _extract_years(resume_text)
    jd_years     = _extract_years(jd_text)

    log.info(
        "ATS score computed | score=%.1f%% | matched=%d | missing=%d",
        score, len(matched), len(missing),
    )

    return {
        "score":           score,
        "matched_skills":  matched,
        "missing_skills":  missing,
        "jd_skills_count": jd_count,
        "resume_years":    resume_years,
        "jd_years":        jd_years,
    }
