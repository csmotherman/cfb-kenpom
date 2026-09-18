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

export default function LeilaLoadingState({
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
      className={`leila-loader${compact ? " leila-loader--compact" : ""}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="leila-loader__top">
        <span className="leila-loader__eyebrow">LEILA LIVE</span>
        <strong>{COPY[variant].title}</strong>
        <p>{COPY[variant].detail}</p>
      </div>

      <div className="leila-loader__drive" aria-hidden="true">
        <span className="leila-loader__endzone">0</span>
        <span className="leila-loader__yard leila-loader__yard--20" />
        <span className="leila-loader__yard leila-loader__yard--40" />
        <span className="leila-loader__yard leila-loader__yard--60" />
        <span className="leila-loader__yard leila-loader__yard--80" />
        <span className="leila-loader__endzone leila-loader__endzone--right">100</span>
        <span className="leila-loader__football">
          <i />
        </span>
      </div>

      {!compact ? (
        <div className="leila-loader__skeleton" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <div className="leila-loader__card" key={index}>
              <span className="leila-loader__block leila-loader__block--time" />
              <span className="leila-loader__teams">
                <i className="leila-loader__logo" />
                <span className="leila-loader__block leila-loader__block--team" />
                <b />
                <span className="leila-loader__block leila-loader__block--team" />
                <i className="leila-loader__logo" />
              </span>
              <span className="leila-loader__block leila-loader__block--pick" />
            </div>
          ))}
        </div>
      ) : null}

      <div className="leila-loader__status">
        <span className="leila-loader__pulse" aria-hidden="true" />
        <span>{status}</span>
      </div>

      {elapsed >= 12 ? (
        <button type="button" className="leila-loader__reload" onClick={() => window.location.reload()}>
          Reload page
        </button>
      ) : null}
    </section>
  );
}
