# 🎯 Candi - Agentic Interview Helper

An AI-powered interview preparation assistant that analyzes your resume and job description to generate a comprehensive interview prep guide.

![Candi Screenshot](frontend/public/logo.png)

![Next.js](https://img.shields.io/badge/Next.js-16-black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4-412991)

## ✨ Features

- 📄 **Resume & JD Analysis**: Upload your resume and job description (PDF or TXT)
- 🤖 **Smart Routing**: Quick responses for simple questions, full analysis when needed
- 🎯 **Round Prediction**: Identifies likely interview rounds based on role patterns
- 💬 **AI-Generated Q&A**: Creates tailored questions with model answers
- 📊 **PDF Export**: Download a comprehensive preparation guide
- ⚡ **Real-time Progress**: Watch the AI think through each step

## 🚀 Quick Start

### Prerequisites

- [Node.js 18+](https://nodejs.org/)
- [Python 3.11+](https://python.org/)
- [OpenAI API Key](https://platform.openai.com/api-keys)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/Candi.git
   cd Candi
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

3. **Start the Backend**
   ```bash
   cd backend
   python -m venv venv
   .\venv\Scripts\activate  # On Mac/Linux: source venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

4. **Start the Frontend** (new terminal)
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

5. **Open the app**
   - Frontend: [http://localhost:3000](http://localhost:3000)
   - API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## 🐳 Docker Setup (Alternative)

```bash
docker-compose up --build
```

## 📁 Project Structure

```
Candi/
├── frontend/              # Next.js 16 app
│   ├── src/
│   │   ├── app/           # App Router pages
│   │   └── components/    # UI components
│   │       ├── ChatWindow.tsx
│   │       ├── ChatInput.tsx
│   │       ├── FileUpload.tsx
│   │       ├── MessageBubble.tsx
│   │       └── ThinkingAnimation.tsx
│   └── public/            # Static assets (logo)
│
├── backend/               # FastAPI app
│   ├── app/
│   │   ├── main.py        # API endpoints
│   │   ├── agents/        # AI agents
│   │   │   ├── router.py      # Intent classification
│   │   │   ├── researcher.py  # Resume/JD analysis
│   │   │   ├── strategist.py  # Round prediction
│   │   │   └── content_gen.py # Q&A generation
│   │   └── services/
│   │       └── pdf_generator.py
│   └── requirements.txt
│
├── docker-compose.yml
└── .env.example
```

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Smart chat (routes based on intent) |
| `/api/prepare` | POST | Full interview prep (SSE streaming) |
| `/api/extract-text` | POST | Extract text from PDF/TXT |
| `/api/download/{filename}` | GET | Download generated PDF |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

MIT License - feel free to use this for your own interview prep!
