"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getMeta, getPredictionsTrackRecord } from "@/lib/data";
import { buildPerformanceSummary, type PerformanceSummary as Summary } from "@/lib/performanceSummary";

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

/** `initial` is computed on the server; when it is provided (even as null = nothing graded yet) nothing is fetched. */
export default function PredictionsPerformanceSummary({ initial }: { initial?: Summary | null }) {
  const [summary, setSummary] = useState<Summary | null>(initial ?? null);

  useEffect(() => {
    if (initial !== undefined) return;
    let cancelled = false;

    (async () => {
      const meta = await getMeta();
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const predictionYears = meta.predictionYears?.length ? meta.predictionYears : [latestSeason];
      const records = await Promise.all(predictionYears.map((year) => getPredictionsTrackRecord(year))).then((rows) =>
        rows.filter((record): record is NonNullable<typeof record> => Boolean(record?.overall.graded)),
      );
      if (cancelled) return;
      setSummary(buildPerformanceSummary(records));
    })().catch(() => {
      if (!cancelled) setSummary(null);
    });

    return () => {
      cancelled = true;
    };
  }, [initial]);

  if (!summary) return null;

  return (
    <section className="prediction-performance-strip" aria-labelledby="predictionPerformanceTitle">
      <div className="prediction-performance-strip__intro">
        <span className="eyebrow">
          All-time model results{summary.sinceYear ? ` · ${summary.sinceYear}–Present` : null}
        </span>
        <div className="prediction-performance-strip__title-row">
          <h2 id="predictionPerformanceTitle">Prediction Performance</h2>
          <span className="prediction-performance-strip__sample">
            {summary.graded} graded game{summary.graded === 1 ? "" : "s"}
          </span>
        </div>
        {summary.backtestGames > 0 ? (
          <p className="prediction-performance-strip__note">
            Includes {summary.backtestGames} Week 2 walk-forward backtest games from {summary.sinceYear}&ndash;2025 (weekly
            graded picks began in 2026).
          </p>
        ) : null}
      </div>

      <div className="prediction-performance-strip__stats">
        <div className="prediction-performance-strip__stat prediction-performance-strip__stat--record">
          <strong>{summary.correct}-{summary.incorrect}</strong>
          <span>All-time record</span>
        </div>
        <div className="prediction-performance-strip__stat">
          <strong>{percent(summary.accuracy)}</strong>
          <span>Winner accuracy</span>
        </div>
        <div className="prediction-performance-strip__stat">
          <strong>{summary.mae === null ? "—" : summary.mae.toFixed(1)}</strong>
          <span>Margin MAE</span>
        </div>
      </div>

      <Link className="prediction-performance-strip__link" href="/predictions/performance">
        Detailed performance <span aria-hidden="true">→</span>
      </Link>
    </section>
  );
}
