"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface FlashCard {
  question: string;
  answer: string;
}

interface FlashcardsProps {
  cards: FlashCard[];
  onClose: () => void;
}

export function Flashcards({ cards, onClose }: FlashcardsProps) {
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);

  if (!cards.length) return null;

  const card = cards[index];
  const next = () => { setIndex((i) => (i + 1) % cards.length); setFlipped(false); };
  const prev = () => { setIndex((i) => (i - 1 + cards.length) % cards.length); setFlipped(false); };
  const flip = () => setFlipped((f) => !f);

  return (
    <div className="flex-shrink-0 border-b bg-muted/30 p-4 animate-in slide-in-from-top duration-300">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-medium">
            Flashcards ({index + 1}/{cards.length})
          </h2>
          <Button variant="ghost" size="sm" className="h-6 text-xs" onClick={onClose}>
            Close
          </Button>
        </div>

        <div
          className="relative cursor-pointer rounded-xl border bg-card p-6 min-h-[180px] flex flex-col items-center justify-center text-center transition-all duration-300 hover:shadow-lg"
          onClick={flip}
          style={{ perspective: "1000px" }}
        >
          <div
            className={cn(
              "transition-all duration-300 w-full",
              flipped ? "opacity-0" : "opacity-100"
            )}
          >
            <p className="text-xs text-muted-foreground mb-2">Question</p>
            <p className="text-sm font-medium">{card.question}</p>
            <p className="text-xs text-muted-foreground mt-4">Tap to reveal answer</p>
          </div>

          <div
            className={cn(
              "absolute inset-0 transition-all duration-300 p-6 flex items-center justify-center text-center",
              flipped ? "opacity-100" : "opacity-0 pointer-events-none"
            )}
          >
            <p className="text-xs text-left whitespace-pre-line leading-relaxed">
              {card.answer}
            </p>
          </div>
        </div>

        <div className="flex items-center justify-center gap-2 mt-3">
          <Button variant="outline" size="icon" className="h-7 w-7" onClick={prev}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={flip}>
            <RotateCw className="w-3 h-3" />
            Flip
          </Button>
          <Button variant="outline" size="icon" className="h-7 w-7" onClick={next}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
