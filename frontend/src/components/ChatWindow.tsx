"use client";

import { useRef, useEffect } from "react";
import Image from "next/image";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageBubble, Message } from "./MessageBubble";
import { ThinkingAnimation } from "./ThinkingAnimation";
import { Loader2 } from "lucide-react";

interface ThinkingStep {
  id: string;
  icon: "brain" | "search" | "file" | "lightbulb" | "check";
  text: string;
  status: "pending" | "active" | "complete";
}

interface ChatWindowProps {
  messages: Message[];
  isLoading?: boolean;
  isThinking?: boolean;
  thinkingSteps?: ThinkingStep[];
}

export function ChatWindow({ 
  messages, 
  isLoading = false, 
  isThinking = false,
  thinkingSteps 
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading, isThinking, thinkingSteps]);

  return (
    <ScrollArea className="flex-1 min-h-0">
      <div className="max-w-3xl mx-auto p-4 space-y-4">
        {messages.length === 0 && !isLoading && !isThinking && (
          <div className="flex flex-col items-center justify-center h-[50vh] text-center space-y-6">
            <div className="relative">
              <Image
                src="/logo.png"
                alt="Candi"
                width={280}
                height={80}
                className="h-12 sm:h-16 md:h-20 w-auto opacity-90"
              />
              <div className="absolute -inset-4 rounded-full bg-gradient-to-br from-cyan-500/10 via-blue-500/10 to-indigo-500/10 blur-2xl -z-10" />
            </div>
            <div className="space-y-3 max-w-md">
              <p className="text-lg text-muted-foreground">
                Your AI-powered interview preparation assistant
              </p>
              <div className="flex flex-wrap justify-center gap-2 text-xs">
                <span className="px-3 py-1.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                  📄 Resume Analysis
                </span>
                <span className="px-3 py-1.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  🔍 Deep Research
                </span>
                <span className="px-3 py-1.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  💡 Smart Q&A
                </span>
              </div>
            </div>
          </div>
        )}

        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}

        {/* Thinking Animation with real-time steps */}
        <ThinkingAnimation isVisible={isThinking} steps={thinkingSteps} />

        {/* Simple loading indicator when not thinking */}
        {isLoading && !isThinking && (
          <div className="flex gap-3 p-4 rounded-2xl max-w-[85%] mr-auto bg-muted animate-pulse">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
              <Loader2 className="w-4 h-4 text-white animate-spin" />
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs opacity-70">Candi</span>
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 bg-cyan-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}
