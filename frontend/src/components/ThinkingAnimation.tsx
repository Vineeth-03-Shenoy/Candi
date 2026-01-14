"use client";

import { cn } from "@/lib/utils";
import { Brain, Search, FileText, Lightbulb, CheckCircle2 } from "lucide-react";

interface ThinkingStep {
  id: string;
  icon: "brain" | "search" | "file" | "lightbulb" | "check";
  text: string;
  status: "pending" | "active" | "complete";
}

interface ThinkingAnimationProps {
  isVisible: boolean;
  steps?: ThinkingStep[];
}

const defaultSteps: ThinkingStep[] = [
  { id: "1", icon: "file", text: "Analyzing your resume...", status: "pending" },
  { id: "2", icon: "search", text: "Researching company interview patterns...", status: "pending" },
  { id: "3", icon: "brain", text: "Identifying likely interview rounds...", status: "pending" },
  { id: "4", icon: "lightbulb", text: "Generating tailored questions...", status: "pending" },
  { id: "5", icon: "check", text: "Preparing your interview guide...", status: "pending" },
];

const iconMap = {
  brain: Brain,
  search: Search,
  file: FileText,
  lightbulb: Lightbulb,
  check: CheckCircle2,
};

export function ThinkingAnimation({ isVisible, steps }: ThinkingAnimationProps) {
  const displaySteps = steps || defaultSteps;

  if (!isVisible) return null;

  return (
    <div className="flex flex-col gap-2 p-4 rounded-2xl bg-muted/50 backdrop-blur-sm border border-border/50 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-2 mb-2">
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center">
          <Brain className="w-3.5 h-3.5 text-white animate-pulse" />
        </div>
        <span className="text-sm font-medium text-foreground/90">Candi is thinking...</span>
      </div>
      
      <div className="space-y-2 pl-2">
        {displaySteps.map((step) => {
          const Icon = iconMap[step.icon];
          return (
            <div
              key={step.id}
              className={cn(
                "flex items-center gap-3 text-sm transition-all duration-500",
                step.status === "pending" && "opacity-40",
                step.status === "active" && "opacity-100",
                step.status === "complete" && "opacity-70"
              )}
              style={{
                transform: step.status === "active" ? "translateX(4px)" : "translateX(0)",
              }}
            >
              <div
                className={cn(
                  "w-5 h-5 rounded-full flex items-center justify-center transition-all duration-300",
                  step.status === "pending" && "bg-muted-foreground/20",
                  step.status === "active" && "bg-gradient-to-br from-cyan-500 to-blue-600 scale-110",
                  step.status === "complete" && "bg-emerald-500/80"
                )}
              >
                <Icon
                  className={cn(
                    "w-3 h-3 transition-colors",
                    step.status === "active" && "text-white animate-pulse",
                    step.status === "complete" && "text-white",
                    step.status === "pending" && "text-muted-foreground/50"
                  )}
                />
              </div>
              <span
                className={cn(
                  "transition-colors duration-300",
                  step.status === "active" && "text-foreground font-medium",
                  step.status === "complete" && "text-emerald-400 line-through",
                  step.status === "pending" && "text-muted-foreground"
                )}
              >
                {step.text}
              </span>
              {step.status === "active" && (
                <div className="flex gap-0.5 ml-1">
                  <span className="w-1.5 h-1.5 bg-cyan-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
