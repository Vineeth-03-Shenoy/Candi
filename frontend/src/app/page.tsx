"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import Image from "next/image";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { FileUpload } from "@/components/FileUpload";
import { ThinkingAnimation } from "@/components/ThinkingAnimation";
import { Flashcards } from "@/components/Flashcards";
import { SessionSidebar } from "@/components/SessionSidebar";
import { Message } from "@/components/MessageBubble";
import { Button } from "@/components/ui/button";
import { X, Rocket, Download, Cpu, Globe, Zap, DollarSign, MessageSquare, FileText, GraduationCap, Layers, Server, PanelLeft } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_CACHE_KEY = "candi_token_usage";
const SEARCH_PROVIDER_KEY = "candi_search_provider";
const LLM_PROVIDER_KEY = "candi_llm_provider";

type SearchProvider = "duckduckgo" | "tavily";
type LLMProvider = "openai" | "ollama";

interface ThinkingStep {
  id: string;
  icon: "brain" | "search" | "file" | "lightbulb" | "check";
  text: string;
  status: "pending" | "active" | "complete";
}

interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

interface FlashCard {
  question: string;
  answer: string;
}

function loadTokensFromCache(): TokenUsage {
  try {
    const stored = localStorage.getItem(TOKEN_CACHE_KEY);
    if (stored) return JSON.parse(stored);
  } catch {}
  return { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
}

function saveTokensToCache(usage: TokenUsage) {
  try {
    localStorage.setItem(TOKEN_CACHE_KEY, JSON.stringify(usage));
  } catch {}
}

function loadSearchProvider(): SearchProvider {
  try {
    const stored = localStorage.getItem(SEARCH_PROVIDER_KEY);
    if (stored === "tavily" || stored === "duckduckgo") return stored;
  } catch {}
  return "duckduckgo";
}

function loadLlmProvider(): LLMProvider {
  try {
    const stored = localStorage.getItem(LLM_PROVIDER_KEY);
    if (stored === "ollama" || stored === "openai") return stored;
  } catch {}
  return "openai";
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

// ── D.2 Cost estimation ────────────────────────────────────
// Blended rate: ~$0.50/1K tokens (weighted mix of gpt-4o-mini + gpt-4o calls)
function estimateCost(usage: TokenUsage): string {
  const k = usage.total_tokens / 1000;
  const cost = k * 0.50;  // cents, not dollars
  if (cost < 1) return "<$0.01";
  return `$${(cost / 100).toFixed(2)}`;
}

export default function Home() {
  const [messages,      setMessages]      = useState<Message[]>([]);
  const [isLoading,     setIsLoading]     = useState(false);
  const [isThinking,    setIsThinking]    = useState(false);
  const [showUpload,    setShowUpload]    = useState(true);
  const [resumeContent, setResumeContent] = useState("");
  const [jdContent,     setJdContent]     = useState("");
  const [pdfPath,       setPdfPath]       = useState<string | null>(null);
  const [tokenUsage,    setTokenUsage]    = useState<TokenUsage>({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });
  const [searchProvider, setSearchProvider] = useState<SearchProvider>("duckduckgo");
  const [llmProvider, setLlmProvider] = useState<LLMProvider>("openai");
  const [mockMode, setMockMode] = useState(false);
  const [flashcards, setFlashcards] = useState<FlashCard[]>([]);
  const [showFlashcards, setShowFlashcards] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);

  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([
    { id: "1", icon: "file",      text: "Analyzing your resume...",                  status: "pending" },
    { id: "2", icon: "file",      text: "Analyzing job description...",              status: "pending" },
    { id: "3", icon: "search",    text: "Researching company interview patterns...", status: "pending" },
    { id: "4", icon: "brain",     text: "Identifying likely interview rounds...",    status: "pending" },
    { id: "5", icon: "lightbulb", text: "Creating preparation strategy...",          status: "pending" },
    { id: "6", icon: "brain",     text: "Analyzing role seniority fit...",           status: "pending" },
    { id: "7", icon: "file",      text: "Generating resume improvement tips...",     status: "pending" },
    { id: "8", icon: "search",    text: "Researching salary data...",                status: "pending" },
    { id: "9", icon: "lightbulb", text: "Generating tailored questions...",          status: "pending" },
    { id: "10", icon: "check",    text: "Preparing your interview guide...",         status: "pending" },
  ]);

  const mockRef     = useRef(false);

  const sessionIdRef = useRef(`session_${Date.now()}`);

  // Load token usage + search provider from localStorage on mount
  useEffect(() => {
    setTokenUsage(loadTokensFromCache());
    setSearchProvider(loadSearchProvider());
    setLlmProvider(loadLlmProvider());
  }, []);

  const chooseSearchProvider = (provider: SearchProvider) => {
    setSearchProvider(provider);
    try {
      localStorage.setItem(SEARCH_PROVIDER_KEY, provider);
    } catch {}
  };

  const chooseLlmProvider = (provider: LLMProvider) => {
    setLlmProvider(provider);
    try {
      localStorage.setItem(LLM_PROVIDER_KEY, provider);
    } catch {}
  };

  const updateTokenUsage = useCallback((incoming: TokenUsage | undefined) => {
    if (!incoming) return;
    // Always use the cumulative value returned by the server (it already sums the full session)
    setTokenUsage(incoming);
    saveTokensToCache(incoming);
  }, []);

  const addMessage = useCallback((role: "user" | "assistant", content: string) => {
    const newMessage: Message = {
      id: Date.now().toString(),
      role,
      content,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, newMessage]);
    return newMessage;
  }, []);

  const updateThinkingStep = (stepNumber: number, status: "active" | "complete") => {
    setThinkingSteps(prev => prev.map((step, index) => {
      if (index + 1 === stepNumber) return { ...step, status };
      if (index + 1 < stepNumber && status === "active") return { ...step, status: "complete" };
      return step;
    }));
  };

  const resetThinkingSteps = () => {
    setThinkingSteps(prev => prev.map(step => ({ ...step, status: "pending" as const })));
  };

  const handleStartPreparation = async () => {
    if (!resumeContent || !jdContent) return;

    setShowUpload(false);
    addMessage("user", "I've uploaded my resume and job description. Please help me prepare for the interview.");
    setIsLoading(true);
    setIsThinking(true);
    resetThinkingSteps();

    try {
      const response = await fetch(`${API_URL}/api/prepare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text:     resumeContent,
          jd_text:         jdContent,
          session_id:      sessionIdRef.current,
          search_provider: searchProvider,
          llm_provider:    llmProvider,
        }),
      });

      if (!response.ok) throw new Error("Failed to prepare interview guide");

      const reader  = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          for (const line of chunk.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6));

              if (data.step === "error") throw new Error(data.message);

              if (data.step === "complete") {
                setIsThinking(false);
                setPdfPath(data.pdf_path);
                addMessage("assistant", data.summary);
                updateTokenUsage(data.token_usage);
              } else if (typeof data.step === "number") {
                updateThinkingStep(data.step, data.status);
              }
            } catch {
              // Skip malformed JSON lines
            }
          }
        }
      }
    } catch (error) {
      console.error("Preparation error:", error);
      setIsThinking(false);
      addMessage("assistant", "I apologize, but I encountered an error while processing your request. Please make sure the backend server is running and try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (content: string) => {
    if (mockMode) {
      addMessage("user", content);
      setIsLoading(true);
      try {
        const response = await fetch(`${API_URL}/api/mock-interview/evaluate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionIdRef.current }),
        });
        if (!response.ok) throw new Error("Evaluation failed");
        const data = await response.json();
        updateTokenUsage(data.token_usage);
        addMessage("assistant", data.message);
      } catch {
        addMessage("assistant", "I'm having trouble evaluating your answer. Let's try again.");
      } finally {
        setIsLoading(false);
      }
      return;
    }

    addMessage("user", content);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message:     content,
          session_id:  sessionIdRef.current,
          resume_text: resumeContent || undefined,
          jd_text:     jdContent     || undefined,
          llm_provider: llmProvider,
        }),
      });

      if (!response.ok) throw new Error("Failed to send message");

      const data = await response.json();
      updateTokenUsage(data.token_usage);

      if (data.action === "redirect_to_prepare" && resumeContent && jdContent) {
        handleStartPreparation();
      } else {
        addMessage("assistant", data.response);
      }
    } catch (error) {
      console.error("Chat error:", error);
      addMessage("assistant", `I'm having trouble connecting to the server. Please make sure the backend is running at ${API_URL}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadPdf = () => {
    if (pdfPath) {
      const parts    = pdfPath.replace(/\\/g, "/").split("/");
      const filename = parts[parts.length - 1];
      window.open(`${API_URL}/api/download/${filename}`, "_blank");
    }
  };

  // ── Mock interview ────────────────────────────────────────

  const handleStartMockInterview = async () => {
    setMockMode(true);
    mockRef.current = true;
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/mock-interview/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current }),
      });
      if (!response.ok) throw new Error("Failed to start mock interview");
      const data = await response.json();
      updateTokenUsage(data.token_usage);
      addMessage("assistant", data.message);
    } catch {
      addMessage("assistant", "I couldn't start the mock interview. Make sure you've run a preparation first.");
      setMockMode(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopMock = () => {
    setMockMode(false);
    mockRef.current = false;
    addMessage("assistant", "Mock interview ended. Great work! Review the feedback above and practice more when you're ready.");
  };

  // ── Export helpers ────────────────────────────────────────

  const handleExportMarkdown = () => {
    window.open(`${API_URL}/api/export/${sessionIdRef.current}/markdown`, "_blank");
  };

  const handleGenerateCoverLetter = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/cover-letter`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current }),
      });
      if (!response.ok) throw new Error("Cover letter generation failed");
      const data = await response.json();
      updateTokenUsage(data.token_usage);
      addMessage("assistant", "**Your Cover Letter**\n\n" + data.cover_letter);
    } catch {
      addMessage("assistant", "I couldn't generate a cover letter. Have you run a preparation first?");
    } finally {
      setIsLoading(false);
    }
  };

  // ── Flashcards ─────────────────────────────────────────

  const handleToggleFlashcards = async () => {
    if (showFlashcards) {
      setShowFlashcards(false);
      return;
    }
    if (flashcards.length) {
      setShowFlashcards(true);
      return;
    }
    setIsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/flashcards/${sessionIdRef.current}`);
      if (!response.ok) throw new Error("No flashcards");
      const data = await response.json();
      setFlashcards(data.cards || []);
      setShowFlashcards(true);
    } catch {
      addMessage("assistant", "No flashcards available. Run a preparation first to generate behavioral Q&A.");
    } finally {
      setIsLoading(false);
    }
  };

  // ── Session switching ────────────────────────────────────

  const handleSelectSession = async (sessionId: string) => {
    if (sessionId === sessionIdRef.current) return;
    sessionIdRef.current = sessionId;
    setIsLoading(true);
    setPdfPath(null);
    setFlashcards([]);
    setShowFlashcards(false);
    setMockMode(false);
    setShowUpload(false);
    setTokenUsage({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });

    try {
      const res = await fetch(`${API_URL}/api/session/${sessionId}/messages`);
      if (!res.ok) throw new Error("Failed to load");
      const data = await res.json();
      const loaded: Message[] = (data.messages || []).map((m: any, i: number) => ({
        id: `${sessionId}-${i}`,
        role: m.role,
        content: m.content,
        timestamp: new Date(),
      }));
      setMessages(loaded);
      if (data.has_resume) setResumeContent("(loaded from session)");
      if (data.has_jd) setJdContent("(loaded from session)");
      if (data.has_prep) {
        const s = await fetch(`${API_URL}/api/session/${sessionId}`);
        if (s.ok) {
          const sd = await s.json();
          setTokenUsage(sd.token_usage || { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });
        }
      }
    } catch {
      // fallback
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewSession = () => {
    const id = `session_${Date.now()}`;
    sessionIdRef.current = id;
    setMessages([]);
    setPdfPath(null);
    setTokenUsage({ prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });
    setResumeContent("");
    setJdContent("");
    setMockMode(false);
    setFlashcards([]);
    setShowFlashcards(false);
    setShowUpload(true);
    setShowSidebar(false);
  };

  const canStart = resumeContent && jdContent;

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      {showSidebar && (
        <SessionSidebar
          activeSessionId={sessionIdRef.current}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onClose={() => setShowSidebar(false)}
        />
      )}

      <div className="flex flex-col flex-1 overflow-hidden">

      {/* Header */}
      <header className="flex-shrink-0 border-b px-4 py-3 bg-background/80 backdrop-blur-xl z-10">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <Image
            src="/logo.png"
            alt="Candi - Master Your Interview"
            width={180}
            height={50}
            className="h-8 sm:h-10 md:h-12 w-auto"
            priority
          />
          <div className="flex items-center gap-2 flex-wrap justify-end">

            {/* Sidebar toggle */}
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setShowSidebar((prev) => !prev)}
              title="Conversations"
            >
              <PanelLeft className="w-4 h-4" />
            </Button>

            {/* Token usage + cost badge */}
            {tokenUsage.total_tokens > 0 && (
              <div
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-muted border text-xs text-muted-foreground"
                title={`Prompt: ${tokenUsage.prompt_tokens.toLocaleString()} | Completion: ${tokenUsage.completion_tokens.toLocaleString()} | Total: ${tokenUsage.total_tokens.toLocaleString()}`}
              >
                <Cpu className="w-3 h-3 shrink-0" />
                <span>{formatTokens(tokenUsage.total_tokens)} tokens</span>
                <span className="text-cyan-500">·</span>
                <DollarSign className="w-3 h-3 shrink-0 text-emerald-400" />
                <span className="text-emerald-400">{estimateCost(tokenUsage)}</span>
              </div>
            )}

            {/* Mock interview toggle */}
            {pdfPath && (
              <Button
                onClick={handleToggleFlashcards}
                size="sm"
                variant={showFlashcards ? "default" : "outline"}
                className={showFlashcards ? "bg-rose-500 hover:bg-rose-600 text-white" : "border-rose-500/50 text-rose-400 hover:bg-rose-500/10"}
              >
                <Layers className="w-4 h-4 mr-1" />
                {showFlashcards ? "Hide Cards" : "Flashcards"}
              </Button>
            )}

            {pdfPath && (
              <Button
                onClick={mockMode ? handleStopMock : handleStartMockInterview}
                size="sm"
                variant={mockMode ? "destructive" : "outline"}
                className={mockMode ? "" : "border-amber-500/50 text-amber-400 hover:bg-amber-500/10"}
                disabled={isLoading}
              >
                <GraduationCap className="w-4 h-4 mr-1" />
                {mockMode ? "Stop Mock" : "Mock Interview"}
              </Button>
            )}

            {/* Export markdown */}
            {pdfPath && (
              <Button
                onClick={handleExportMarkdown}
                size="sm"
                variant="outline"
                className="border-slate-500/50 text-slate-400 hover:bg-slate-500/10"
              >
                <FileText className="w-4 h-4 mr-1" />
                .md
              </Button>
            )}

            {/* Cover letter */}
            {pdfPath && (
              <Button
                onClick={handleGenerateCoverLetter}
                size="sm"
                variant="outline"
                disabled={isLoading}
                className="border-violet-500/50 text-violet-400 hover:bg-violet-500/10"
              >
                <MessageSquare className="w-4 h-4 mr-1" />
                Cover Letter
              </Button>
            )}

            {pdfPath && (
              <Button
                onClick={handleDownloadPdf}
                size="sm"
                className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white"
              >
                <Download className="w-4 h-4 mr-1" />
                Download Guide
              </Button>
            )}

            <span className="text-xs text-muted-foreground hidden sm:block">
              Master Your Interview
            </span>
          </div>
        </div>
      </header>

      {/* Upload Panel */}
      {showUpload && (
        <div className="flex-shrink-0 border-b bg-muted/30 p-4 animate-in slide-in-from-top duration-300">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium">Upload Documents</h2>
              <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setShowUpload(false)}>
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FileUpload type="resume" label="Your Resume"      onFileUploaded={setResumeContent} />
              <FileUpload type="jd"     label="Job Description"  onFileUploaded={setJdContent}     textInput />
            </div>

            {/* LLM provider picker */}
            <div className="mt-3">
              <p className="text-xs text-muted-foreground mb-1.5">LLM provider (chat only)</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => chooseLlmProvider("openai")}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                    llmProvider === "openai"
                      ? "border-cyan-500 bg-cyan-500/10 text-foreground"
                      : "border-border bg-background text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Server className="w-4 h-4 shrink-0" />
                  <span>
                    <span className="block font-medium">OpenAI</span>
                    <span className="block text-[10px] text-muted-foreground">API key · paid</span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => chooseLlmProvider("ollama")}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                    llmProvider === "ollama"
                      ? "border-cyan-500 bg-cyan-500/10 text-foreground"
                      : "border-border bg-background text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Layers className="w-4 h-4 shrink-0" />
                  <span>
                    <span className="block font-medium">Ollama</span>
                    <span className="block text-[10px] text-muted-foreground">Local · free</span>
                  </span>
                </button>
              </div>
            </div>
            <div className="mt-3">
              <p className="text-xs text-muted-foreground mb-1.5">Web search provider</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => chooseSearchProvider("duckduckgo")}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                    searchProvider === "duckduckgo"
                      ? "border-cyan-500 bg-cyan-500/10 text-foreground"
                      : "border-border bg-background text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Globe className="w-4 h-4 shrink-0" />
                  <span>
                    <span className="block font-medium">DuckDuckGo</span>
                    <span className="block text-[10px] text-muted-foreground">Free · no API key</span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => chooseSearchProvider("tavily")}
                  className={`flex items-center gap-2 rounded-md border px-3 py-2 text-left text-xs transition-colors ${
                    searchProvider === "tavily"
                      ? "border-cyan-500 bg-cyan-500/10 text-foreground"
                      : "border-border bg-background text-muted-foreground hover:bg-muted"
                  }`}
                >
                  <Zap className="w-4 h-4 shrink-0" />
                  <span>
                    <span className="block font-medium">Tavily</span>
                    <span className="block text-[10px] text-muted-foreground">API key · higher quality</span>
                  </span>
                </button>
              </div>
            </div>

            {canStart && (
              <Button
                onClick={handleStartPreparation}
                disabled={isLoading}
                className="w-full mt-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 text-white"
              >
                <Rocket className="w-4 h-4 mr-2" />
                Start Interview Preparation
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Flashcards Panel */}
      {showFlashcards && flashcards.length > 0 && (
        <Flashcards cards={flashcards} onClose={() => setShowFlashcards(false)} />
      )}

      {/* Chat area */}
      <ChatWindow
        messages={messages}
        isLoading={isLoading && !isThinking}
        isThinking={isThinking}
        thinkingSteps={thinkingSteps}
      />

      {/* Input */}
      <ChatInput
        onSendMessage={handleSendMessage}
        onToggleUpload={() => setShowUpload(prev => !prev)}
        isLoading={isLoading}
        showUploadHint={!showUpload && !resumeContent}
        mockMode={mockMode}
      />
    </div>
    </div>
  );
}
