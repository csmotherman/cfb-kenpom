"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getMeta, getPredictionsTrackRecord } from "@/lib/data";

type Summary = {
  correct: number;
  incorrect: number;
  graded: number;
  accuracy: number;
  mae: number | null;
  seasons: number;
};

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function PredictionsPerformanceSummary() {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const meta = await getMeta();
      const records = (
        await Promise.all(meta.rankingsYears.map((year) => getPredictionsTrackRecord(year)))
      ).filter((record): record is NonNullable<typeof record> => Boolean(record?.overall.graded));

      if (cancelled || records.length === 0) return;

      const graded = records.reduce((sum, record) => sum + record.overall.graded, 0);
      const correct = records.reduce((sum, record) => sum + record.overall.correct, 0);
      const maeWeighted = records.reduce(
        (sum, record) =>
          sum +
          (record.overall.avgAbsMarginError === null
            ? 0
            : record.overall.avgAbsMarginError * record.overall.graded),
        0,
      );
      const maeGraded = records.reduce(
        (sum, record) =>
          sum + (record.overall.avgAbsMarginError === null ? 0 : record.overall.graded),
        0,
      );

      setSummary({
        correct,
        incorrect: graded - correct,
        graded,
        accuracy: graded ? correct / graded : 0,
        mae: maeGraded ? maeWeighted / maeGraded : null,
        seasons: records.length,
      });
    })().catch(() => {
      if (!cancelled) setSummary(null);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  if (!summary) return null;

  return (
    <section className="prediction-performance-strip" aria-labelledby="predictionPerformanceTitle">
      <div className="prediction-performance-strip__intro">
        <span className="eyebrow">All-time model results</span>
        <div className="prediction-performance-strip__title-row">
          <h2 id="predictionPerformanceTitle">Prediction Performance</h2>
          <span className="prediction-performance-strip__sample">
            {summary.graded} graded game{summary.graded === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      <div className="prediction-performance-strip__stats">
        <div className="prediction-performance-strip__stat">
          <strong>{summary.correct}</strong>
          <span>Correct</span>
        </div>
        <div className="prediction-performance-strip__stat">
          <strong>{summary.incorrect}</strong>
          <span>Incorrect</span>
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
