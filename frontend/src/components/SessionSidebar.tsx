"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Plus, MessageSquare, FileText, Trash2, PanelLeftClose } from "lucide-react";
import { cn } from "@/lib/utils";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SessionMeta {
  session_id: string;
  updated_at: number;
  has_prep: boolean;
  message_count: number;
  token_usage: { total_tokens: number };
  has_pdf: boolean;
  display_name: string;
}

interface SessionSidebarProps {
  activeSessionId: string;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onClose: () => void;
}

export function SessionSidebar({
  activeSessionId,
  onSelectSession,
  onNewSession,
  onClose,
}: SessionSidebarProps) {
  const [sessions, setSessions] = useState<SessionMeta[]>([]);

  const loadSessions = async () => {
    try {
      const res = await fetch(`${API_URL}/api/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch {}
  };

  useEffect(() => {
    loadSessions();
  }, [activeSessionId]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    try {
      await fetch(`${API_URL}/api/session/${sessionId}`, { method: "DELETE" });
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch {}
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 86400000) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diff < 604800000) return d.toLocaleDateString([], { weekday: "short" });
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  };

  return (
    <div className="w-72 border-r bg-muted/20 flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-3 border-b">
        <h2 className="text-sm font-semibold">Conversations</h2>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onNewSession} title="New session">
            <Plus className="w-4 h-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose} title="Close sidebar">
            <PanelLeftClose className="w-4 h-4" />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.session_id}
              onClick={() => onSelectSession(s.session_id)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === "Enter") onSelectSession(s.session_id); }}
              className={cn(
                "w-full text-left px-3 py-2 rounded-lg text-xs transition-colors group cursor-pointer",
                s.session_id === activeSessionId
                  ? "bg-primary/10 border border-primary/30"
                  : "hover:bg-muted border border-transparent"
              )}
            >
              <div className="flex items-start gap-2">
                {s.has_prep ? (
                  <FileText className="w-4 h-4 mt-0.5 shrink-0 text-cyan-400" />
                ) : (
                  <MessageSquare className="w-4 h-4 mt-0.5 shrink-0 text-muted-foreground" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">
                    {s.display_name || "New conversation"}
                  </p>
                  <div className="flex items-center gap-2 mt-0.5 text-[10px] text-muted-foreground">
                    <span>{s.message_count} msgs</span>
                    {s.token_usage?.total_tokens > 0 && (
                      <span>
                        {s.token_usage.total_tokens >= 1000
                          ? `${(s.token_usage.total_tokens / 1000).toFixed(1)}K tokens`
                          : `${s.token_usage.total_tokens} tokens`}
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {formatTime(s.updated_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(e, s.session_id)}
                  className="p-1 rounded hover:bg-destructive/10"
                  title="Delete session"
                >
                  <Trash2 className="w-3 h-3 text-muted-foreground/50 hover:text-destructive" />
                </button>
              </div>
            </div>
          ))}

          {sessions.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-8">
              No conversations yet
            </p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
