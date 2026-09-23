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
      <span className="prediction-performance-strip__icon" aria-hidden="true"><i /><i /><i /></span>
      <h2 id="predictionPerformanceTitle">Model record</h2>
      <p>
        <strong>{summary.correct}-{summary.incorrect}</strong>
        <span aria-hidden="true">·</span>
        <strong>{percent(summary.accuracy)}</strong> winners
        <span aria-hidden="true">·</span>
        <strong>{summary.mae === null ? "—" : summary.mae.toFixed(1)}</strong> margin MAE
      </p>

      <Link className="prediction-performance-strip__link" href="/predictions/performance">
        Performance <span aria-hidden="true">→</span>
      </Link>
    </section>
  );
}
