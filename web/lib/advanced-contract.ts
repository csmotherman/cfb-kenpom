import type { AdvancedRow, AdvancedSeason, RankingsSeason, ScheduleSeason } from "./types";

function require(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

/**
 * Make every Advanced consumer use the exact same headline rating snapshot as
 * the public Ratings table. The private Advanced payload owns the deeper
 * metrics; Rankings owns team identity plus Adj. Net / Adj. Off / Adj. Def and
 * their national ranks.
 *
 * Calendar-only weeks are carried forward exactly like the client-side data
 * loaders: snapshot values persist until a new model fit exists, while `wk`
 * stays empty so range aggregations cannot double-count the prior week.
 */
export function canonicalizeAdvancedSeason(
  advanced: AdvancedSeason,
  rankings: RankingsSeason,
  schedule: ScheduleSeason | null,
  seasonLabel: string,
): AdvancedSeason {
  require(
    advanced.weeks.length === rankings.weeks.length &&
      advanced.weeks.every((week, index) => week === rankings.weeks[index]),
    `Advanced/rankings week mismatch for ${seasonLabel}`,
  );

  const byWeek: Record<string, AdvancedRow[]> = {};

  for (const week of advanced.weeks) {
    const key = String(week);
    const ratingRows = rankings.byWeek[key] ?? [];
    const ratingsBySlug = new Map(ratingRows.map((row) => [row.slug, row]));
    const advancedRows = advanced.byWeek[key] ?? [];

    require(
      advancedRows.length === ratingRows.length &&
        advancedRows.every((row) => ratingsBySlug.has(row.slug)),
      `Advanced/rankings team coverage mismatch for ${seasonLabel} week ${week}`,
    );

    byWeek[key] = advancedRows.map((row) => {
      const rating = ratingsBySlug.get(row.slug)!;
      return {
        ...row,
        team: rating.team,
        teamId: rating.teamId,
        conf: rating.conf,
        adjEM: rating.adjEM,
        adjO: rating.adjO,
        adjD: rating.adjD,
        rank: rating.rank,
        adjORank: rating.adjORank,
        adjDRank: rating.adjDRank,
      };
    });
  }

  const weeks = [...rankings.weeks];
  const weekLabels = { ...rankings.weekLabels };

  if (schedule && weeks.length > 0) {
    const lastPublishedWeek = weeks[weeks.length - 1];
    const targetWeek = schedule.currentWeek;
    let previousRows = byWeek[String(lastPublishedWeek)] ?? [];

    for (let week = lastPublishedWeek + 1; week <= targetWeek; week += 1) {
      previousRows = previousRows.map((row) => ({ ...row, wk: {} }));
      byWeek[String(week)] = previousRows;
      weeks.push(week);
      const label = schedule.weekLabels?.[String(week)];
      if (label) weekLabels[String(week)] = label;
    }
  }

  return { ...advanced, weeks, weekLabels, byWeek };
}
