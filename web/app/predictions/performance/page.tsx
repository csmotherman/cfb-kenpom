"use client";

import { useEffect, useMemo, useState } from "react";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import PrimeLoadingState from "@/components/PrimeLoadingState";
import { getMeta, getPredictionsTrackRecord } from "@/lib/data";
import type { PredictionsTrackRecord, PredictionRecordStats } from "@/lib/types";

function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function points(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1)}`;
}

function record(stats: PredictionRecordStats): string {
  return `${stats.correct}–${stats.graded - stats.correct}`;
}

export default function PredictionPerformancePage() {
  const [records, setRecords] = useState<PredictionsTrackRecord[]>([]);
  const [season, setSeason] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const meta = await getMeta();
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const predictionYears = meta.predictionYears?.length ? meta.predictionYears : [latestSeason];
      const loaded = (
        await Promise.all(predictionYears.map((year) => getPredictionsTrackRecord(year)))
      )
        .filter((item): item is PredictionsTrackRecord => Boolean(item))
        .sort((a, b) => b.season - a.season);

      if (cancelled) return;
      setRecords(loaded);
      setSeason(loaded[0]?.season ?? null);
      setLoading(false);
    })().catch(() => {
      if (!cancelled) setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const active = useMemo(
    () => records.find((item) => item.season === season) ?? records[0] ?? null,
    [records, season],
  );

  useEffect(() => {
    document.title = active
      ? `${active.season} Prediction Performance | PRIME Football`
      : "Prediction Performance | PRIME Football";
  }, [active]);

  return (
    <>
      <a className="skip-link" href="#performanceContent">Skip to performance</a>
      <SiteHeader tagline="Prediction Model Performance" />
      <SiteNav />

      <main id="performanceContent" className="container prediction-performance-page">
        {loading ? (
          <PrimeLoadingState variant="predictions" />
        ) : !active ? (
          <p className="network-loading">
            Prediction performance will appear after the first frozen picks have final scores to grade.
          </p>
        ) : (
          <>
            <header className="prediction-performance-page__header">
              <div>
                <span className="eyebrow">Transparent model grading</span>
                <h1>Model Performance</h1>
                <p>
                  Every result comes from a frozen pregame prediction matched to the final score.
                  No current ratings are used to rewrite old picks.
                </p>
              </div>

              {records.length > 1 ? (
                <label className="prediction-performance-page__season">
                  <span>Season</span>
                  <select value={active.season} onChange={(event) => setSeason(Number(event.target.value))}>
                    {records.map((item) => (
                      <option key={item.season} value={item.season}>{item.season}</option>
                    ))}
                  </select>
                </label>
              ) : (
                <span className="prediction-performance-page__season-pill">{active.season} season</span>
              )}
            </header>

            <section className="prediction-performance-kpis" aria-label="Season summary">
              <div><strong>{record(active.overall)}</strong><span>Correct–incorrect</span></div>
              <div><strong>{pct(active.overall.accuracySU)}</strong><span>Winner accuracy</span></div>
              <div><strong>{points(active.overall.avgAbsMarginError)}</strong><span>Margin MAE</span></div>
              <div><strong>{active.overall.graded}</strong><span>Graded games</span></div>
            </section>

            <section className="prediction-performance-errors" aria-labelledby="errorTitle">
              <div className="prediction-performance-section-heading">
                <div>
                  <span className="eyebrow">Error distribution</span>
                  <h2 id="errorTitle">How close were the projected margins?</h2>
                </div>
                <span className="prediction-performance-model-id">{active.modelVersion}</span>
              </div>
              <div className="prediction-performance-errors__grid">
                <div><strong>{points(active.overall.medianAbsMarginError)}</strong><span>Median error</span></div>
                <div><strong>{pct(active.overall.within3Pct)}</strong><span>Within 3 pts</span></div>
                <div><strong>{pct(active.overall.within7Pct)}</strong><span>Within 7 pts</span></div>
                <div><strong>{pct(active.overall.within10Pct)}</strong><span>Within 10 pts</span></div>
                <div><strong>{pct(active.overall.within14Pct)}</strong><span>Within 14 pts</span></div>
              </div>
            </section>

            <PerformanceTable
              title="By week"
              eyebrow="Weekly grading"
              headers={["Week", "Record", "Accuracy", "MAE", "Median error", "Games"]}
              rows={active.weeks.map((week) => [
                `Week ${week.week}`,
                week.graded ? record(week) : "Not graded",
                pct(week.accuracySU),
                points(week.avgAbsMarginError),
                points(week.medianAbsMarginError),
                String(week.graded),
              ])}
            />

            {active.conferences?.length ? (
              <PerformanceTable
                title="By conference"
                eyebrow="Games involving each conference"
                note="Nonconference games appear in each participating conference's sample, so conference game counts do not sum to the overall total."
                headers={["Conference", "Record", "Accuracy", "MAE", "Median error", "Games"]}
                rows={active.conferences.map((conference) => [
                  conference.conference,
                  conference.graded ? record(conference) : "—",
                  pct(conference.accuracySU),
                  points(conference.avgAbsMarginError),
                  points(conference.medianAbsMarginError),
                  String(conference.graded),
                ])}
              />
            ) : null}

            {active.confidenceBuckets?.some((bucket) => bucket.graded > 0) ? (
              <PerformanceTable
                title="Confidence calibration"
                eyebrow="Predicted probability vs. reality"
                note="A well-calibrated model should have actual win rate track closely with average predicted confidence inside each bucket."
                headers={["Confidence", "Avg predicted", "Actual win rate", "Gap", "Record", "Games"]}
                rows={active.confidenceBuckets
                  .filter((bucket) => bucket.games > 0)
                  .map((bucket) => [
                    bucket.label,
                    pct(bucket.avgConfidence),
                    pct(bucket.actualWinRate),
                    bucket.calibrationGap === null
                      ? "—"
                      : `${bucket.calibrationGap >= 0 ? "+" : ""}${(bucket.calibrationGap * 100).toFixed(1)} pp`,
                    bucket.graded ? `${bucket.correct}–${bucket.graded - bucket.correct}` : "—",
                    String(bucket.graded),
                  ])}
              />
            ) : null}

            {active.marginBuckets?.length ? (
              <PerformanceTable
                title="By projected margin"
                eyebrow="Prediction strength"
                note="This shows whether PRIME is more reliable on close calls or on games where the model sees a larger separation."
                headers={["Projected edge", "Record", "Accuracy", "MAE", "Within 7", "Games"]}
                rows={active.marginBuckets.map((bucket) => [
                  bucket.label,
                  bucket.graded ? record(bucket) : "—",
                  pct(bucket.accuracySU),
                  points(bucket.avgAbsMarginError),
                  pct(bucket.within7Pct),
                  String(bucket.graded),
                ])}
              />
            ) : null}

            <p className="prediction-performance-page__method-note">
              Straight-up winner accuracy is not against the spread. Margin MAE is the mean absolute
              difference between PRIME’s predicted home margin and the final home margin. Ties and games
              without verifiable final scores are excluded from grading.
            </p>
          </>
        )}
      </main>

      <SiteFooter note="Prediction performance is graded from frozen pregame model outputs and final scores. Historical results are descriptive, not betting advice." />
    </>
  );
}

function PerformanceTable({
  title,
  eyebrow,
  headers,
  rows,
  note,
}: {
  title: string;
  eyebrow: string;
  headers: string[];
  rows: string[][];
  note?: string;
}) {
  return (
    <section className="prediction-performance-section">
      <div className="prediction-performance-section-heading">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
      </div>
      <div className="prediction-performance-table-wrap" role="region" aria-label={title} tabIndex={0}>
        <table className="prediction-performance-table">
          <thead>
            <tr>
              {headers.map((header, index) => (
                <th key={header} scope="col" className={index === 0 ? "" : "num"}>{header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`${title}-${rowIndex}`}>
                {row.map((cell, cellIndex) =>
                  cellIndex === 0 ? <th key={cellIndex} scope="row">{cell}</th> : <td key={cellIndex} className="num">{cell}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {note ? <p className="prediction-performance-section__note">{note}</p> : null}
    </section>
  );
}
