from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import os
import json
import asyncio
import io

from PyPDF2 import PdfReader

from app.agents.router import IntentRouter
from app.agents.researcher import ResearchAgent
from app.agents.strategist import StrategistAgent
from app.agents.content_gen import ContentGenAgent
from app.services.pdf_generator import PDFGenerator
from app.utils.logger import get_logger
from app.utils import pii_masker

load_dotenv()

log = get_logger(__name__)
log.info("Starting Candi API")

app = FastAPI(
    title="Candi - Interview Helper API",
    description="Agentic backend for interview preparation",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router     = IntentRouter()
researcher = ResearchAgent()
strategist = StrategistAgent()
content_gen = ContentGenAgent()
pdf_gen    = PDFGenerator()

sessions: dict = {}


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


class PrepareRequest(BaseModel):
    resume_text: str
    jd_text: str
    session_id: Optional[str] = "default"
    is_fresher: Optional[bool] = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/")
async def root():
    log.debug("GET / — health ping")
    return {"message": "Candi API is running!"}


@app.get("/health")
async def health_check():
    api_key_set = bool(os.getenv("OPENAI_API_KEY"))
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
        session = sessions.get(request.session_id, {})
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

        if intent == "FULL_PREPARATION":
            log.info("Chat redirecting to full preparation | session_id='%s'", request.session_id)
            sessions[request.session_id] = session
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
                resume_text=session.get("resume_text", ""),
                jd_text=session.get("jd_text", ""),
                prep_context=session.get("prep_data"),
            )
        else:  # SIMPLE_CHAT
            log.debug("Handling SIMPLE_CHAT | session_id='%s'", request.session_id)
            reply, tokens = await router.simple_chat_response(
                safe_message,
                conversation_history=session.get("messages", []),
            )

        _add_tokens(session, tokens)

        session["messages"].append({"role": "user",      "content": request.message})
        session["messages"].append({"role": "assistant", "content": reply})
        sessions[request.session_id] = session

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

async def generate_prep_events(resume_text: str, jd_text: str, session_id: str):
    """Generator that streams SSE progress events while running the full pipeline."""
    log.info(
        "Preparation pipeline started | session_id='%s' | resume_chars=%d | jd_chars=%d",
        session_id, len(resume_text), len(jd_text),
    )

    # Session token accumulator for this pipeline run
    session = sessions.get(session_id, {})
    session.setdefault("messages",    [])
    session.setdefault("token_usage", _blank_tokens())

    try:
        # ── Step 1: Resume analysis (full text — needed to extract candidate name) ──
        log.info("Pipeline step 1/7 — resume analysis | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 1, 'status': 'active', 'message': 'Analyzing your resume...'})}\n\n"
        resume_analysis = await researcher.extract_resume_info(resume_text)
        _add_tokens(session, resume_analysis.get("_tokens"))
        yield f"data: {json.dumps({'step': 1, 'status': 'complete', 'message': 'Resume analyzed'})}\n\n"
        log.info("Pipeline step 1/7 complete | session_id='%s'", session_id)

        # Extract candidate name, then create PII-masked copies for all future prompts
        candidate_name = pii_masker.extract_name_from_analysis(
            resume_analysis.get("resume_analysis", "")
        )
        masked_resume = pii_masker.mask_resume(resume_text, candidate_name=candidate_name)
        masked_jd     = pii_masker.mask_pii(jd_text)
        log.info(
            "PII masking applied | candidate_name_found=%s | session_id='%s'",
            bool(candidate_name), session_id,
        )

        # ── Step 2: JD analysis (masked) ──
        log.info("Pipeline step 2/7 — JD analysis | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 2, 'status': 'active', 'message': 'Analyzing job description...'})}\n\n"
        jd_analysis = await researcher.extract_jd_info(masked_jd)
        _add_tokens(session, jd_analysis.get("_tokens"))
        yield f"data: {json.dumps({'step': 2, 'status': 'complete', 'message': 'Job description analyzed'})}\n\n"
        log.info("Pipeline step 2/7 complete | session_id='%s'", session_id)

        company_name, role_name = researcher._extract_company_role(jd_analysis.get("jd_analysis", ""))
        skills = researcher._extract_skills_from_jd(jd_analysis.get("jd_analysis", ""))

        # ── Step 3: Parallel web research ──
        log.info(
            "Pipeline step 3/7 — parallel web research | company='%s' | role='%s' | session_id='%s'",
            company_name, role_name, session_id,
        )
        yield f"data: {json.dumps({'step': 3, 'status': 'active', 'message': f'Researching {company_name} interview patterns...'})}\n\n"
        company_research, interview_experiences, technical_qa = await asyncio.gather(
            researcher.research_company(company_name, role_name),
            researcher.search_interview_experiences(company_name, role_name),
            researcher.fetch_technical_qa(skills, role_name),
        )
        _add_tokens(session, company_research.get("_tokens"))
        yield f"data: {json.dumps({'step': 3, 'status': 'complete', 'message': 'Company research complete'})}\n\n"
        log.info(
            "Pipeline step 3/7 complete | sources=%d | experiences=%d | skills_with_qa=%d | session_id='%s'",
            len(company_research.get("sources", [])), len(interview_experiences),
            len(technical_qa), session_id,
        )

        # ── Step 4: Identify rounds ──
        log.info("Pipeline step 4/7 — round identification | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 4, 'status': 'active', 'message': 'Identifying likely interview rounds...'})}\n\n"
        rounds = await strategist.identify_rounds(jd_analysis, company_research)
        _add_tokens(session, rounds.get("_tokens"))
        yield f"data: {json.dumps({'step': 4, 'status': 'complete', 'message': 'Interview rounds identified'})}\n\n"
        log.info(
            "Pipeline step 4/7 complete | estimated_rounds=%s | session_id='%s'",
            rounds.get("estimated_rounds"), session_id,
        )

        # ── Step 5: Preparation strategy ──
        log.info("Pipeline step 5/7 — preparation strategy | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 5, 'status': 'active', 'message': 'Creating preparation strategy...'})}\n\n"
        strategy = await strategist.generate_preparation_strategy(rounds, resume_analysis, jd_analysis)
        _add_tokens(session, strategy.get("_tokens"))
        yield f"data: {json.dumps({'step': 5, 'status': 'complete', 'message': 'Strategy created'})}\n\n"
        log.info("Pipeline step 5/7 complete | session_id='%s'", session_id)

        # ── Step 6: Parallel question generation ──
        log.info("Pipeline step 6/7 — parallel question generation | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 6, 'status': 'active', 'message': 'Generating tailored questions...'})}\n\n"
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
        yield f"data: {json.dumps({'step': 6, 'status': 'complete', 'message': 'Questions generated'})}\n\n"
        log.info("Pipeline step 6/7 complete | session_id='%s'", session_id)

        # ── Step 7: PDF generation ──
        log.info("Pipeline step 7/7 — PDF generation | session_id='%s'", session_id)
        yield f"data: {json.dumps({'step': 7, 'status': 'active', 'message': 'Preparing your interview guide...'})}\n\n"
        pdf_path = pdf_gen.generate_prep_guide(
            company_name=company_name,
            role_name=role_name,
            resume_analysis=resume_analysis,
            jd_analysis=jd_analysis,
            rounds=rounds,
            strategy=strategy,
            questions=questions,
            behavioral_questions=behavioral,
            technical_questions=technical,
        )
        yield f"data: {json.dumps({'step': 7, 'status': 'complete', 'message': 'Guide ready!'})}\n\n"
        log.info(
            "Pipeline step 7/7 complete | pdf='%s' | session_id='%s'",
            os.path.basename(pdf_path), session_id,
        )

        # Persist session
        session["prep_data"] = {
            "resume_analysis": resume_analysis,
            "jd_analysis":     jd_analysis,
            "rounds":          rounds,
            "strategy":        strategy,
            "questions":       questions,
        }
        session["pdf_path"] = pdf_path
        sessions[session_id] = session

        total_tokens = session["token_usage"]["total_tokens"]
        log.info(
            "Preparation pipeline complete | session_id='%s' | total_tokens=%d | pdf='%s'",
            session_id, total_tokens, os.path.basename(pdf_path),
        )

        summary = f"""**Your Interview Preparation Guide is Ready!**

I've analyzed your profile and the job requirements. Here's what I found:

**Role Analysis:**
{jd_analysis.get('jd_analysis', '')[:500]}...

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
        "POST /api/prepare | session_id='%s' | resume_chars=%d | jd_chars=%d",
        request.session_id, len(request.resume_text), len(request.jd_text),
    )
    return StreamingResponse(
        generate_prep_events(request.resume_text, request.jd_text, request.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/api/download/{filename}")
async def download_pdf(filename: str):
    """Download the generated PDF."""
    log.info("GET /api/download | filename='%s'", filename)
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    filepath   = os.path.join(output_dir, filename)

    if not os.path.exists(filepath):
        log.warning("PDF not found | filename='%s'", filename)
        raise HTTPException(status_code=404, detail="PDF not found")

    log.info("Serving PDF | filename='%s'", filename)
    return FileResponse(filepath, media_type="application/pdf", filename=filename)


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Get session state."""
    log.debug("GET /api/session | session_id='%s'", session_id)
    session = sessions.get(session_id)
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
