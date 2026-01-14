"use client";

import { useState, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Send, Paperclip, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  onToggleUpload: () => void;
  isLoading?: boolean;
  showUploadHint?: boolean;
}

export function ChatInput({
  onSendMessage,
  onToggleUpload,
  isLoading = false,
  showUploadHint = false,
}: ChatInputProps) {
  const [message, setMessage] = useState("");

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isLoading) {
      onSendMessage(message.trim());
      setMessage("");
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

        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask about interview preparation..."
          disabled={isLoading}
          className="flex-1 bg-muted/50 border-0 focus-visible:ring-1 focus-visible:ring-primary"
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
