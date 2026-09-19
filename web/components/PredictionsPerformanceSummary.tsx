"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getMeta, getPredictionsTrackRecord, getPreseasonPower } from "@/lib/data";

type Summary = {
  correct: number;
  incorrect: number;
  graded: number;
  accuracy: number;
  mae: number | null;
  sinceYear: number | null;
  backtestGames: number;
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
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const predictionYears = meta.predictionYears?.length ? meta.predictionYears : [latestSeason];
      const [records, power] = await Promise.all([
        Promise.all(predictionYears.map((year) => getPredictionsTrackRecord(year))).then((rows) =>
          rows.filter((record): record is NonNullable<typeof record> => Boolean(record?.overall.graded)),
        ),
        getPreseasonPower(latestSeason).catch(() => null),
      ]);

      if (cancelled) return;

      let graded = records.reduce((sum, record) => sum + record.overall.graded, 0);
      let correct = records.reduce((sum, record) => sum + record.overall.correct, 0);
      let maeWeighted = records.reduce(
        (sum, record) =>
          sum +
          (record.overall.avgAbsMarginError === null
            ? 0
            : record.overall.avgAbsMarginError * record.overall.graded),
        0,
      );
      let maeGraded = records.reduce(
        (sum, record) =>
          sum + (record.overall.avgAbsMarginError === null ? 0 : record.overall.graded),
        0,
      );

      // The graded weekly-picks product only started in 2026, so that's all
      // `records` above can ever cover. The only pre-2026 evidence this model
      // has is its own frozen leakage-safe Week 2 walk-forward backtest run
      // against every earlier COMPLETE_SEASON -- narrower than a full season
      // of live picks (Week 2 only), so it's called out by count rather than
      // silently blended in as if it were the same kind of sample.
      const backtest = power?.backtest ?? null;
      const backtestGames = backtest?.n ?? 0;
      if (backtest && backtestGames > 0) {
        const backtestCorrect = Math.round((backtest.winnerPct / 100) * backtestGames);
        graded += backtestGames;
        correct += backtestCorrect;
        maeWeighted += backtest.mae * backtestGames;
        maeGraded += backtestGames;
      }

      if (graded === 0) return;

      setSummary({
        correct,
        incorrect: graded - correct,
        graded,
        accuracy: graded ? correct / graded : 0,
        mae: maeGraded ? maeWeighted / maeGraded : null,
        sinceYear: backtestGames > 0 ? meta.rankingsYears[0] ?? null : null,
        backtestGames,
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
