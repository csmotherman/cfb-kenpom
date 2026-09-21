// Week-level trust states for the ratings, from the historical stability analysis (2014-2025): how closely each week's
// APR ordering matches that season's final ordering. These are broad, week-level states only -- there is deliberately
// no team-specific confidence figure, because none has been validated.
export type TrustState = {
  level: "provisional" | "tiers" | "solid" | "exact";
  label: string;
  detail: string;
};

export function ratingsTrustState(week: number | null | undefined, isPostseasonWeek = false): TrustState | null {
  if (week == null || !Number.isFinite(week) || isPostseasonWeek) return null;
  if (week <= 3) {
    return {
      level: "provisional",
      label: "Provisional",
      detail: "Early-season rankings are still highly sensitive to new opponent information.",
    };
  }
  if (week <= 5) {
    return {
      level: "tiers",
      label: "Tiers only",
      detail: "Read these as tiers, not exact positions: the top of the order can still move a lot.",
    };
  }
  if (week <= 9) {
    return {
      level: "solid",
      label: "Solid ordering",
      detail: "The overall order is largely settled; individual ranks can still move several places.",
    };
  }
  return {
    level: "exact",
    label: "Exact ranks increasingly meaningful",
    detail: "Ratings now rest on most of the schedule, so individual ranks move far less week to week.",
  };
}
