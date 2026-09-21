import type { PredictionsTrackRecord } from "@/lib/types";

export type PerformanceSummary = {
  correct: number;
  incorrect: number;
  graded: number;
  accuracy: number;
  mae: number | null;
  sinceYear: number | null;
  backtestGames: number;
};

/** Combines the graded live picks. Pure, so the server and the browser agree. */
export function buildPerformanceSummary(
  records: PredictionsTrackRecord[],
): PerformanceSummary | null {
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

  if (graded === 0) return null;
  return {
    correct,
    incorrect: graded - correct,
    graded,
    accuracy: graded ? correct / graded : 0,
    mae: maeGraded ? maeWeighted / maeGraded : null,
    sinceYear: null,
    backtestGames: 0,
  };
}
