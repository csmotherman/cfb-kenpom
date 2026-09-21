import type { RankingsSeason, ScheduleSeason } from "./types";

/**
 * Rankings/Advanced are model snapshots, while the schedule is the calendar
 * source of truth. A new college-football week can begin before a new FBS-vs-
 * FBS result changes the rating graph. In that gap, expose the schedule's
 * current week by carrying the most recent model snapshot forward. Weekly raw
 * Advanced counts stay empty until games actually finish, so range stats never
 * double-count the previous week.
 */
export function extendRankingsToCurrentWeek(season: RankingsSeason, schedule: ScheduleSeason | null): RankingsSeason {
  if (!schedule || season.weeks.length === 0) return season;
  const lastPublishedWeek = season.weeks[season.weeks.length - 1];
  const targetWeek = schedule.currentWeek;
  if (targetWeek <= lastPublishedWeek) return season;

  const byWeek = { ...season.byWeek };
  const weeks = [...season.weeks];
  const weekLabels = { ...season.weekLabels };
  let previousRows = byWeek[String(lastPublishedWeek)] ?? [];

  for (let week = lastPublishedWeek + 1; week <= targetWeek; week += 1) {
    previousRows = previousRows.map((row) => ({
      ...row,
      rankChange: row.rank === null ? null : 0,
    }));
    byWeek[String(week)] = previousRows;
    weeks.push(week);
    const label = schedule.weekLabels?.[String(week)];
    if (label) weekLabels[String(week)] = label;
  }

  return { ...season, weeks, weekLabels, byWeek };
}

