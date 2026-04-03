# Candi - Agentic Interview Helper

An AI-powered interview preparation assistant that analyses your resume and job description, researches the company from the web, and generates a comprehensive, grounded interview prep guide as a downloadable PDF.

![Next.js](https://img.shields.io/badge/Next.js-16-black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991)

## Features

- **Resume & JD Analysis** — Upload your resume and job description (PDF or TXT); Candi extracts your skills, gaps, and the role's requirements.
- **Real Company Research** — Searches DuckDuckGo and scrapes GeeksforGeeks, Glassdoor snippets, and other public sources to find actual interview patterns for the target company and role.
- **Interview Experience Mining** — Finds and scrapes real candidate interview experiences from GeeksforGeeks to surface questions that were actually asked.
- **Grounded Technical Q&A** — Fetches real Q&A content from GeeksforGeeks and InterviewBit for each required skill; answers are based on this sourced content rather than hallucination.
- **Round Prediction** — Identifies likely interview rounds (DSA, System Design, Behavioural, HR, etc.) tailored to the company and role.
- **Personalised Prep Strategy** — Generates a 2-week study plan matched to the candidate's current level and the role's requirements.
- **PDF Export** — Packages everything into a structured, downloadable PDF guide.
- **Smart Chat** — Handles quick questions about the role/resume alongside the full prep flow.
- **Real-time Progress** — SSE streaming shows each pipeline step as it runs.

## Architecture

The backend uses a multi-agent pipeline:

```
Upload Resume + JD
        │
        ▼
[Step 1] ResearchAgent.extract_resume_info()     — profile analysis
[Step 2] ResearchAgent.extract_jd_info()         — JD analysis + extract company/role/skills
[Step 3] ─── parallel ───────────────────────────────────────────────────────────
         ResearchAgent.research_company()         — web search + page scraping
         ResearchAgent.search_interview_experiences() — GFG interview experience articles
         ResearchAgent.fetch_technical_qa()       — GFG/InterviewBit Q&A per skill
         ─────────────────────────────────────────────────────────────────────────
[Step 4] StrategistAgent.identify_rounds()        — round prediction
[Step 5] StrategistAgent.generate_preparation_strategy() — 2-week plan
[Step 6] ─── parallel ───────────────────────────────────────────────────────────
         ContentGenAgent.generate_all_questions() — grounded in research
         ContentGenAgent.generate_behavioral_questions() — culture-aligned
         ContentGenAgent.generate_technical_deep_dives() — answers from real sources
         ─────────────────────────────────────────────────────────────────────────
[Step 7] PDFGenerator.generate_prep_guide()       — PDF export
```

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Radix UI |
| Backend | FastAPI, Python 3.11+, Uvicorn |
| AI | OpenAI GPT-4o (complex) / GPT-4o-mini (fast tasks) |
| Web Research | httpx + BeautifulSoup4 (DuckDuckGo, GFG, InterviewBit) |
| PDF | ReportLab |
| Deployment | Docker + Docker Compose |

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- OpenAI API key

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/Candi.git
   cd Candi
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Add your OPENAI_API_KEY to .env
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

## Docker Setup

```bash
docker-compose up --build
```

## Project Structure

```
Candi/
├── frontend/
│   └── src/
│       ├── app/
│       │   └── page.tsx               # Main UI – chat + file upload
│       └── components/
│           ├── ChatWindow.tsx
│           ├── ChatInput.tsx
│           ├── FileUpload.tsx
│           ├── MessageBubble.tsx
│           └── ThinkingAnimation.tsx  # Real-time step progress
│
├── backend/
│   └── app/
│       ├── main.py                    # API endpoints + SSE pipeline
│       ├── agents/
│       │   ├── router.py              # Intent classification
│       │   ├── researcher.py          # Web research + resume/JD analysis
│       │   ├── strategist.py          # Round prediction + prep strategy
│       │   └── content_gen.py         # Grounded Q&A generation
│       └── services/
│           └── pdf_generator.py       # ReportLab PDF export
│
├── docker-compose.yml
└── .env.example
```

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/chat` | POST | Smart chat — routes by intent (simple/quick/full prep) |
| `/api/prepare` | POST | Full prep pipeline with SSE streaming |
| `/api/extract-text` | POST | Extract text from uploaded PDF or TXT |
| `/api/download/{filename}` | GET | Download generated PDF guide |
| `/api/session/{session_id}` | GET | Get session state |

## License

MIT
