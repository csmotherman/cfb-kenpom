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
  rank: number;
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  record: string;
  ratingRank: number;
  sorRank: number;
  primeScore: number;
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

export type TrackRecordFile = { generatedAt?: string };
export const getTrackRecordTimestamp = cache(async (year: number | string) => ((await readPublicData(`prediction-track-record/${year}.json`)) as TrackRecordFile | null)?.generatedAt ?? null);

/** Latest published rating snapshot for a season: the rows and the week they describe. */
export const getLatestSnapshot = cache(async (year: number) => {
  const season = await getRankingsSeasonServer(year);
  const week = season?.weeks?.length ? season.weeks[season.weeks.length - 1] : null;
  const rows = season && week !== null ? season.byWeek[String(week)] ?? [] : [];
  return { season, week, rows };
});

export type TeamGameRow = {
  game: ScheduleGame;
  home: boolean;
  opponent: string;
  opponentFull: string;
  opponentSlug: string;
  opponentHasProfile: boolean;
  opponentRank: number | null;
  pointsFor: number | null;
  pointsAgainst: number | null;
  result: "W" | "L" | "T" | null;
};

export type TeamContent = {
  snapshot: TeamSnapshot;
  games: TeamGameRow[];
  totalRated: number;
  /** Position by PRIME rating among rated teams of the same conference. */
  confRank: number | null;
  confTotal: number;
  weekLabel: string | null;
};

const gameSort = (a: ScheduleGame, b: ScheduleGame) => a.week - b.week || (a.startDate ?? "").localeCompare(b.startDate ?? "");

export async function getTeamContent(snapshot: TeamSnapshot): Promise<TeamContent> {
  const { year, entry } = snapshot;
  const [schedule, directory, latestSnap] = await Promise.all([
    year ? getScheduleServer(year) : null,
    getTeamDirectory(),
    year ? getLatestSnapshot(year) : null,
  ]);
  const profiles = new Set(directory.map((team) => team.slug));
  const rows = latestSnap?.rows ?? [];
  const rankBySlug = new Map(rows.map((row) => [row.slug, row.rank]));
  const games = schedule
    ? Object.values(schedule.byWeek)
        .flat()
        .filter((g) => g.homeSlug === entry.slug || g.awaySlug === entry.slug)
        .sort(gameSort)
        .map((g): TeamGameRow => {
          const home = g.homeSlug === entry.slug;
          const opponent = home ? g.awayTeam : g.homeTeam;
          const opponentSlug = home ? g.awaySlug : g.homeSlug;
          const pointsFor = home ? g.homePoints : g.awayPoints;
          const pointsAgainst = home ? g.awayPoints : g.homePoints;
          const scored = g.completed && pointsFor !== null && pointsAgainst !== null;
          return {
            game: g,
            home,
            opponent,
            opponentFull: fullTeamName(opponent),
            opponentSlug,
            opponentHasProfile: profiles.has(opponentSlug),
            opponentRank: rankBySlug.get(opponentSlug) ?? null,
            pointsFor,
            pointsAgainst,
            result: scored ? (pointsFor! > pointsAgainst! ? "W" : pointsFor! < pointsAgainst! ? "L" : "T") : null,
          };
        })
    : [];
  const confRows = rows.filter((row) => row.conf === entry.conf && row.rank !== null).sort((a, b) => a.rank! - b.rank!);
  const confIndex = confRows.findIndex((row) => row.slug === entry.slug);
  const week = snapshot.week;
  return {
    snapshot,
    games,
    totalRated: rows.filter((row) => row.rank !== null).length,
    confRank: confIndex >= 0 ? confIndex + 1 : null,
    confTotal: confRows.length,
    weekLabel: week === null ? null : latestSnap?.season?.weekLabels?.[String(week)] || `Week ${week}`,
  };
}

export type MatchupSide = {
  name: string;
  fullName: string;
  slug: string;
  /** True when the team has a PRIME profile page (FBS teams). FCS opponents have none. */
  hasProfile: boolean;
  row: RankingsRow | null;
  /** Position in The PRIME 25, only when the ratings shown are current and the team is in it. */
  prime25: number | null;
  rank: number | null;
  /** Overall record entering the matchup, including games against FCS opponents. */
  overallRecord: string;
  /** FBS-only record entering the matchup. */
  fbsRecord: string;
  /** Record across the team's five most recent games entering the matchup. */
  lastFiveRecord: string;
  homeRecord: string;
  roadRecord: string;
  pointsPerGame: number | null;
  pointsAllowedPerGame: number | null;
  averageMargin: number | null;
  /** Published record from the rating snapshot. */
  record: string | null;
};

export type GameContext = {
  season: number;
  game: ScheduleGame;
  weekLabel: string;
  away: MatchupSide;
  home: MatchupSide;
  /** Which published rating snapshot the comparison uses. "pregame" = the week before kickoff, "current" = latest available. */
  ratingBasis: "pregame" | "current" | null;
  ratingWeek: number | null;
  totalRated: number;
  /** True for the current season, whose weeks have hub pages at /week/[n]. */
  currentSeason: boolean;
};

/** Returns null when the schedule loads but the game is not in it; undefined when the schedule itself cannot be read. */
export async function getGameContext(seasonParam: string, gameId: string): Promise<GameContext | null | undefined> {
  const season = Number.parseInt(seasonParam, 10);
  if (!Number.isFinite(season)) return null;
  const schedule = await getScheduleServer(season);
  if (!schedule) return undefined;
  const all = Object.values(schedule.byWeek).flat();
  const game = all.find((g) => String(g.gameId) === gameId);
  if (!game) return null;
  const [rankings, directory, prime, latestYear] = await Promise.all([getRankingsSeasonServer(season), getTeamDirectory(), getPrimeRankingsServer(season), getLatestYear()]);
  const profiles = new Set(directory.map((team) => team.slug));
  const weeks = rankings?.weeks ?? [];
  const rowsFor = (week: number | null) => (rankings && week !== null ? rankings.byWeek[String(week)] ?? [] : []);
  const priorWeeks = weeks.filter((w) => w < game.week);
  const pregameWeek = priorWeeks.length ? priorWeeks[priorWeeks.length - 1] : null;
  const latestWeek = weeks.length ? weeks[weeks.length - 1] : null;
  const has = (rows: RankingsRow[]) => rows.some((r) => r.slug === game.awaySlug) && rows.some((r) => r.slug === game.homeSlug);
  // Prefer the true pregame snapshot; when a team was not yet rated then (e.g. a Week 1 opener), fall back to the latest one.
  let ratingWeek: number | null = null;
  let ratingBasis: GameContext["ratingBasis"] = null;
  if (has(rowsFor(pregameWeek))) { ratingWeek = pregameWeek; ratingBasis = "pregame"; }
  else if (has(rowsFor(latestWeek))) { ratingWeek = latestWeek; ratingBasis = latestWeek !== null && latestWeek < game.week ? "pregame" : "current"; }
  const rows = rowsFor(ratingWeek);
  const primeSlugs = new Map((prime?.teams ?? []).map((t) => [t.slug, t.rank]));
  const primeApplies = ratingWeek !== null && prime?.throughWeek === ratingWeek;
  const side = (name: string, slug: string): MatchupSide => {
    const row = rows.find((r) => r.slug === slug) ?? null;
    const completedGames = all
      .filter((g) => g.completed && g.week < game.week && (g.homeSlug === slug || g.awaySlug === slug))
      .sort(gameSort);
    const recordFor = (games: ScheduleGame[]) => games.reduce(
      (record, g) => {
        const home = g.homeSlug === slug;
        const pointsFor = home ? g.homePoints : g.awayPoints;
        const pointsAgainst = home ? g.awayPoints : g.homePoints;
        if (pointsFor === null || pointsAgainst === null) return record;
        if (pointsFor > pointsAgainst) record.wins += 1;
        else if (pointsFor < pointsAgainst) record.losses += 1;
        else record.ties += 1;
        return record;
      },
      { wins: 0, losses: 0, ties: 0 }
    );
    const formatRecord = (record: ReturnType<typeof recordFor>) =>
      `${record.wins}-${record.losses}${record.ties ? `-${record.ties}` : ""}`;
    const overall = recordFor(completedGames);
    const fbs = recordFor(completedGames.filter((g) => profiles.has(g.homeSlug === slug ? g.awaySlug : g.homeSlug)));
    const lastFive = recordFor(completedGames.slice(-5));
    const home = recordFor(completedGames.filter((g) => !g.neutralSite && g.homeSlug === slug));
    const road = recordFor(completedGames.filter((g) => !g.neutralSite && g.awaySlug === slug));
    const scoredGames = completedGames.filter((g) => g.homePoints !== null && g.awayPoints !== null);
    const scoring = scoredGames.reduce(
      (totals, g) => {
        const isHome = g.homeSlug === slug;
        totals.for += isHome ? g.homePoints! : g.awayPoints!;
        totals.against += isHome ? g.awayPoints! : g.homePoints!;
        return totals;
      },
      { for: 0, against: 0 }
    );
    const overallRecord = formatRecord(overall);
    const fbsRecord = formatRecord(fbs);
    const gamesPlayed = scoredGames.length;
    return {
      name,
      fullName: fullTeamName(name),
      slug,
      hasProfile: profiles.has(slug),
      row,
      prime25: primeApplies ? primeSlugs.get(slug) ?? null : null,
      rank: row?.rank ?? null,
      overallRecord,
      fbsRecord,
      lastFiveRecord: formatRecord(lastFive),
      homeRecord: formatRecord(home),
      roadRecord: formatRecord(road),
      pointsPerGame: gamesPlayed ? scoring.for / gamesPlayed : null,
      pointsAllowedPerGame: gamesPlayed ? scoring.against / gamesPlayed : null,
      averageMargin: gamesPlayed ? (scoring.for - scoring.against) / gamesPlayed : null,
      record: row?.record ?? null,
    };
  };
  const away = side(game.awayTeam, game.awaySlug);
  const home = side(game.homeTeam, game.homeSlug);
  return {
    season,
    game,
    weekLabel: schedule.weekLabels?.[String(game.week)] || `Week ${game.week}`,
    away,
    home,
    ratingBasis,
    ratingWeek,
    totalRated: rows.filter((r) => r.rank !== null).length,
    currentSeason: latestYear === season,
  };
}

/** A game page is indexable when both teams have profiles and ratings; FBS-vs-FCS games have no comparison to offer. */
export const isIndexableGame = (ctx: GameContext) => ctx.away.hasProfile && ctx.home.hasProfile && !!ctx.away.row && !!ctx.home.row;

// ------------------------------------------------------------------ week and conference hubs

export type HubGame = { game: ScheduleGame; awayRank: number | null; homeRank: number | null; awayFull: string; homeFull: string };
/**
 * A week page is worth indexing when it lists a real slate to browse, not a single game whose own matchup page already says
 * everything. Judged per week on the 2026 schedule: Week 0 is the complete opening slate (8 games, all with results), so it
 * is indexable; Week 14 is one game (Army-Navy), which adds nothing beyond that game's page, so it stays noindex.
 */
export const MIN_HUB_GAMES = 5;

export type WeekHub = {
  year: number;
  week: number;
  label: string;
  weeks: { week: number; label: string }[];
  games: HubGame[];
  played: boolean;
  /** FBS-vs-FBS games with two rated teams; FCS games are left out (their pages are noindex). */
  allCompleted: boolean;
  ratingWeek: number | null;
};

const weekLabel = (schedule: ScheduleSeason, week: number) => schedule.weekLabels?.[String(week)] || `Week ${week}`;

/** Current-season slate for one site week. null = no such week; undefined = data unreadable. */
export async function getWeekHub(week: number): Promise<WeekHub | null | undefined> {
  const year = await getLatestYear();
  if (!year) return undefined;
  const [schedule, snap] = await Promise.all([getScheduleServer(year), getLatestSnapshot(year)]);
  if (!schedule) return undefined;
  if (!schedule.weeks.includes(week)) return null;
  const rank = new Map(snap.rows.filter((r) => r.rank !== null).map((r) => [r.slug, r.rank as number]));
  const all = schedule.byWeek[String(week)] ?? [];
  const games = all
    .filter((g) => rank.has(g.awaySlug) && rank.has(g.homeSlug))
    .map((g): HubGame => ({ game: g, awayRank: rank.get(g.awaySlug) ?? null, homeRank: rank.get(g.homeSlug) ?? null, awayFull: fullTeamName(g.awayTeam), homeFull: fullTeamName(g.homeTeam) }))
    .sort((a, b) => (a.awayRank! + a.homeRank!) - (b.awayRank! + b.homeRank!));
  return {
    year, week, label: weekLabel(schedule, week),
    weeks: schedule.weeks.map((w) => ({ week: w, label: weekLabel(schedule, w) })),
    games, played: games.length > 0 && games.every((g) => g.game.completed), allCompleted: all.every((g) => g.completed), ratingWeek: snap.week,
  };
}

/** Weeks that have an indexable hub page, in order. */
export async function getHubWeeks(): Promise<{ year: number; weeks: { week: number; label: string; played: boolean }[] }> {
  const year = await getLatestYear();
  const schedule = year ? await getScheduleServer(year) : null;
  if (!year || !schedule) return { year: year ?? 0, weeks: [] };
  const hubs = await Promise.all(schedule.weeks.map((w) => getWeekHub(w)));
  return { year, weeks: hubs.filter((h): h is WeekHub => !!h && h.games.length >= MIN_HUB_GAMES).map((h) => ({ week: h.week, label: h.label, played: h.played })) };
}

export type ConferenceHub = {
  code: string;
  year: number;
  week: number | null;
  teams: RankingsRow[];
  avgRating: number | null;
  /** Position among conferences (by average PRIME rating) and how many were compared. */
  confRank: number | null;
  confCount: number;
  bestOffense: RankingsRow | null;
  bestDefense: RankingsRow | null;
  nonConf: { wins: number; losses: number } | null;
  upcoming: HubGame[];
  weekLabel: string | null;
};

export async function getConferenceHub(code: string): Promise<ConferenceHub | null | undefined> {
  const year = await getLatestYear();
  if (!year) return undefined;
  const [snap, schedule] = await Promise.all([getLatestSnapshot(year), getScheduleServer(year)]);
  if (!snap.rows.length) return undefined;
  const rated = snap.rows.filter((r) => r.rank !== null && r.adjEM !== null);
  const teams = rated.filter((r) => r.conf === code).sort((a, b) => a.rank! - b.rank!);
  if (!teams.length) return null;
  const avg = (rows: RankingsRow[]) => rows.reduce((sum, r) => sum + (r.adjEM as number), 0) / rows.length;
  const byConf = new Map<string, RankingsRow[]>();
  for (const r of rated) if (r.conf !== "IND") byConf.set(r.conf, [...(byConf.get(r.conf) ?? []), r]);
  const ranked = [...byConf.entries()].filter(([, rows]) => rows.length >= 8).map(([c, rows]) => [c, avg(rows)] as const).sort((a, b) => b[1] - a[1]);
  const idx = ranked.findIndex(([c]) => c === code);
  const conf = new Set(teams.map((t) => t.slug));
  const ratedSlugs = new Set(rated.map((r) => r.slug));
  const games = schedule ? Object.values(schedule.byWeek).flat() : [];
  // Non-conference record against rated FBS opponents only (the same scope as every PRIME record).
  let wins = 0, losses = 0;
  for (const g of games) {
    if (!g.completed || g.conferenceGame || g.homePoints === null || g.awayPoints === null) continue;
    if (!ratedSlugs.has(g.homeSlug) || !ratedSlugs.has(g.awaySlug)) continue;
    const homeIn = conf.has(g.homeSlug), awayIn = conf.has(g.awaySlug);
    if (homeIn === awayIn) continue;
    const confWon = homeIn ? g.homePoints > g.awayPoints : g.awayPoints > g.homePoints;
    if (g.homePoints === g.awayPoints) continue;
    if (confWon) wins++; else losses++;
  }
  const rank = new Map(teams.map((t) => [t.slug, t.rank as number]));
  const nextWeek = schedule ? [...new Set(games.filter((g) => !g.completed).map((g) => g.week))].sort((a, b) => a - b)[0] : undefined;
  const upcoming = games
    .filter((g) => !g.completed && g.week === nextWeek && g.conferenceGame && conf.has(g.homeSlug) && conf.has(g.awaySlug))
    .map((g): HubGame => ({ game: g, awayRank: rank.get(g.awaySlug) ?? null, homeRank: rank.get(g.homeSlug) ?? null, awayFull: fullTeamName(g.awayTeam), homeFull: fullTeamName(g.homeTeam) }))
    .sort((a, b) => (a.awayRank! + a.homeRank!) - (b.awayRank! + b.homeRank!));
  const best = (key: "adjORank" | "adjDRank") => teams.filter((t) => t[key]).sort((a, b) => a[key]! - b[key]!)[0] ?? null;
  return {
    code, year, week: snap.week, teams, avgRating: avg(teams), confRank: idx >= 0 ? idx + 1 : null, confCount: ranked.length,
    bestOffense: best("adjORank"), bestDefense: best("adjDRank"),
    nonConf: wins + losses ? { wins, losses } : null,
    upcoming, weekLabel: schedule && nextWeek !== undefined ? weekLabel(schedule, nextWeek) : null,
  };
}
