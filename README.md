# Candi — Agentic Interview Preparation Platform

An AI-powered interview preparation assistant that analyses your resume and job description, researches the company from the web, and generates a comprehensive, grounded interview prep guide as a downloadable PDF.

[![Next.js](https://img.shields.io/badge/Next.js-16-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991)](https://openai.com)
[![Ollama](https://img.shields.io/badge/Ollama-Local-000000)](https://ollama.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## Features

### Core Preparation Pipeline (10 steps)

| Step | Feature | Description |
|------|---------|-------------|
| 1 | **Resume Analysis** | Structured extraction of skills, experience, projects, and strengths using GPT-4o-mini with native structured outputs |
| 2 | **JD Analysis** | Extracts company, role, required skills, responsibilities, and interview focus areas |
| 3 | **Web Research** (parallel) | Real-time web search for company interview patterns, candidate experiences, and technical Q&A from trusted sources |
| 4 | **Round Prediction** | Predicts likely interview rounds based on JD requirements and company research |
| 5 | **Prep Strategy** | Generates a personalised week-by-week preparation plan matched to your profile |
| 6 | **Seniority Analysis** | Assesses candidate level vs role requirements; provides salary negotiation advice |
| 7 | **Resume Improvement** | Compares your resume against JD requirements and web-sourced best practices; suggests specific skills to add, achievement framing, and ATS keyword optimisation |
| 8 | **Salary Research** | Searches the web for market salary data (average, range, monthly equivalent) for the specific role, city, and country |
| 9 | **Question Generation** (parallel) | Generates comprehensive interview questions, behavioural questions (STAR), and technical deep-dives with sourced answers |
| 10 | **PDF Export** | Packages everything into a structured, downloadable PDF guide |

### Smart Features

- **Early Exit** — If the analysis determines the role is out of reach, stops early with a focused summary (profile analysis + JD + resume tips + salary) instead of generating a full prep guide — saves time and API credits
- **Research Cache** — SQLite-backed cache with 7-day TTL; repeat preparations for the same company or overlapping skillsets cost $0
- **Retries with Backoff** — Exponential backoff (1s→2s→4s) on all LLM calls and web searches; transient failures don't kill the pipeline
- **PII Masking** — Emails, phone numbers, and candidate names are redacted before any data leaves your machine; unmasked calls are withheld from logs
- **Cost Display** — Real-time token count with estimated cost visible in the header

### Chat & Interaction

- **Smart Chat** — Intent-aware chat routes automatically: simple conversation, quick Q&A (with resume/JD context), or full preparation
- **Streaming Chat (SSE)** — Real-time word-by-word streaming responses
- **Session History** — Resizable sidebar with all past conversations; switch between multiple company/role preparations; delete old sessions
- **File Attachment** — Attach PDF/TXT files inline for chat context without opening the upload panel

### Interview Practice Tools

- **Mock Interview Mode** — AI interviewer asks role-specific questions, evaluates answers with specific feedback, and asks follow-ups — turns the prep guide into a practice platform
- **Flashcards** — Flip-card UI extracted from behavioural Q&A; prev/next/flip controls with answers on the back
- **Cover Letter Generator** — Generates a personalised cover letter (one LLM call) from stored prep data

### Export & Analysis

- **PDF Download** — Full prep guide as a downloadable PDF (path-traversal safe)
- **Markdown Export** — Same content as a `.md` file for developers and version control
- **ATS Keyword Score** — Pure Python (no LLM, $0) keyword overlap analysis between resume and JD
- **Per-Round Drill-Down** — Generate targeted questions for a specific interview round
- **Standalone Seniority Analysis** — Run seniority assessment on-demand without full prep

### Provider Flexibility

- **LLM Providers** — Switch between OpenAI (GPT-4o/GPT-4o-mini) and Ollama (local, free, zero-API-key) via frontend picker — per-request switching works for both chat and the full prep pipeline
- **Web Search Providers** — Choose DuckDuckGo (free, no key) or Tavily (higher quality results, 1,000 free credits/month) per preparation run
- **Budget Profile** — `.env.example` documents an all-mini configuration (~$0.02/run, ~10× cheaper)
- **Local Embeddings** — ChromaDB uses free all-MiniLM-L6-v2 ONNX model for RAG (no API cost)

---

## Architecture

### 10-Step Agentic Pipeline

```
Upload Resume + JD
        │
        ▼
[Step 1]  ResearchAgent.extract_resume_info()          — Structured resume extraction
[Step 2]  ResearchAgent.extract_jd_info()              — Structured JD extraction
         │
         ▼
[Step 3]  ─── 5× parallel ─────────────────────────────────────────────────────
          ResearchAgent.research_company()              — Web search + page scraping
          ResearchAgent.search_interview_experiences()  — GFG interview articles
          ResearchAgent.fetch_technical_qa()            — Per-skill Q&A from trusted sources
          ResearchAgent.research_resume_improvement()   — Resume tips + market standards
          ResearchAgent.research_salary()               — Salary data from web
         ─────────────────────────────────────────────────────────────────────────
         │
         ▼
[Step 4]  StrategistAgent.identify_rounds()            — Round prediction
[Step 5]  StrategistAgent.generate_preparation_strategy() — 2-week prep plan
[Step 6]  StrategistAgent.analyze_role_seniority()     — Level assessment
         │
         ├── Underqualified? → EARLY EXIT (short PDF with profile + tips)
         │
         ▼
[Step 7]  Resume improvement synthesis                 — Gap analysis + ATS tips
[Step 8]  Salary analysis                              — Market rate + negotiation
[Step 9]  ─── 3× parallel ─────────────────────────────────────────────────────
          ContentGenAgent.generate_all_questions()      — Grounded in research
          ContentGenAgent.generate_behavioral_questions() — Culture-aligned STAR
          ContentGenAgent.generate_technical_deep_dives() — Progressive difficulty
         ─────────────────────────────────────────────────────────────────────────
         │
         ▼
[Step 10] PDFGenerator.generate_prep_guide()           — Structured PDF export
```

### Agents

| Agent | Responsibility |
|-------|---------------|
| **IntentRouter** | Classifies user intent (SIMPLE_CHAT / QUICK_QUESTION / FULL_PREPARATION); handles chat + streaming chat |
| **ResearchAgent** | Resume/JD parsing (Structured Outputs), web research, Tavily/DuckDuckGo searches, page scraping, resume improvement, salary research |
| **StrategistAgent** | Interview round prediction, preparation strategy, role seniority analysis |
| **ContentGenAgent** | Generates comprehensive, behavioural (STAR), and technical interview questions grounded in research |
| **RetrieverAgent** | RAG context retrieval from ChromaDB vector store for grounded chat responses |

### Services

| Service | Description |
|---------|-------------|
| **LLMClient** (ABC) | Pluggable LLM interface: `OpenAILLMClient` (native structured outputs) and `OllamaLLMClient` (local, free) |
| **SearchProvider** (ABC) | Pluggable web search: `DuckDuckGoProvider` (free scraping) and `TavilyProvider` (API, higher quality) |
| **CacheService** | SQLite-backed TTL cache for research results (7-day default, configurable) |
| **SessionStore** | SQLite-backed session persistence (survives restarts, TTL cleanup on startup) |
| **VectorStore** | ChromaDB wrapper with section/round/window chunking strategies; explicit local ONNX embeddings |
| **PDFGenerator** | ReportLab PDF generation with numbered sections, markdown cleaning, and early-exit mode |
| **ATSScorer** | Pure Python keyword-match scoring (100+ tech terms, $0) |
| **PIIMasker** | Email/phone/name redaction with strict phone regex (no false positives on URL digits) |
| **LLMLogger** | JSONL logging of every LLM interaction (PII-safe, with token counts and timing) |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Radix UI, react-markdown, react-dropzone |
| **Backend** | FastAPI, Python 3.11+, Uvicorn, Pydantic v2, pydantic-settings |
| **AI / LLM** | OpenAI GPT-4o (complex), GPT-4o-mini (fast tasks), Ollama (local, free) |
| **RAG / Embeddings** | ChromaDB with all-MiniLM-L6-v2 ONNX (local, free, $0) |
| **Web Research** | httpx + BeautifulSoup4 (DuckDuckGo HTML scraping, Tavily Search API) |
| **PDF** | ReportLab |
| **Reliability** | tenacity (exponential backoff retries on all LLM + HTTP calls) |
| **Persistence** | SQLite (stdlib sqlite3 — sessions + research cache, zero new deps) |
| **Deployment** | Docker + Docker Compose, non-root users, HEALTHCHECK, .dockerignore |

---

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- OpenAI API key (or Ollama running locally for free mode)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Vineeth-03-Shenoy/Candi.git
   cd Candi
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env — add your OPENAI_API_KEY at minimum
   ```

3. **Start the backend**
   ```bash
   cd backend
   python -m venv venv
   .\venv\Scripts\activate        # Windows
   # source venv/bin/activate     # Mac/Linux
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

4. **Start the frontend** (new terminal)
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. **Open the app**
   - Frontend: http://localhost:3000
   - API docs: http://localhost:8000/docs

### Budget Mode (all gpt-4o-mini, ~$0.02/run)

Set these in your `.env`:
```env
STRATEGIST_STRATEGY_MODEL=gpt-4o-mini
CONTENT_ROUND_QUESTIONS_MODEL=gpt-4o-mini
CONTENT_ALL_QUESTIONS_MODEL=gpt-4o-mini
CONTENT_TECHNICAL_MODEL=gpt-4o-mini
```

### Free Mode (Ollama, $0/run)

1. Install [Ollama](https://ollama.com) and pull a model: `ollama pull llama3.2`
2. Set `LLM_PROVIDER=ollama` in `.env`
3. Select Ollama in the frontend picker
4. Structured output extraction (resume/JD parsing) needs OpenAI — set `LLM_PROVIDER=openai` for initial steps or accept lower parse quality

## Docker Setup

```bash
docker-compose up --build
```

- Backend runs as non-root `appuser` (uid 1001)
- HEALTHCHECK on both services
- Healthcheck-based `depends_on` for frontend → backend
- `.dockerignore` prevents `.env`, `venv/`, `chroma_db/`, and `Logs/` from entering image layers

## Project Structure

```
Candi/
├── frontend/
│   ├── Dockerfile                          # Next.js production image
│   ├── .dockerignore
│   └── src/
│       ├── app/
│       │   ├── page.tsx                    # Main app — single-page, all state
│       │   ├── layout.tsx
│       │   └── globals.css
│       └── components/
│           ├── ChatWindow.tsx              # Message list + thinking animation
│           ├── ChatInput.tsx               # Text input + file attach + send
│           ├── FileUpload.tsx              # Drag-drop resume + JD textarea
│           ├── MessageBubble.tsx           # Markdown-rendered messages
│           ├── ThinkingAnimation.tsx       # Step-by-step pipeline progress
│           ├── SessionSidebar.tsx          # Resizable session history panel
│           ├── Flashcards.tsx              # Flip-card practice UI
│           └── ui/                         # shadcn/ui primitives
│
├── backend/
│   ├── Dockerfile                          # Python 3.11-slim, non-root user
│   ├── .dockerignore
│   ├── requirements.txt
│   └── app/
│       ├── main.py                         # FastAPI app, 10-step SSE pipeline, all endpoints
│       ├── config.py                       # pydantic-settings (validated at startup)
│       ├── agents/
│       │   ├── router.py                   # Intent classification + chat
│       │   ├── researcher.py              # Web research, resume/JD parsing
│       │   ├── strategist.py              # Rounds, strategy, seniority
│       │   ├── content_gen.py             # Grounded question generation
│       │   └── retriever.py               # ChromaDB RAG retrieval
│       ├── models/
│       │   └── schemas.py                  # JDInfo, ResumeInfo (structured outputs)
│       ├── services/
│       │   ├── llm_client.py              # LLMClient ABC + OpenAI/Ollama
│       │   ├── search_provider.py          # SearchProvider ABC + DDG/Tavily
│       │   ├── cache_service.py            # SQLite research cache
│       │   ├── session_store.py             # SQLite session persistence
│       │   ├── vector_store.py             # ChromaDB embeddings + chunking
│       │   ├── pdf_generator.py            # ReportLab PDF export
│       │   └── ats_scorer.py              # Pure-python keyword matcher
│       └── utils/
│           ├── llm_logger.py               # JSONL LLM interaction logging
│           ├── pii_masker.py               # PII redaction (email/phone/name)
│           └── logger.py                   # Structured logging
│
├── docker-compose.yml
├── .dockerignore
├── .env.example
└── README.md
```

## API Endpoints

### Chat & Preparation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Smart chat with intent routing (SIMPLE_CHAT / QUICK_QUESTION / FULL_PREPARATION) |
| `/api/chat/stream` | POST | Streaming chat via SSE (word-by-word) |
| `/api/prepare` | POST | Full 10-step preparation pipeline with SSE progress events |

### Interview Practice

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mock-interview/start` | POST | Start mock interview — returns first AI interviewer question |
| `/api/mock-interview/evaluate` | POST | Evaluate last answer + return next question with feedback |
| `/api/flashcards/{session_id}` | GET | Extract behavioural Q&A as flip-card pairs |
| `/api/questions/round` | POST | Generate targeted questions for a specific round |

### Content Generation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/cover-letter` | POST | Generate personalised cover letter from prep data |
| `/api/seniority` | POST | Run standalone seniority/role-fit analysis |
| `/api/ats-score` | POST | Pure Python keyword overlap score (resume vs JD, $0) |

### Export & Files

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/extract-text` | POST | Extract text from uploaded PDF/TXT file |
| `/api/download/{filename}` | GET | Download generated PDF guide (path-traversal safe) |
| `/api/export/{session_id}/markdown` | GET | Export prep guide as `.md` file |

### Sessions

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sessions` | GET | List all sessions with metadata (company, messages, tokens, PDF) |
| `/api/session/{session_id}` | GET | Get session state |
| `/api/session/{session_id}/messages` | GET | Get full message history for a session |
| `/api/session/{session_id}` | DELETE | Delete session + ChromaDB collection |

### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health ping |
| `/health` | GET | Health check with API key status |

## Configuration

All settings are documented in `.env.example`. Key configuration areas:

| Category | Key Settings |
|----------|-------------|
| **API Keys** | `OPENAI_API_KEY`, `TAVILY_API_KEY` |
| **LLM** | `LLM_PROVIDER` (openai/ollama), `OLLAMA_BASE_URL` |
| **Search** | `SEARCH_PROVIDER` (duckduckgo/tavily) |
| **Model Selection** | Per-agent model, max_tokens, and temperature settings for all 4 agents |
| **Sessions** | `SESSION_TTL_DAYS`, `CACHE_TTL_DAYS` |
| **Embeddings** | `EMBEDDING_MODEL` (local/openai-model-name) |
| **Budget** | Documented all-mini profile (~$0.02/run) |

## Observability

Every LLM interaction is logged in JSONL format at `backend/Logs/<Year>/<Month>/llm_interactions_<date>.jsonl`:
- Model, prompt/completion tokens, timing
- Input messages (PII-sanitised; withheld entirely for unmasked calls)
- Output text (PII-sanitised)

Web search activity is logged separately at `backend/Logs/<Year>/<Month>/web_search_<date>.jsonl`.

## License

MIT
