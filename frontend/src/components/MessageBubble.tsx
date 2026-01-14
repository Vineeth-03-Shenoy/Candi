"use client";

import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-3 p-4 rounded-2xl max-w-[85%] animate-in fade-in slide-in-from-bottom-2 duration-300",
        isUser
          ? "ml-auto bg-primary text-primary-foreground"
          : "mr-auto bg-muted"
      )}
    >
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser
            ? "bg-primary-foreground/20"
            : "bg-gradient-to-br from-cyan-500 to-blue-600"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>
      <div className="flex flex-col gap-1 min-w-0 flex-1">
        <span className="text-xs opacity-70">
          {isUser ? "You" : "Candi"}
        </span>
        <div className={cn(
          "text-sm leading-relaxed prose prose-sm max-w-none",
          isUser ? "prose-invert" : "dark:prose-invert",
          // Custom styles for markdown elements
          "[&_p]:mb-2 [&_p:last-child]:mb-0",
          "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-4",
          "[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-4",
          "[&_li]:my-0.5",
          "[&_strong]:font-semibold",
          "[&_em]:italic",
          "[&_h1]:text-lg [&_h1]:font-bold [&_h1]:mb-2",
          "[&_h2]:text-base [&_h2]:font-bold [&_h2]:mb-2",
          "[&_h3]:text-sm [&_h3]:font-bold [&_h3]:mb-1",
          "[&_code]:bg-black/20 [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs",
          "[&_pre]:bg-black/20 [&_pre]:p-2 [&_pre]:rounded [&_pre]:overflow-x-auto",
          "[&_blockquote]:border-l-2 [&_blockquote]:border-primary/50 [&_blockquote]:pl-3 [&_blockquote]:italic",
        )}>
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
