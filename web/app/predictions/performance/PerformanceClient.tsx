"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
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

const MODEL_NAMES: Record<string, string> = {
  "early-season-blend-2026-v1": "Early-season blend (retired; used preseason power)",
  "aggregate-advanced-2026-v1": "Aggregate advanced model (from Week 6)",
};

function record(stats: PredictionRecordStats): string {
  return `${stats.correct}–${stats.graded - stats.correct}`;
}

export default function PerformanceClient({ seoLede }: { seoLede?: ReactNode }) {
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

  return (
    <>
      <a className="skip-link" href="#performanceContent">Skip to performance</a>
      <SiteHeader tagline="Prediction Model Performance" />
      <SiteNav />

      <main id="performanceContent" className="container prediction-performance-page">
        {loading ? (
          <>
            {seoLede ?? <h1 className="sr-only">Prediction Model Performance</h1>}
            <PrimeLoadingState variant="predictions" />
          </>
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
                <div><strong>{points(active.overall.rmse)}</strong><span>RMSE</span></div>
                <div><strong>{pct(active.overall.within3Pct)}</strong><span>Within 3 pts</span></div>
                <div><strong>{pct(active.overall.within7Pct)}</strong><span>Within 7 pts</span></div>
                <div><strong>{pct(active.overall.within10Pct)}</strong><span>Within 10 pts</span></div>
                <div><strong>{pct(active.overall.within14Pct)}</strong><span>Within 14 pts</span></div>
              </div>
            </section>

            {active.models?.length ? (
              <PerformanceTable
                title="By model"
                eyebrow="Live picks, split by the model that made them"
                note="Weeks 1-3 were picked by the early-season blend, which used preseason information and has been retired. Week 4 onward is picked by the aggregate model, which uses current-season games only. Each model is graded only on its own frozen picks."
                headers={["Model", "Weeks", "Record", "Accuracy", "MAE", "RMSE", "Games"]}
                rows={active.models.map((model) => [
                  MODEL_NAMES[model.modelVersion] ?? model.modelVersion,
                  model.weeks[0] === model.weeks[1] ? String(model.weeks[0]) : `${model.weeks[0]}–${model.weeks[1]}`,
                  model.graded ? record(model) : "Not graded",
                  pct(model.accuracySU),
                  points(model.avgAbsMarginError),
                  points(model.rmse),
                  String(model.graded),
                ])}
              />
            ) : null}

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

            {active.market || active.marketBacktest ? (
              <>
                {active.market ? (
                  <PerformanceTable
                    title={`Against the market, ${active.season} so far`}
                    eyebrow="Live picks vs the betting line"
                    note={`${active.market.note} ${active.market.games} graded picks have a line, so treat these figures as early and noisy.`}
                    headers={["Measure", "PRIME", "Market"]}
                    rows={[
                      ["Winner accuracy", pct(active.market.primeSU), pct(active.market.marketSU)],
                      ["Margin MAE", points(active.market.primeMAE), points(active.market.marketMAE)],
                    ]}
                  />
                ) : null}
                {active.marketBacktest ? (
                  <>
                    <PerformanceTable
                      title="Against the market, historical backtest"
                      eyebrow={`Walk-forward, ${active.marketBacktest.seasons[0]}–${active.marketBacktest.seasons[active.marketBacktest.seasons.length - 1]}, ${active.marketBacktest.games.toLocaleString()} games`}
                      note={`${active.marketBacktest.method} The closing line was more accurate than PRIME on every measure here; the differences are statistically clear (95% intervals exclude zero for accuracy, margin error and log loss).`}
                      headers={["Measure", "PRIME", "Market", "PRIME minus market (95% range)"]}
                      rows={[
                        ["Winner accuracy", pct(active.marketBacktest.suPrime), pct(active.marketBacktest.suMarket), `${(active.marketBacktest.suDiff.diff * 100).toFixed(1)} pp (${(active.marketBacktest.suDiff.ci_lo * 100).toFixed(1)} to ${(active.marketBacktest.suDiff.ci_hi * 100).toFixed(1)})`],
                        ["Margin MAE", points(active.marketBacktest.maePrime), points(active.marketBacktest.maeMarket), `${active.marketBacktest.maeDiff.diff.toFixed(2)} (${active.marketBacktest.maeDiff.ci_lo.toFixed(2)} to ${active.marketBacktest.maeDiff.ci_hi.toFixed(2)})`],
                        ["Margin RMSE", points(active.marketBacktest.rmsePrime), points(active.marketBacktest.rmseMarket), "—"],
                        ...(active.marketBacktest.probability ? [["Log loss (win probability)", active.marketBacktest.probability.loglossPrime.toFixed(3), active.marketBacktest.probability.loglossMarket.toFixed(3), `${active.marketBacktest.probability.loglossDiff.diff.toFixed(3)} (${active.marketBacktest.probability.loglossDiff.ci_lo.toFixed(3)} to ${active.marketBacktest.probability.loglossDiff.ci_hi.toFixed(3)})`]] : []),
                      ]}
                    />
                    <PerformanceTable
                      title="When PRIME disagrees with the line"
                      eyebrow="Model-market disagreement, historical"
                      note={`If disagreements carried signal, PRIME's side would cover well above 50% as the gap grows. It does not: cover rates stay near 50%, and the slope of actual-minus-line on PRIME-minus-line is ${active.marketBacktest.disagreementSlope.beta.toFixed(2)} (95% range ${active.marketBacktest.disagreementSlope.ci_lo.toFixed(2)} to ${active.marketBacktest.disagreementSlope.ci_hi.toFixed(2)}; 0 means no signal, 1 means PRIME fully right). Against the spread is shown only as a diagnostic, not as the measure of model quality.`}
                      headers={["PRIME vs line", "Games", "PRIME side covers", "95% range"]}
                      rows={active.marketBacktest.disagreementBuckets.map((bucket) => [
                        bucket.disagreement,
                        String(bucket.games),
                        pct(bucket.primeSideCoverRate),
                        `${pct(bucket.ci95[0])} to ${pct(bucket.ci95[1])}`,
                      ])}
                    />
                  </>
                ) : null}
              </>
            ) : null}

            {active.backtest ? (
              <>
                <PerformanceTable
                  title="Backtest: aggregate model, historical seasons"
                  eyebrow="Not live picks"
                  note={active.backtest.method}
                  headers={["Season", "Record", "Accuracy", "MAE", "RMSE", "Log loss", "Games"]}
                  rows={[
                    ...active.backtest.seasons.map((row) => [
                      String(row.season),
                      `${row.correct}–${row.games - row.correct}`,
                      pct(row.accuracySU),
                      points(row.mae),
                      points(row.rmse),
                      row.logLoss.toFixed(3),
                      String(row.games),
                    ]),
                  ]}
                />
                <PerformanceTable
                  title="Backtest calibration"
                  eyebrow="Predicted probability vs. reality, historical"
                  note="Out-of-sample: each season's probabilities use a calibration fit only on earlier seasons. The model was somewhat overconfident in the 70–80% band."
                  headers={["Confidence", "Avg predicted", "Actual win rate", "Gap", "Games"]}
                  rows={active.backtest.confidenceBuckets.map((bucket) => [
                    bucket.label,
                    pct(bucket.avgConfidence),
                    pct(bucket.actualWinRate),
                    `${bucket.actualWinRate - bucket.avgConfidence >= 0 ? "+" : ""}${((bucket.actualWinRate - bucket.avgConfidence) * 100).toFixed(1)} pp`,
                    String(bucket.games),
                  ])}
                />
              </>
            ) : null}

            <p className="prediction-performance-page__method-note">
              Straight-up winner accuracy is not against the spread. Margin MAE is the mean absolute
              difference between PRIME’s predicted home margin and the final home margin. Ties and games
              without verifiable final scores are excluded from grading. The betting market is treated as the benchmark:
              it is itself a predictive model, and PRIME is judged against it on winner accuracy, margin error and probability quality,
              not only on cover records.
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
