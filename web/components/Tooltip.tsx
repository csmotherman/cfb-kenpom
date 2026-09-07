"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";

type TipState = { text: string; rect: DOMRect } | null;

const TooltipCtx = createContext<{
  show: (el: HTMLElement, text: string) => void;
  hide: () => void;
  togglePinned: (el: HTMLElement, text: string) => void;
} | null>(null);

export function TooltipProvider({ children }: { children: React.ReactNode }) {
  const [tip, setTip] = useState<TipState>(null);
  const pinnedRef = useRef(false);
  const currentElRef = useRef<HTMLElement | null>(null);
  const bubbleRef = useRef<HTMLDivElement>(null);

  const show = useCallback((el: HTMLElement, text: string) => {
    currentElRef.current = el;
    setTip({ text, rect: el.getBoundingClientRect() });
  }, []);

  const hide = useCallback(() => {
    pinnedRef.current = false;
    currentElRef.current = null;
    setTip(null);
  }, []);

  const togglePinned = useCallback(
    (el: HTMLElement, text: string) => {
      if (pinnedRef.current && currentElRef.current === el) {
        hide();
        return;
      }
      show(el, text);
      pinnedRef.current = true;
    },
    [hide, show]
  );

  useEffect(() => {
    function onScroll() {
      if (currentElRef.current) {
        setTip((t) => (t ? { ...t, rect: currentElRef.current!.getBoundingClientRect() } : t));
      }
    }
    function onKeydown(e: KeyboardEvent) {
      if (e.key === "Escape") hide();
    }
    function onDocClick(e: MouseEvent) {
      if (!pinnedRef.current) return;
      const target = e.target as HTMLElement;
      if (bubbleRef.current?.contains(target)) return;
      if (target.closest("[data-tip-trigger]")) return;
      hide();
    }
    window.addEventListener("scroll", onScroll, true);
    document.addEventListener("keydown", onKeydown);
    document.addEventListener("click", onDocClick);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("keydown", onKeydown);
      document.removeEventListener("click", onDocClick);
    };
  }, [hide]);

  const [pos, setPos] = useState({ left: 0, top: 0 });

  // Position depends on the bubble's own rendered width, so it can only be
  // measured after the bubble (with its new text) has painted.
  useLayoutEffect(() => {
    if (!tip || !bubbleRef.current) return;
    const bw = bubbleRef.current.offsetWidth;
    let left = tip.rect.left + tip.rect.width / 2 - bw / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
    setPos({ left, top: tip.rect.bottom + 8 });
  }, [tip]);

  return (
    <TooltipCtx.Provider value={{ show, hide, togglePinned }}>
      {children}
      <div
        ref={bubbleRef}
        className="tip-bubble"
        hidden={!tip}
        style={tip ? pos : undefined}
      >
        {tip?.text}
      </div>
    </TooltipCtx.Provider>
  );
}

export function TipTrigger({ text }: { text: string }) {
  const ctx = useContext(TooltipCtx);
  if (!ctx) return null;
  return (
    <span
      className="tip-trigger"
      data-tip-trigger="1"
      tabIndex={0}
      role="button"
      aria-label="Explain this metric"
      onMouseEnter={(e) => ctx.show(e.currentTarget, text)}
      onMouseLeave={() => ctx.hide()}
      onClick={(e) => {
        e.stopPropagation();
        ctx.togglePinned(e.currentTarget, text);
      }}
    >
      ?
    </span>
  );
}
