"use client";

import { useState, useCallback, useRef } from "react";
import Image from "next/image";
import { ChatWindow } from "@/components/ChatWindow";
import { ChatInput } from "@/components/ChatInput";
import { FileUpload } from "@/components/FileUpload";
import { ThinkingAnimation } from "@/components/ThinkingAnimation";
import { Message } from "@/components/MessageBubble";
import { Button } from "@/components/ui/button";
import { X, Rocket, Download } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ThinkingStep {
  id: string;
  icon: "brain" | "search" | "file" | "lightbulb" | "check";
  text: string;
  status: "pending" | "active" | "complete";
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isThinking, setIsThinking] = useState(false);
  const [showUpload, setShowUpload] = useState(true);
  const [resumeContent, setResumeContent] = useState("");
  const [jdContent, setJdContent] = useState("");
  const [pdfPath, setPdfPath] = useState<string | null>(null);
  const [thinkingSteps, setThinkingSteps] = useState<ThinkingStep[]>([
    { id: "1", icon: "file", text: "Analyzing your resume...", status: "pending" },
    { id: "2", icon: "file", text: "Analyzing job description...", status: "pending" },
    { id: "3", icon: "search", text: "Researching company interview patterns...", status: "pending" },
    { id: "4", icon: "brain", text: "Identifying likely interview rounds...", status: "pending" },
    { id: "5", icon: "lightbulb", text: "Creating preparation strategy...", status: "pending" },
    { id: "6", icon: "lightbulb", text: "Generating tailored questions...", status: "pending" },
    { id: "7", icon: "check", text: "Preparing your interview guide...", status: "pending" },
  ]);
  const sessionIdRef = useRef(`session_${Date.now()}`);

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
      if (index + 1 === stepNumber) {
        return { ...step, status };
      }
      if (index + 1 < stepNumber && status === "active") {
        return { ...step, status: "complete" };
      }
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
          resume_text: resumeContent,
          jd_text: jdContent,
          session_id: sessionIdRef.current,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to prepare interview guide");
      }

      // Handle SSE stream
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                
                if (data.step === 'error') {
                  throw new Error(data.message);
                }
                
                if (data.step === 'complete') {
                  setIsThinking(false);
                  setPdfPath(data.pdf_path);
                  addMessage("assistant", data.summary);
                } else if (typeof data.step === 'number') {
                  updateThinkingStep(data.step, data.status);
                }
              } catch (e) {
                // Skip malformed JSON
              }
            }
          }
        }
      }
    } catch (error) {
      console.error("Error:", error);
      setIsThinking(false);
      addMessage(
        "assistant",
        "I apologize, but I encountered an error while processing your request. Please make sure the backend server is running and try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (content: string) => {
    addMessage("user", content);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: content,
          session_id: sessionIdRef.current,
          resume_text: resumeContent || undefined,
          jd_text: jdContent || undefined,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const data = await response.json();
      
      if (data.action === "redirect_to_prepare" && resumeContent && jdContent) {
        // Trigger full preparation
        handleStartPreparation();
      } else {
        addMessage("assistant", data.response);
      }
    } catch (error) {
      console.error("Error:", error);
      addMessage(
        "assistant",
        "I'm having trouble connecting to the server. Please make sure the backend is running at " + API_URL
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleUpload = () => {
    setShowUpload((prev) => !prev);
  };

  const handleDownloadPdf = () => {
    if (pdfPath) {
      // Handle both Windows (backslash) and Unix (forward slash) paths
      const parts = pdfPath.replace(/\\/g, '/').split('/');
      const filename = parts[parts.length - 1];
      window.open(`${API_URL}/api/download/${filename}`, '_blank');
    }
  };

  const canStart = resumeContent && jdContent;

  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">
      {/* Header - Fixed */}
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
          <div className="flex items-center gap-2">
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

      {/* Upload Panel - Fixed when visible */}
      {showUpload && (
        <div className="flex-shrink-0 border-b bg-muted/30 p-4 animate-in slide-in-from-top duration-300">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-medium">Upload Documents</h2>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setShowUpload(false)}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <FileUpload
                type="resume"
                label="Your Resume"
                onFileUploaded={setResumeContent}
              />
              <FileUpload
                type="jd"
                label="Job Description"
                onFileUploaded={setJdContent}
              />
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

      {/* Chat Area - Scrollable (takes remaining space) */}
      <ChatWindow 
        messages={messages} 
        isLoading={isLoading && !isThinking} 
        isThinking={isThinking}
        thinkingSteps={thinkingSteps}
      />

      {/* Input - Fixed at bottom */}
      <ChatInput
        onSendMessage={handleSendMessage}
        onToggleUpload={handleToggleUpload}
        isLoading={isLoading}
        showUploadHint={!showUpload && !resumeContent}
      />
    </div>
  );
}
