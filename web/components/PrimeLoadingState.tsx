"use client";

import { useEffect, useState } from "react";

type LoaderVariant = "predictions" | "matchup" | "archive";

const COPY: Record<LoaderVariant, { title: string; detail: string }> = {
  predictions: {
    title: "Setting this week’s board",
    detail: "Loading the schedule, ratings, predictions and market context.",
  },
  matchup: {
    title: "Building the matchup",
    detail: "Loading the pregame snapshot, team profiles and model context.",
  },
  archive: {
    title: "Opening the game archive",
    detail: "Loading completed games and team history.",
  },
};

export default function PrimeLoadingState({
  variant = "predictions",
  compact = false,
}: {
  variant?: LoaderVariant;
  compact?: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - started) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const status =
    elapsed >= 12
      ? "Taking longer than usual — we’re still trying."
      : elapsed >= 5
        ? "Still working — the latest data can take a few seconds."
        : "Loading live data…";

  return (
    <section
      className={`prime-loader${compact ? " prime-loader--compact" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="prime-loader__top">
        <span className="prime-loader__eyebrow">PRIME LIVE</span>
        <strong>{COPY[variant].title}</strong>
        <p>{COPY[variant].detail}</p>
      </div>

      <div className="prime-loader__drive" aria-hidden="true">
        <span className="prime-loader__endzone">0</span>
        <span className="prime-loader__yard prime-loader__yard--20" />
        <span className="prime-loader__yard prime-loader__yard--40" />
        <span className="prime-loader__yard prime-loader__yard--60" />
        <span className="prime-loader__yard prime-loader__yard--80" />
        <span className="prime-loader__endzone prime-loader__endzone--right">100</span>
        <span className="prime-loader__football">
          <i />
        </span>
      </div>

      {!compact ? (
        <div className="prime-loader__skeleton" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <div className="prime-loader__card" key={index}>
              <span className="prime-loader__block prime-loader__block--time" />
              <span className="prime-loader__teams">
                <i className="prime-loader__logo" />
                <span className="prime-loader__block prime-loader__block--team" />
                <b />
                <span className="prime-loader__block prime-loader__block--team" />
                <i className="prime-loader__logo" />
              </span>
              <span className="prime-loader__block prime-loader__block--pick" />
            </div>
          ))}
        </div>
      ) : null}

      <div className="prime-loader__status">
        <span className="prime-loader__pulse" aria-hidden="true" />
        <span>{status}</span>
      </div>

      {elapsed >= 12 ? (
        <button type="button" className="prime-loader__reload" onClick={() => window.location.reload()}>
          Reload page
        </button>
      ) : null}
    </section>
  );
}
