import type { PredictionsTrackRecord, PreseasonPower } from "@/lib/types";

export type PerformanceSummary = {
  correct: number;
  incorrect: number;
  graded: number;
  accuracy: number;
  mae: number | null;
  sinceYear: number | null;
  backtestGames: number;
};

/** Combines the graded live picks with the frozen preseason-power backtest. Pure, so the server and the browser agree. */
export function buildPerformanceSummary(
  records: PredictionsTrackRecord[],
  power: PreseasonPower | null,
  rankingsYears: number[],
): PerformanceSummary | null {
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

  if (graded === 0) return null;
  return {
    correct,
    incorrect: graded - correct,
    graded,
    accuracy: graded ? correct / graded : 0,
    mae: maeGraded ? maeWeighted / maeGraded : null,
    sinceYear: backtestGames > 0 ? rankingsYears[0] ?? null : null,
    backtestGames,
  };
}
