"use client";

import { useState, useRef, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send, Paperclip, FileUp, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  onToggleUpload: () => void;
  isLoading?: boolean;
  showUploadHint?: boolean;
  mockMode?: boolean;
}

export function ChatInput({
  onSendMessage,
  onToggleUpload,
  isLoading = false,
  showUploadHint = false,
  mockMode = false,
}: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [attaching, setAttaching] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isLoading) {
      onSendMessage(message.trim());
      setMessage("");
    }
  };

  const handleFileAttach = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setAttaching(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/api/extract-text`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Failed to extract text");
      const data = await res.json();
      if (data.success) {
        const preview = data.text.slice(0, 3000);
        setMessage((prev) =>
          prev
            ? `${prev}\n\n[Attached: ${file.name}]\n${preview}${data.text.length > 3000 ? "\n...(truncated)" : ""}`
            : `[Attached: ${file.name}]\n${preview}${data.text.length > 3000 ? "\n...(truncated)" : ""}`
        );
      }
    } catch {
      // silently fail
    } finally {
      setAttaching(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="border-t bg-background/80 backdrop-blur-xl p-4">
      <form
        onSubmit={handleSubmit}
        className="max-w-3xl mx-auto flex items-center gap-2"
      >
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onToggleUpload}
          className={cn(
            "flex-shrink-0 relative",
            showUploadHint && "text-primary"
          )}
        >
          <Paperclip className="w-5 h-5" />
          {showUploadHint && (
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-primary rounded-full animate-pulse" />
          )}
        </Button>

        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => fileRef.current?.click()}
          disabled={isLoading || attaching}
          className="flex-shrink-0 text-muted-foreground hover:text-foreground"
          title="Attach a file for context"
        >
          {attaching ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <FileUp className="w-4 h-4" />
          )}
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.pdf"
          onChange={handleFileAttach}
          className="hidden"
        />

        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={mockMode ? "Type your answer to the interviewer..." : "Ask about interview preparation..."}
          disabled={isLoading}
          className={cn(
            "flex-1 bg-muted/50 border-0 focus-visible:ring-1",
            mockMode
              ? "focus-visible:ring-amber-500 border-amber-500/30"
              : "focus-visible:ring-primary"
          )}
        />

        <Button
          type="submit"
          size="icon"
          disabled={!message.trim() || isLoading}
          className="flex-shrink-0 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-600 hover:to-blue-700 transition-all text-white"
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Send className="w-4 h-4" />
          )}
        </Button>
      </form>
    </div>
  );
}
