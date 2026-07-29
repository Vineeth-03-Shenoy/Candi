from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel
from typing import Literal, Optional
import os
import re
import json
import asyncio
import io

from PyPDF2 import PdfReader

from app.config import settings
from app.agents.router import IntentRouter
from app.agents.researcher import ResearchAgent
from app.agents.strategist import StrategistAgent
from app.agents.content_gen import ContentGenAgent
from app.agents.retriever import RetrieverAgent
from app.services.cache_service import CacheService
from app.services.llm_client import create_llm_client
from app.services.pdf_generator import PDFGenerator
from app.services.search_provider import get_search_provider
from app.services.session_store import SessionStore
from app.services.vector_store import VectorStore
from app.utils.logger import get_logger
from app.utils import pii_masker
from app.services.ats_scorer import compute_ats_score

log = get_logger(__name__)
log.info("Starting Candi API")

router        = IntentRouter()
cache_service = CacheService()
researcher    = ResearchAgent(cache=cache_service)
strategist    = StrategistAgent()
content_gen   = ContentGenAgent()
pdf_gen       = PDFGenerator()
vector_store  = VectorStore()
retriever     = RetrieverAgent(vector_store)
session_store = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: reap sessions and cache entries older than their TTLs."""
    expired = session_store.cleanup_expired(settings.session_ttl_days * 86400)
    for sid in expired:
        vector_store.delete_session(sid)
    if expired:
        log.info("Startup cleanup complete | expired_sessions=%d", len(expired))

    cache_reaped = cache_service.clear_expired()
    if cache_reaped:
        log.info("Startup cache cleanup complete | expired_entries=%d", cache_reaped)

    yield


app = FastAPI(
    title="Candi - Interview Helper API",
    description="Agentic backend for interview preparation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _blank_tokens() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _add_tokens(session: dict, tokens: dict | None) -> None:
    """Accumulate token counts into session['token_usage']."""
    if not tokens:
        return
    usage = session.setdefault("token_usage", _blank_tokens())
    usage["prompt_tokens"]     += tokens.get("prompt_tokens", 0)
    usage["completion_tokens"] += tokens.get("completion_tokens", 0)
    usage["total_tokens"]      += tokens.get("total_tokens", 0)
    log.debug(
        "Tokens accumulated | +prompt=%d +completion=%d | session_total=%d",
        tokens.get("prompt_tokens", 0),
        tokens.get("completion_tokens", 0),
        usage["total_tokens"],
    )


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class ChatMessage(BaseModel):
    message: str
    session_id: str
    resume_text: Optional[str] = None
    jd_text: Optional[str] = None
    llm_provider: Optional[Literal["openai", "ollama"]] = None


class PrepareRequest(BaseModel):
    resume_text: str
    jd_text: str
    session_id: Optional[str] = "default"
    # Web search backend for the research step; None → SEARCH_PROVIDER env default
    search_provider: Optional[Literal["duckduckgo", "tavily"]] = None


class RoundQuestionsRequest(BaseModel):
    session_id: str
    round_info: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/")
async def root():
    log.debug("GET / — health ping")
    return {"message": "Candi API is running!"}


@app.get("/health")
async def health_check():
    # The app refuses to start without a key (see app/config.py), so this
    # is always true at runtime — kept for frontend compatibility.
    api_key_set = bool(settings.openai_api_key)
    log.info("GET /health | api_key_set=%s", api_key_set)
    return {"status": "healthy", "api_key_set": api_key_set}


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF or TXT file."""
    try:
        content  = await file.read()
        filename = file.filename or ""
        log.info("POST /api/extract-text | filename='%s' | size=%d bytes", filename, len(content))

        if filename.lower().endswith(".pdf"):
            pdf_reader   = PdfReader(io.BytesIO(content))
            text_parts   = [p for page in pdf_reader.pages if (p := page.extract_text())]
            extracted    = "\n".join(text_parts)

            if not extracted.strip():
                log.warning("PDF extraction yielded no text | filename='%s'", filename)
                return {
                    "success": False,
                    "error": "Could not extract text from this PDF. It may be image-based or encrypted. Please paste the text manually.",
                }

            log.info("PDF text extracted | filename='%s' | chars=%d", filename, len(extracted))
            return {"success": True, "text": extracted, "filename": filename}

        elif filename.lower().endswith(".txt"):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            log.info("TXT file read | filename='%s' | chars=%d", filename, len(text))
            return {"success": True, "text": text, "filename": filename}

        else:
            log.warning("Unsupported file type | filename='%s'", filename)
            return {"success": False, "error": "Unsupported file type. Please upload a PDF or TXT file."}

    except Exception as exc:
        log.error("extract_text failed | filename='%s' | error=%s", file.filename, exc, exc_info=True)
        return {"success": False, "error": f"Failed to process file: {exc}"}


@app.post("/api/chat")
async def chat(request: ChatMessage):
    """
    Smart chat endpoint — routes to the appropriate handler based on intent.
    All exceptions are caught and logged before returning a 500.
    """
    log.info(
        "POST /api/chat | session_id='%s' | message='%s'",
        request.session_id, request.message[:100],
    )

    try:
        session = session_store.get(request.session_id) or {}
        session.setdefault("messages",    [])
        session.setdefault("resume_text", "")
        session.setdefault("jd_text",     "")
        session.setdefault("prep_data",   None)
        session.setdefault("token_usage", _blank_tokens())

        if request.resume_text:
            log.debug("Updating session resume_text | session_id='%s'", request.session_id)
            session["resume_text"] = request.resume_text
        if request.jd_text:
            log.debug("Updating session jd_text | session_id='%s'", request.session_id)
            session["jd_text"] = request.jd_text

        # Mask PII from the incoming message before routing
        safe_message = pii_masker.mask_chat_message(request.message)
        log.debug("PII masked chat message | session_id='%s'", request.session_id)

        intent = router.classify_intent(
            safe_message,
            has_resume=bool(session.get("resume_text")),
            has_jd=bool(session.get("jd_text")),
        )

        # Per-request LLM client override (D.11 — Ollama frontend picker)
        req_client = None
        if request.llm_provider and request.llm_provider != settings.llm_provider:
            req_client = create_llm_client(provider=request.llm_provider)

        if intent == "FULL_PREPARATION":
            log.info("Chat redirecting to full preparation | session_id='%s'", request.session_id)
            session_store.save(request.session_id, session)
            return {
                "response": "I'll start preparing your comprehensive interview guide. This will take a moment as I research and generate personalized content...",
                "intent": intent,
                "action": "redirect_to_prepare",
                "session_id": request.session_id,
                "token_usage": session["token_usage"],
            }

        if intent == "QUICK_QUESTION":
            log.debug("Handling QUICK_QUESTION | session_id='%s'", request.session_id)
            reply, tokens = await router.quick_question_response(
                safe_message,
                session_id=request.session_id,
                retriever=retriever,
                resume_text=session.get("resume_text", ""),
                jd_text=session.get("jd_text", ""),
                prep_context=session.get("prep_data"),
                conversation_history=session.get("messages", []),
                client=req_client,
            )
        else:  # SIMPLE_CHAT
            log.debug("Handling SIMPLE_CHAT | session_id='%s'", request.session_id)
            reply, tokens = await router.simple_chat_response(
                safe_message,
                session_id=request.session_id,
                retriever=retriever,
                conversation_history=session.get("messages", []),
                client=req_client,
            )

        _add_tokens(session, tokens)

        session["messages"].append({"role": "user",      "content": request.message})
        session["messages"].append({"role": "assistant", "content": reply})
        session_store.save(request.session_id, session)

        log.info(
            "Chat response sent | session_id='%s' | intent=%s | reply_length=%d | session_total_tokens=%d",
            request.session_id, intent, len(reply), session["token_usage"]["total_tokens"],
        )
        return {
            "response":    reply,
            "intent":      intent,
            "session_id":  request.session_id,
            "token_usage": session["token_usage"],
        }

    except Exception as exc:
        log.error(
            "POST /api/chat failed | session_id='%s' | error=%s",
            request.session_id, exc, exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# Preparation pipeline (SSE)
# ------------------------------------------------------------------

async def generate_prep_events(
    resume_text: str,
    jd_text: str,
    session_id: str,
    search_provider: Optional[str] = None,
):
    """Generator that streams SSE progress events while running the full pipeline."""
    log.info(
        "Preparation pipeline started | session_id='%s' | resume_chars=%d | jd_chars=%d | search_provider=%s",
        session_id, len(resume_text), len(jd_text), search_provider or settings.search_provider,
    )

    # Resolve the search backend up front so a bad choice/missing key fails fast
    try:
        search = get_search_provider(search_provider, researcher.http_client)
    except ValueError as exc:
        log.warning("Search provider rejected | session_id='%s' | error=%s", session_id, exc)
        yield f"data: {json.dumps({'step': 'error', 'message': str(exc)})}\n\n"
        return

    # Session token accumulator for this pipeline run
    session = session_store.get(session_id) or {}
    session.setdefault("messages",    [])
    session.setdefault("token_usage", _blank_tokens())

    try:
        # ── Step 1: Resume analysis (full text — needed to extract candidate name) ──
        log.info("Pipeline step 1/8 — resume analysis | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 1, 'status': 'active', 'message': 'Analyzing your resume...'})}\n\n"
        resume_analysis = await researcher.extract_resume_info(resume_text)
        _add_tokens(session, resume_analysis.get("_tokens"))
        yield f"data: {json.dumps({'step': 1, 'status': 'complete', 'message': 'Resume analyzed'})}\n\n"
        log.info("Pipeline step 1/8 complete | session_id='%s'", session_id)

        # Extract candidate name (structured field), then create PII-masked
        # copies for all future prompts
        candidate_name = resume_analysis.get("resume_info").candidate_name or None
        if candidate_name:
            candidate_name = candidate_name.strip() or None
        masked_resume = pii_masker.mask_resume(resume_text, candidate_name=candidate_name)
        masked_jd     = pii_masker.mask_pii(jd_text)
        log.info(
            "PII masking applied | candidate_name_found=%s | session_id='%s'",
            bool(candidate_name), session_id,
        )

        # ── Step 2: JD analysis (masked) ──
        log.info("Pipeline step 2/8 — JD analysis | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 2, 'status': 'active', 'message': 'Analyzing job description...'})}\n\n"
        jd_analysis = await researcher.extract_jd_info(masked_jd)
        _add_tokens(session, jd_analysis.get("_tokens"))
        yield f"data: {json.dumps({'step': 2, 'status': 'complete', 'message': 'Job description analyzed'})}\n\n"
        log.info("Pipeline step 2/8 complete | session_id='%s'", session_id)

        jd_info      = jd_analysis["jd_info"]
        company_name = jd_info.company_name.strip() or "Target Company"
        role_name    = jd_info.role_title.strip()    or "Software Engineer"
        skills       = jd_info.required_skills[:6]
        log.info(
            "JD structured fields | company='%s' | role='%s' | skills=%s",
            company_name, role_name, skills,
        )

        # Store resume in vector store.
        # We store the LLM's structured analysis (which has **Section** headers matching
        # the chunking strategy) instead of the raw resume text, which has no such headers.
        log.debug("Storing resume analysis in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "resume",
            resume_analysis.get("resume_analysis", masked_resume),
            role=role_name, company=company_name,
        )
        log.debug("Storing JD analysis in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "jd",
            jd_analysis.get("jd_analysis", masked_jd),
            role=role_name, company=company_name,
        )

        # ── Step 3: Parallel web research ──
        log.info(
            "Pipeline step 3/8 — parallel web research | company='%s' | role='%s' | session_id='%s'",
            company_name, role_name, session_id,
        )
        yield f"data: {json.dumps({'step': 3, 'status': 'active', 'message': f'Researching {company_name} interview patterns...'})}\n\n"
        company_research, interview_experiences, technical_qa = await asyncio.gather(
            researcher.research_company(company_name, role_name, search),
            researcher.search_interview_experiences(company_name, role_name, search),
            researcher.fetch_technical_qa(skills, role_name, search),
        )
        _add_tokens(session, company_research.get("_tokens"))
        yield f"data: {json.dumps({'step': 3, 'status': 'complete', 'message': 'Company research complete'})}\n\n"
        log.info(
            "Pipeline step 3/8 complete | sources=%d | experiences=%d | skills_with_qa=%d | session_id='%s'",
            len(company_research.get("sources", [])), len(interview_experiences),
            len(technical_qa), session_id,
        )

        # Store company research in vector store
        log.debug("Storing company research in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "company_research",
            company_research.get("research_summary", ""),
            role=role_name, company=company_name,
        )

        # ── Step 4: Identify rounds ──
        log.info("Pipeline step 4/8 — round identification | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 4, 'status': 'active', 'message': 'Identifying likely interview rounds...'})}\n\n"
        rounds = await strategist.identify_rounds(jd_analysis, company_research)
        _add_tokens(session, rounds.get("_tokens"))
        yield f"data: {json.dumps({'step': 4, 'status': 'complete', 'message': 'Interview rounds identified'})}\n\n"
        log.info(
            "Pipeline step 4/8 complete | estimated_rounds=%s | session_id='%s'",
            rounds.get("estimated_rounds"), session_id,
        )

        # Store rounds in vector store
        log.debug("Storing rounds in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "rounds",
            rounds.get("rounds_breakdown", ""),
            role=role_name, company=company_name,
        )

        # ── Step 5: Preparation strategy ──
        log.info("Pipeline step 5/8 — preparation strategy | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 5, 'status': 'active', 'message': 'Creating preparation strategy...'})}\n\n"
        strategy = await strategist.generate_preparation_strategy(rounds, resume_analysis, jd_analysis)
        _add_tokens(session, strategy.get("_tokens"))
        yield f"data: {json.dumps({'step': 5, 'status': 'complete', 'message': 'Strategy created'})}\n\n"
        log.info("Pipeline step 5/8 complete | session_id='%s'", session_id)

        # Store strategy in vector store
        log.debug("Storing strategy in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "strategy",
            strategy.get("preparation_strategy", ""),
            role=role_name, company=company_name,
        )

        # ── Step 6: Role seniority analysis ──
        log.info("Pipeline step 6/8 — role seniority analysis | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 6, 'status': 'active', 'message': 'Analyzing role seniority fit...'})}\n\n"
        seniority = await strategist.analyze_role_seniority(resume_analysis, jd_analysis)
        _add_tokens(session, seniority.get("_tokens"))
        yield f"data: {json.dumps({'step': 6, 'status': 'complete', 'message': 'Seniority analysis complete'})}\n\n"
        log.info("Pipeline step 6/8 complete | is_fresher=%s | session_id='%s'",
                 seniority.get("is_fresher"), session_id)

        log.debug("Storing seniority analysis in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "seniority",
            seniority.get("seniority_analysis", ""),
            role=role_name, company=company_name,
        )

        # ── Step 7: Parallel question generation ──
        log.info("Pipeline step 7/8 — parallel question generation | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 7, 'status': 'active', 'message': 'Generating tailored questions...'})}\n\n"
        questions, behavioral, technical = await asyncio.gather(
            content_gen.generate_all_questions(
                rounds, jd_analysis, resume_analysis,
                company_research=company_research,
                interview_experiences=interview_experiences,
            ),
            content_gen.generate_behavioral_questions(
                resume_analysis,
                interview_experiences=interview_experiences,
                company_research=company_research,
            ),
            content_gen.generate_technical_deep_dives(
                jd_analysis, resume_analysis,
                technical_qa=technical_qa,
            ),
        )
        _add_tokens(session, questions.get("_tokens"))
        _add_tokens(session, behavioral.get("_tokens"))
        _add_tokens(session, technical.get("_tokens"))
        yield f"data: {json.dumps({'step': 7, 'status': 'complete', 'message': 'Questions generated'})}\n\n"
        log.info("Pipeline step 7/8 complete | session_id='%s'", session_id)

        # Store all question types in vector store
        log.debug("Storing questions in vector store | session_id='%s'", session_id)
        vector_store.store_chunks(
            session_id, "questions",
            questions.get("comprehensive_questions", ""),
            role=role_name, company=company_name,
        )
        vector_store.store_chunks(
            session_id, "behavioral",
            behavioral.get("behavioral_questions", ""),
            role=role_name, company=company_name,
        )
        vector_store.store_chunks(
            session_id, "technical",
            technical.get("technical_questions", ""),
            role=role_name, company=company_name,
        )

        # ── Step 8: PDF generation ──
        log.info("Pipeline step 8/8 — PDF generation | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 8, 'status': 'active', 'message': 'Preparing your interview guide...'})}\n\n"
        pdf_path = pdf_gen.generate_prep_guide(
            company_name=company_name,
            role_name=role_name,
            resume_analysis=resume_analysis,
            jd_analysis=jd_analysis,
            rounds=rounds,
            strategy=strategy,
            seniority_analysis=seniority,
            questions=questions,
            behavioral_questions=behavioral,
            technical_questions=technical,
        )
        yield f"data: {json.dumps({'step': 8, 'status': 'complete', 'message': 'Guide ready!'})}\n\n"
        log.info(
            "Pipeline step 8/8 complete | pdf='%s' | session_id='%s'",
            os.path.basename(pdf_path), session_id,
        )

        # Persist session
        session["prep_data"] = {
            "resume_analysis": resume_analysis,
            "jd_analysis":     jd_analysis,
            "rounds":          rounds,
            "strategy":        strategy,
            "seniority":       seniority,
            "questions":       questions,
        }
        session["pdf_path"] = pdf_path
        session_store.save(session_id, session)

        total_tokens = session["token_usage"]["total_tokens"]
        log.info(
            "Preparation pipeline complete | session_id='%s' | total_tokens=%d | pdf='%s'",
            session_id, total_tokens, os.path.basename(pdf_path),
        )

        summary = f"""**Your Interview Preparation Guide is Ready!**

I've analyzed your profile and the job requirements. Here's what I found:

**Role Analysis:**
{jd_analysis.get('jd_analysis', '')[:500]}...

**Role Fit & Salary Negotiation:**
{seniority.get('seniority_analysis', '')[:300]}...

**Interview Rounds:**
{rounds.get('rounds_breakdown', '')[:300]}...

**Preparation Strategy:**
{strategy.get('preparation_strategy', '')[:300]}...

I've generated a comprehensive PDF guide with:
- Detailed questions for each round
- Sample answers and frameworks
- Behavioral question prep (STAR method)
- Technical deep-dives on key skills

**Click the download button to get your full guide!**"""

        yield f"data: {json.dumps({'step': 'complete', 'summary': summary, 'pdf_path': pdf_path, 'token_usage': session['token_usage']})}\n\n"

    except Exception as exc:
        log.error(
            "Preparation pipeline failed | session_id='%s' | error=%s",
            session_id, exc, exc_info=True,
        )
        yield f"data: {json.dumps({'step': 'error', 'message': str(exc)})}\n\n"


@app.post("/api/prepare")
async def prepare_interview(request: PrepareRequest):
    """Full preparation endpoint with SSE streaming progress."""
    log.info(
        "POST /api/prepare | session_id='%s' | resume_chars=%d | jd_chars=%d | search_provider=%s",
        request.session_id, len(request.resume_text), len(request.jd_text),
        request.search_provider or settings.search_provider,
    )
    return StreamingResponse(
        generate_prep_events(
            request.resume_text, request.jd_text, request.session_id,
            search_provider=request.search_provider,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/questions/round")
async def get_round_questions(request: RoundQuestionsRequest):
    """Generate targeted questions for a specific interview round (B.10)."""
    log.info(
        "POST /api/questions/round | session_id='%s' | round='%s'",
        request.session_id, request.round_info[:80],
    )
    session = session_store.get(request.session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=400, detail="No preparation data found. Run /api/prepare first.")

    prep = session["prep_data"]
    result = await content_gen.generate_questions_for_round(
        round_info=request.round_info,
        jd_analysis=prep["jd_analysis"],
        resume_analysis=prep["resume_analysis"],
    )
    _add_tokens(session, result.get("_tokens"))
    session_store.save(request.session_id, session)
    return {
        "round_questions": result["round_questions"],
        "token_usage": session["token_usage"],
    }


@app.post("/api/seniority")
async def get_seniority_analysis(request: RoundQuestionsRequest):
    """Run the role seniority analysis on stored prep data (B.10)."""
    log.info(
        "POST /api/seniority | session_id='%s'", request.session_id,
    )
    session = session_store.get(request.session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=400, detail="No preparation data found. Run /api/prepare first.")

    prep = session["prep_data"]
    result = await strategist.analyze_role_seniority(
        prep["resume_analysis"], prep["jd_analysis"],
    )
    _add_tokens(session, result.get("_tokens"))
    session_store.save(request.session_id, session)
    return {
        "seniority_analysis": result["seniority_analysis"],
        "is_fresher": result["is_fresher"],
        "token_usage": session["token_usage"],
    }


@app.get("/api/download/{filename}")
async def download_pdf(filename: str):
    """Download the generated PDF. Filename is strictly validated (path-traversal safe)."""
    log.info("GET /api/download | filename='%s'", filename)

    # Strip any directory components, then enforce an allowlist pattern
    # (matches exactly what PDFGenerator produces: Interview_Prep_<Company>_<ts>.pdf)
    safe_name = os.path.basename(filename)
    if safe_name != filename or not re.fullmatch(r"[\w\-. ]+\.pdf", safe_name):
        log.warning("Rejected unsafe download filename | filename='%s'", filename)
        raise HTTPException(status_code=400, detail="Invalid filename")

    output_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "output"))
    filepath   = os.path.realpath(os.path.join(output_dir, safe_name))

    # Belt-and-braces: resolved path must stay inside output_dir
    if os.path.dirname(filepath) != output_dir:
        log.warning("Path traversal attempt blocked | filename='%s'", filename)
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not os.path.exists(filepath):
        log.warning("PDF not found | filename='%s'", safe_name)
        raise HTTPException(status_code=404, detail="PDF not found")

    log.info("Serving PDF | filename='%s'", safe_name)
    return FileResponse(filepath, media_type="application/pdf", filename=safe_name)


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get session state."""
    log.debug("GET /api/session | session_id='%s'", session_id)
    session = session_store.get(session_id)
    if not session:
        log.debug("Session not found | session_id='%s'", session_id)
        return {"exists": False}

    result = {
        "exists":        True,
        "has_resume":    bool(session.get("resume_text")),
        "has_jd":        bool(session.get("jd_text")),
        "has_prep":      bool(session.get("prep_data")),
        "message_count": len(session.get("messages", [])),
        "token_usage":   session.get("token_usage", _blank_tokens()),
    }
    log.debug("Session state | session_id='%s' | total_tokens=%d",
              session_id, result["token_usage"]["total_tokens"])
    return result


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and its Chroma vector-store collection."""
    log.info("DELETE /api/session | session_id='%s'", session_id)
    existed = session_store.delete(session_id)
    vector_store.delete_session(session_id)
    return {"deleted": True, "existed": existed}


# ════════════════════════════════════════════════════════════════════
# Section D — Feature endpoints
# ════════════════════════════════════════════════════════════════════


# ── D.4: Markdown export ──────────────────────────────────────────

@app.get("/api/export/{session_id}/markdown")
async def export_markdown(session_id: str):
    """Export the preparation guide as a markdown file."""
    log.info("GET /api/export/%s/markdown", session_id)
    session = session_store.get(session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=404, detail="No preparation data found")

    prep = session["prep_data"]

    parts = [
        "# Interview Preparation Guide",
        "",
        prep.get("resume_analysis", {}).get("resume_analysis", "*Not available*"),
        "",
        "---",
        "",
        "## Job Requirements",
        "",
        prep.get("jd_analysis", {}).get("jd_analysis", "*Not available*"),
        "",
        "---",
        "",
        "## Interview Rounds",
        "",
        prep.get("rounds", {}).get("rounds_breakdown", "*Not available*"),
    ]

    seniority = prep.get("seniority", {})
    if seniority.get("seniority_analysis"):
        parts.extend([
            "",
            "---",
            "",
            "## Role Fit & Salary Negotiation",
            "",
            seniority["seniority_analysis"],
        ])

    parts.extend([
        "",
        "---",
        "",
        "## Preparation Strategy",
        "",
        prep.get("strategy", {}).get("preparation_strategy", "*Not available*"),
        "",
        "---",
        "",
        "## Practice Questions",
        "",
        prep.get("questions", {}).get("comprehensive_questions", "*Not available*"),
        "",
        "---",
        "",
        "*Generated by Candi AI — [github.com/Vineeth-03-Shenoy/Candi](https://github.com/Vineeth-03-Shenoy/Candi)*",
    ])

    md = "\n".join(parts)
    filename = f"candi_prep_{session_id}.md"
    log.info("Markdown exported | session_id=%s | bytes=%d", session_id, len(md))
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── D.5: Streaming chat (SSE) ─────────────────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(request: ChatMessage):
    """Streaming chat — returns the LLM response as SSE text chunks."""
    log.info("POST /api/chat/stream | session_id='%s'", request.session_id)

    async def _stream():
        try:
            session = session_store.get(request.session_id) or {}
            session.setdefault("messages",    [])
            session.setdefault("resume_text", "")
            session.setdefault("jd_text",     "")
            session.setdefault("token_usage", _blank_tokens())

            if request.resume_text:
                session["resume_text"] = request.resume_text
            if request.jd_text:
                session["jd_text"] = request.jd_text

            safe_message = pii_masker.mask_chat_message(request.message)
            intent = router.classify_intent(
                safe_message,
                has_resume=bool(session.get("resume_text")),
                has_jd=bool(session.get("jd_text")),
            )

            # Yield intent first so the frontend can switch modes
            yield f"data: {json.dumps({'type': 'intent', 'intent': intent})}\n\n"

            if intent == "FULL_PREPARATION":
                yield f"data: {json.dumps({'type': 'redirect', 'action': 'redirect_to_prepare'})}\n\n"
                return

            if intent == "QUICK_QUESTION":
                reply, tokens = await router.quick_question_response(
                    safe_message,
                    session_id=request.session_id,
                    retriever=retriever,
                    resume_text=session.get("resume_text", ""),
                    jd_text=session.get("jd_text", ""),
                    prep_context=session.get("prep_data"),
                    conversation_history=session.get("messages", []),
                )
            else:
                reply, tokens = await router.simple_chat_response(
                    safe_message,
                    session_id=request.session_id,
                    retriever=retriever,
                    conversation_history=session.get("messages", []),
                )

            _add_tokens(session, tokens)

            session["messages"].append({"role": "user",      "content": request.message})
            session["messages"].append({"role": "assistant", "content": reply})
            session_store.save(request.session_id, session)

            # Stream the reply word-by-word for a visual streaming effect
            words = reply.split()
            chunk_size = 3
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i + chunk_size])
                yield f"data: {json.dumps({'type': 'text', 'content': chunk + ' '})}\n\n"
                await asyncio.sleep(0.05)

            yield f"data: {json.dumps({'type': 'done', 'token_usage': session['token_usage']})}\n\n"

        except Exception as exc:
            log.error("chat_stream failed | session_id='%s' | error=%s",
                      request.session_id, exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


# ── D.7: Prep history (list sessions) ─────────────────────────────

@app.get("/api/sessions")
async def list_sessions():
    """List past preparation sessions with basic metadata."""
    log.info("GET /api/sessions")
    sessions = session_store.list_all()
    return {"sessions": sessions, "count": len(sessions)}


# ── D.10: ATS keyword-match score ─────────────────────────────────

class ATSScoreRequest(BaseModel):
    resume_text: str
    jd_text: str


@app.post("/api/ats-score")
async def ats_score(request: ATSScoreRequest):
    """Compute ATS keyword overlap between resume and JD (pure Python, $0)."""
    log.info("POST /api/ats-score | resume_chars=%d | jd_chars=%d",
             len(request.resume_text), len(request.jd_text))
    result = compute_ats_score(request.resume_text, request.jd_text)
    return result


# ── D.12: Cover letter generator ──────────────────────────────────

class CoverLetterRequest(BaseModel):
    session_id: str


@app.post("/api/cover-letter")
async def generate_cover_letter(request: CoverLetterRequest):
    """Generate a cover letter from stored prep data (one LLM call)."""
    log.info("POST /api/cover-letter | session_id='%s'", request.session_id)
    session = session_store.get(request.session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=404, detail="No preparation data found")

    prep = session["prep_data"]
    resume = prep.get("resume_analysis", {}).get("resume_analysis", "")
    jd     = prep.get("jd_analysis", {}).get("jd_analysis", "")
    seniority = prep.get("seniority", {}).get("seniority_analysis", "")

    prompt = f"""Write a professional cover letter for this candidate applying to this role.

## Candidate Profile
{resume[:2000]}

## Job Requirements
{jd[:2000]}

## Seniority Assessment
{seniority[:500] if seniority else "Not available"}

Write a 3-4 paragraph cover letter that:
- Opens with enthusiasm for the role and company
- Highlights 2-3 specific skills/experiences that match the JD
- Uses specific details from the candidate's actual background (projects, technologies, metrics)
- Has a confident, professional closing
- NEVER uses placeholder text like [Company Name] or [Your Name]

The letter should read as if the candidate wrote it — authentic and personal."""

    from app.utils.llm_logger import llm_call
    letter, tokens = await llm_call(
        router.client, __name__,
        model=settings.router_simple_chat_model,
        messages=[{"role": "system", "content": "You are an expert career coach who writes authentic, compelling cover letters."},
                  {"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.7,
    )

    _add_tokens(session, tokens)
    session_store.save(request.session_id, session)

    log.info("Cover letter generated | session_id='%s' | length=%d",
             request.session_id, len(letter))
    return {
        "cover_letter": letter.strip(),
        "token_usage": session["token_usage"],
    }


# ── D.6: Mock Interview mode ──────────────────────────────────────

_mock_system_prompt = (
    "You are a professional technical interviewer. "
    "You are conducting a mock interview for the candidate. "
    "Ask ONE question at a time. Be direct and professional. "
    "After each answer, briefly note what was good and what could be improved, "
    "then ask the next question. Cover a mix of technical, behavioral, and "
    "role-specific topics based on the job description. "
    "Keep feedback constructive and specific. "
    "After 3-4 questions, offer to continue or wrap up."
)


class MockInterviewRequest(BaseModel):
    session_id: str


@app.post("/api/mock-interview/start")
async def mock_interview_start(request: MockInterviewRequest):
    """Start a mock interview session — returns the first question."""
    log.info("POST /api/mock-interview/start | session_id='%s'", request.session_id)
    session = session_store.get(request.session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=404, detail="No preparation data found")

    prep = session["prep_data"]
    jd     = prep.get("jd_analysis", {}).get("jd_analysis", "")
    resume = prep.get("resume_analysis", {}).get("resume_analysis", "")

    prompt = f"""You are starting a mock interview. Introduce yourself briefly,
then ask the FIRST interview question.

## Job Description
{jd[:1500]}

## Candidate Background
{resume[:1000]}

Keep it natural. Say 'Hello, I'll be your interviewer today...' then ask your first question.
Make the question relevant to this specific role."""

    from app.utils.llm_logger import llm_call
    reply, tokens = await llm_call(
        router.client, __name__,
        model=settings.router_simple_chat_model,
        messages=[{"role": "system", "content": _mock_system_prompt},
                  {"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.8,
    )

    _add_tokens(session, tokens)
    session.setdefault("mock_interview", []).append({"role": "interviewer", "content": reply})
    session_store.save(request.session_id, session)

    return {
        "message": reply,
        "question_number": 1,
        "token_usage": session["token_usage"],
    }


@app.post("/api/mock-interview/evaluate")
async def mock_interview_evaluate(request: MockInterviewRequest):
    """
    Evaluate the candidate's last answer and provide the next question.
    The candidate's answer should be the most recent user message in the session.
    """
    log.info("POST /api/mock-interview/evaluate | session_id='%s'", request.session_id)
    session = session_store.get(request.session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=404, detail="No preparation data found")

    messages = session.get("messages", [])
    # Find the most recent user message (the answer to evaluate)
    last_answer = ""
    for m in reversed(messages):
        if m["role"] == "user":
            last_answer = m["content"]
            break

    if not last_answer:
        raise HTTPException(status_code=400, detail="No user answer found to evaluate")

    recent = session.get("mock_interview", [])
    q_num   = len([m for m in recent if m["role"] == "interviewer"]) + 1
    context = "\n".join(
        f"{'Interviewer' if m['role'] == 'interviewer' else 'Candidate'}: {m['content'][:300]}"
        for m in recent[-6:]
    )

    prep = session["prep_data"]
    jd = prep.get("jd_analysis", {}).get("jd_analysis", "")

    prompt = f"""The candidate just answered the last question. Evaluate their answer and ask the next question.

## Job Description
{jd[:1000]}

## Previous Exchange
{context}

## Candidate's Latest Answer
{last_answer[:1500]}

First, give brief, specific feedback (1-2 sentences on what was good, 1 on what to improve).
Then ask the NEXT interview question (different topic than before).
Keep it natural and conversational."""

    from app.utils.llm_logger import llm_call
    reply, tokens = await llm_call(
        router.client, __name__,
        model=settings.router_simple_chat_model,
        messages=[{"role": "system", "content": _mock_system_prompt},
                  {"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.8,
    )

    _add_tokens(session, tokens)
    session.setdefault("mock_interview", []).append({"role": "candidate", "content": last_answer})
    session.setdefault("mock_interview", []).append({"role": "interviewer", "content": reply})
    session_store.save(request.session_id, session)

    return {
        "message": reply,
        "question_number": q_num,
        "token_usage": session["token_usage"],
    }


# ── D.13: Flashcards ──────────────────────────────────────────────

@app.get("/api/flashcards/{session_id}")
async def get_flashcards(session_id: str):
    """Extract behavioral Q&A pairs as flashcards from prep data."""
    log.info("GET /api/flashcards/%s", session_id)
    session = session_store.get(session_id)
    if not session or not session.get("prep_data"):
        raise HTTPException(status_code=404, detail="No preparation data found")

    prep = session["prep_data"]
    data_sources = [
        prep.get("questions", {}).get("comprehensive_questions", ""),
        session.get("prep_data", {}).get("behavioral_questions", ""),
    ]

    cards: list[dict] = []
    seen: set[str] = set()

    for text in data_sources:
        if not text:
            continue
        blocks = re.split(r"\n(?=\d+\.\s*\*\*Question|\*\*Question|###)", text)
        for block in blocks:
            q_match = re.search(
                r"(?:\d+\.\s*)?\*{0,2}Question\*{0,2}[\s:]+(.+?)(?:\n|$)", block
            )
            if not q_match:
                continue
            question = q_match.group(1).strip()
            if len(question) < 10 or question.lower() in seen:
                continue
            seen.add(question.lower())

            answer = block[q_match.end():].strip()
            answer = re.sub(r'\*\*Why They Ask This\*\*', '\n\n**Why They Ask This**', answer)
            answer = re.sub(r'\*\*Key Points to Cover\*\*', '\n\n**Key Points to Cover**', answer)
            answer = re.sub(r'\*\*Sample Answer.*?\*\*', '\n\n**Sample Answer**', answer)
            answer = re.sub(r'\*\*Common Mistakes\*\*', '\n\n**Common Mistakes**', answer)
            answer = answer[:600]

            cards.append({"question": question, "answer": answer})

    log.info("Flashcards generated | session_id=%s | count=%d", session_id, len(cards))
    return {"cards": cards, "count": len(cards)}
