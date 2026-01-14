from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
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

load_dotenv()

app = FastAPI(
    title="Candi - Interview Helper API",
    description="Agentic backend for interview preparation",
    version="1.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agents
router = IntentRouter()
researcher = ResearchAgent()
strategist = StrategistAgent()
content_gen = ContentGenAgent()
pdf_gen = PDFGenerator()

# In-memory session storage (replace with Redis/DB in production)
sessions = {}


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


@app.get("/")
async def root():
    return {"message": "Candi API is running!"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "api_key_set": bool(os.getenv("OPENAI_API_KEY"))}


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...)):
    """
    Extract text from uploaded PDF or TXT file.
    """
    try:
        content = await file.read()
        filename = file.filename or ""
        
        if filename.lower().endswith('.pdf'):
            # Extract text from PDF
            pdf_reader = PdfReader(io.BytesIO(content))
            text_parts = []
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            extracted_text = "\n".join(text_parts)
            
            if not extracted_text.strip():
                return {
                    "success": False,
                    "error": "Could not extract text from this PDF. It may be image-based or encrypted. Please paste the text manually."
                }
            
            return {"success": True, "text": extracted_text, "filename": filename}
        
        elif filename.lower().endswith('.txt'):
            # Read plain text
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                text = content.decode('latin-1')
            return {"success": True, "text": text, "filename": filename}
        
        else:
            return {
                "success": False,
                "error": "Unsupported file type. Please upload a PDF or TXT file."
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to process file: {str(e)}"
        }


@app.post("/api/chat")
async def chat(request: ChatMessage):
    """
    Smart chat endpoint - routes to appropriate handler based on intent.
    
    - Simple questions → Direct LLM response (fast)
    - Questions with context → Uses uploaded docs (medium)
    - Full prep request → Redirects to /api/prepare (slow)
    """
    session = sessions.get(request.session_id, {
        "messages": [],
        "resume_text": "",
        "jd_text": "",
        "prep_data": None
    })
    
    # Update session with any new document content
    if request.resume_text:
        session["resume_text"] = request.resume_text
    if request.jd_text:
        session["jd_text"] = request.jd_text
    
    # Classify intent
    intent = router.classify_intent(
        request.message,
        has_resume=bool(session.get("resume_text")),
        has_jd=bool(session.get("jd_text"))
    )
    
    if intent == "FULL_PREPARATION":
        return {
            "response": "I'll start preparing your comprehensive interview guide. This will take a moment as I research and generate personalized content...",
            "intent": intent,
            "action": "redirect_to_prepare",
            "session_id": request.session_id
        }
    
    elif intent == "QUICK_QUESTION":
        response = await router.quick_question_response(
            request.message,
            resume_text=session.get("resume_text", ""),
            jd_text=session.get("jd_text", ""),
            prep_context=session.get("prep_data")
        )
    
    else:  # SIMPLE_CHAT
        response = await router.simple_chat_response(
            request.message,
            conversation_history=session.get("messages", [])
        )
    
    # Update conversation history
    session["messages"].append({"role": "user", "content": request.message})
    session["messages"].append({"role": "assistant", "content": response})
    sessions[request.session_id] = session
    
    return {
        "response": response,
        "intent": intent,
        "session_id": request.session_id
    }


async def generate_prep_events(resume_text: str, jd_text: str, session_id: str):
    """
    Generator for SSE events during preparation.
    Yields progress updates as the agents work.
    """
    try:
        # Step 1: Analyze Resume
        yield f"data: {json.dumps({'step': 1, 'status': 'active', 'message': 'Analyzing your resume...'})}\n\n"
        resume_analysis = await researcher.extract_resume_info(resume_text)
        yield f"data: {json.dumps({'step': 1, 'status': 'complete', 'message': 'Resume analyzed'})}\n\n"
        
        # Step 2: Analyze JD
        yield f"data: {json.dumps({'step': 2, 'status': 'active', 'message': 'Analyzing job description...'})}\n\n"
        jd_analysis = await researcher.extract_jd_info(jd_text)
        yield f"data: {json.dumps({'step': 2, 'status': 'complete', 'message': 'Job description analyzed'})}\n\n"
        
        # Extract company and role from JD analysis
        company_name = "Target Company"  # TODO: Extract from JD
        role_name = "Software Engineer"  # TODO: Extract from JD
        
        # Step 3: Research Company
        yield f"data: {json.dumps({'step': 3, 'status': 'active', 'message': 'Researching company interview patterns...'})}\n\n"
        company_research = await researcher.research_company(company_name, role_name)
        yield f"data: {json.dumps({'step': 3, 'status': 'complete', 'message': 'Company research complete'})}\n\n"
        
        # Step 4: Identify Rounds
        yield f"data: {json.dumps({'step': 4, 'status': 'active', 'message': 'Identifying likely interview rounds...'})}\n\n"
        rounds = await strategist.identify_rounds(jd_analysis, company_research)
        yield f"data: {json.dumps({'step': 4, 'status': 'complete', 'message': 'Interview rounds identified'})}\n\n"
        
        # Step 5: Generate Strategy
        yield f"data: {json.dumps({'step': 5, 'status': 'active', 'message': 'Creating preparation strategy...'})}\n\n"
        strategy = await strategist.generate_preparation_strategy(rounds, resume_analysis, jd_analysis)
        yield f"data: {json.dumps({'step': 5, 'status': 'complete', 'message': 'Strategy created'})}\n\n"
        
        # Step 6: Generate Questions
        yield f"data: {json.dumps({'step': 6, 'status': 'active', 'message': 'Generating tailored questions...'})}\n\n"
        questions = await content_gen.generate_all_questions(rounds, jd_analysis, resume_analysis)
        behavioral = await content_gen.generate_behavioral_questions(resume_analysis)
        technical = await content_gen.generate_technical_deep_dives(jd_analysis, resume_analysis)
        yield f"data: {json.dumps({'step': 6, 'status': 'complete', 'message': 'Questions generated'})}\n\n"
        
        # Step 7: Generate PDF
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
            technical_questions=technical
        )
        yield f"data: {json.dumps({'step': 7, 'status': 'complete', 'message': 'Guide ready!'})}\n\n"
        
        # Store in session
        sessions[session_id] = sessions.get(session_id, {})
        sessions[session_id]["prep_data"] = {
            "resume_analysis": resume_analysis,
            "jd_analysis": jd_analysis,
            "rounds": rounds,
            "strategy": strategy,
            "questions": questions
        }
        sessions[session_id]["pdf_path"] = pdf_path
        
        # Create summary message
        summary = f"""🎯 **Your Interview Preparation Guide is Ready!**

I've analyzed your profile and the job requirements. Here's what I found:

**📋 Role Analysis:**
{jd_analysis.get('jd_analysis', '')[:500]}...

**🎯 Interview Rounds:**
{rounds.get('rounds_breakdown', '')[:300]}...

**📚 Preparation Strategy:**
{strategy.get('preparation_strategy', '')[:300]}...

I've generated a comprehensive PDF guide with:
- ✅ Detailed questions for each round
- ✅ Sample answers and frameworks
- ✅ Behavioral question prep (STAR method)
- ✅ Technical deep-dives on key skills

**Click the download button to get your full guide!**"""

        yield f"data: {json.dumps({'step': 'complete', 'summary': summary, 'pdf_path': pdf_path})}\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"


@app.post("/api/prepare")
async def prepare_interview(request: PrepareRequest):
    """
    Full preparation endpoint with streaming progress.
    This runs the complete Research → Strategy → Content → PDF pipeline.
    """
    return StreamingResponse(
        generate_prep_events(request.resume_text, request.jd_text, request.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/download/{filename}")
async def download_pdf(filename: str):
    """
    Download the generated PDF.
    """
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    filepath = os.path.join(output_dir, filename)
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="PDF not found")
    
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename
    )


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """
    Get session data including conversation history.
    """
    session = sessions.get(session_id)
    if not session:
        return {"exists": False}
    
    return {
        "exists": True,
        "has_resume": bool(session.get("resume_text")),
        "has_jd": bool(session.get("jd_text")),
        "has_prep": bool(session.get("prep_data")),
        "message_count": len(session.get("messages", []))
    }
