// Server-side access to the same public JSON the client pages load. Used for metadata, the sitemap and
// server-rendered crawler content. Reads from the build's own public/ folder; falls back to the production
// origin only if a file is missing locally. Never throws: callers get null and degrade gracefully.
import { readFile } from "node:fs/promises";
import path from "node:path";
import { cache } from "react";
import { SITE_URL } from "@/lib/seo";
import { fullTeamName } from "@/lib/teamMascots";
import type { RankingsRow, RankingsSeason, ScheduleGame, ScheduleSeason, SearchIndexEntry, SiteMeta } from "@/lib/types";

const DATA_DIR = path.join(process.cwd(), "public", "data");

export const readPublicData = cache(async (relativePath: string): Promise<unknown | null> => {
  try {
    return JSON.parse(await readFile(path.join(DATA_DIR, relativePath), "utf8"));
  } catch {
    try {
      const response = await fetch(`${SITE_URL}/data/${relativePath}`, { next: { revalidate: 3600 } });
      return response.ok ? await response.json() : null;
    } catch {
      return null;
    }
  }
});

export type PrimeRankingEntry = {
  rank: number; team: string; slug: string; teamId: number; conf: string; record: string; ratingRank: number; sorRank: number;
};
export type PrimeRankingsFile = { season: number; throughWeek: number; releasedAt: string; label: string; teams: PrimeRankingEntry[]; allTeams?: PrimeRankingEntry[] };

export const getSiteMeta = cache(async () => (await readPublicData("meta.json")) as SiteMeta | null);
export const getTeamDirectory = cache(async () => ((await readPublicData("search-index.json")) as SearchIndexEntry[] | null) ?? []);
export const getRankingsSeasonServer = cache(async (year: number | string) => (await readPublicData(`rankings/${year}.json`)) as RankingsSeason | null);
export const getScheduleServer = cache(async (year: number | string) => (await readPublicData(`schedule/${year}.json`)) as ScheduleSeason | null);
export const getPrimeRankingsServer = cache(async (year: number | string) => (await readPublicData(`prime-rankings/${year}.json`)) as PrimeRankingsFile | null);

export async function getLatestYear(): Promise<number | null> {
  const meta = await getSiteMeta();
  const years = meta?.rankingsYears ?? [];
  return years.length ? Math.max(...years) : null;
}

export async function getDataTimestamp(): Promise<string | null> {
  return (await getSiteMeta())?.generatedAt ?? null;
}

export type TeamSnapshot = {
  entry: SearchIndexEntry;
  fullName: string;
  year: number | null;
  week: number | null;
  latest: RankingsRow | null;
  prime25Rank: number | null;
};

/** null = the directory loaded and the team is not in it; undefined = the directory could not be read. */
export async function getTeamSnapshot(slug: string): Promise<TeamSnapshot | null | undefined> {
  const directory = await getTeamDirectory();
  const entry = directory.find((team) => team.slug === slug);
  if (!directory.length) return undefined;
  if (!entry) return null;
  const year = await getLatestYear();
  const season = year ? await getRankingsSeasonServer(year) : null;
  const week = season?.weeks?.length ? season.weeks[season.weeks.length - 1] : null;
  const latest = season && week !== null ? (season.byWeek[String(week)] ?? []).find((row) => row.slug === slug) ?? null : null;
  const prime = year ? await getPrimeRankingsServer(year) : null;
  const prime25 = prime?.teams.find((team) => team.slug === slug)?.rank ?? null;
  return { entry, fullName: fullTeamName(entry.team), year, week, latest, prime25Rank: prime25 };
}

export type GameContext = {
  season: number;
  game: ScheduleGame;
  weekLabel: string;
  away: { name: string; fullName: string; slug: string; rank: number | null; record: string | null };
  home: { name: string; fullName: string; slug: string; rank: number | null; record: string | null };
};

/** Returns null when the schedule loads but the game is not in it; undefined when the schedule itself cannot be read. */
export async function getGameContext(seasonParam: string, gameId: string): Promise<GameContext | null | undefined> {
  const season = Number.parseInt(seasonParam, 10);
  if (!Number.isFinite(season)) return null;
  const schedule = await getScheduleServer(season);
  if (!schedule) return undefined;
  let game: ScheduleGame | undefined;
  for (const games of Object.values(schedule.byWeek)) {
    game = games.find((g) => String(g.gameId) === gameId);
    if (game) break;
  }
  if (!game) return null;
  const rankings = await getRankingsSeasonServer(season);
  // Pregame view: ratings as of the week before the game, matching what the page itself shows.
  const weeks = (rankings?.weeks ?? []).filter((w) => w < game!.week);
  const ratingWeek = weeks.length ? weeks[weeks.length - 1] : null;
  const rows = rankings && ratingWeek !== null ? rankings.byWeek[String(ratingWeek)] ?? [] : [];
  const side = (name: string, slug: string) => {
    const row = rows.find((r) => r.slug === slug);
    return { name, fullName: fullTeamName(name), slug, rank: row?.rank ?? null, record: row?.record ?? null };
  };
  return {
    season,
    game,
    weekLabel: schedule.weekLabels?.[String(game.week)] || `Week ${game.week}`,
    away: side(game.awayTeam, game.awaySlug),
    home: side(game.homeTeam, game.homeSlug),
  };
}
