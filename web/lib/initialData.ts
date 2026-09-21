// Server-side loaders for the initial data of the interactive public pages. They read the same public JSON the browser
// used to fetch after hydration, so the first HTML response already contains the page's main content. Only what the
// first render needs is returned: the current season, the current week's games, and trimmed projection rows. Other
// seasons and weeks still load on demand through lib/data.ts. Premium prediction values are never read here.
import { extendRankingsToCurrentWeek } from "@/lib/rankingsExtend";
import { getLatestYear, getPrimeRankingsServer, getRankingsSeasonServer, getScheduleServer, getSiteMeta, readPublicData, type PrimeRankingsFile } from "@/lib/seoData";
import { buildPerformanceSummary, type PerformanceSummary } from "@/lib/performanceSummary";
import type { CfpSeasonResult, PredictionsTrackRecord, MarketLinesSeason, ProjectionSeason, RankingsRow, RankingsSeason, ScheduleGame, ScheduleSeason } from "@/lib/types";

export type RatingsInitial = {
  year: string;
  years: number[];
  generatedAt: string | null;
  season: RankingsSeason;
  projection: ProjectionSeason | null;
  cfp: CfpSeasonResult | null;
};

/** Rankings with the schedule's current week applied, exactly as the client's own loader produces it. */
async function currentRankings(year: number): Promise<RankingsSeason | null> {
  const [season, schedule] = await Promise.all([getRankingsSeasonServer(year), getScheduleServer(year)]);
  return season ? extendRankingsToCurrentWeek(season, schedule) : null;
}

export async function getRatingsInitial(): Promise<RatingsInitial | null> {
  const [meta, year] = await Promise.all([getSiteMeta(), getLatestYear()]);
  if (!meta || !year) return null;
  const [season, projectionRaw, cfp] = await Promise.all([
    currentRankings(year),
    readPublicData(`projection/${year}.json`) as Promise<ProjectionSeason | null>,
    readPublicData(`cfp-results/${year}.json`) as Promise<CfpSeasonResult | null>,
  ]);
  if (!season) return null;
  // The table only reads team, projection and rank from each projection row.
  const projection = projectionRaw
    ? { ...projectionRaw, byWeek: Object.fromEntries(Object.entries(projectionRaw.byWeek).map(([week, rows]) => [week, rows.map(({ team, projection: value, rank }) => ({ team, projection: value, rank }) as ProjectionSeason["byWeek"][string][number])])) }
    : null;
  return { year: String(year), years: meta.rankingsYears, generatedAt: meta.generatedAt ?? null, season, projection, cfp: cfp ?? null };
}

export type RankingsInitial = { snapshot: PrimeRankingsFile };
export async function getRankingsInitial(): Promise<RankingsInitial | null> {
  const year = await getLatestYear();
  const snapshot = year ? await getPrimeRankingsServer(year) : null;
  return snapshot ? { snapshot } : null;
}

export type HomeInitial = {
  year: string;
  snapshot: PrimeRankingsFile | null;
  latestWeek: number | null;
  currentWeek: number | null;
  topRatings: RankingsRow[];
  featuredGame: ScheduleGame | null;
  featuredHome: RankingsRow | null;
  featuredAway: RankingsRow | null;
  bestOffense: RankingsRow | null;
  bestDefense: RankingsRow | null;
  toughestSchedule: RankingsRow | null;
  biggestRiser: RankingsRow | null;
};

const bestByRank = (rows: RankingsRow[], key: "adjORank" | "adjDRank" | "sosRank") =>
  rows.filter((row) => row[key] !== null).sort((a, b) => (a[key] ?? 999) - (b[key] ?? 999))[0] ?? null;

/** Everything the homepage cards need, computed once on the server so the client ships no 100 KB+ datasets. */
export async function getHomeInitial(): Promise<HomeInitial | null> {
  const year = await getLatestYear();
  if (!year) return null;
  const [season, schedule, snapshot] = await Promise.all([currentRankings(year), getScheduleServer(year), getPrimeRankingsServer(year)]);
  const latestWeek = season?.weeks?.length ? season.weeks[season.weeks.length - 1] : null;
  const currentRows = season && latestWeek !== null ? season.byWeek[String(latestWeek)] ?? [] : [];
  const byTeamId = new Map(currentRows.map((row) => [row.teamId, row]));
  let featuredGame: ScheduleGame | null = null;
  if (schedule) {
    const targetWeek = schedule.weeks.find((week) => (schedule.byWeek[String(week)] ?? []).some((game) => !game.completed)) ?? schedule.currentWeek;
    const candidates = (schedule.byWeek[String(targetWeek)] ?? []).filter((game) => !game.completed);
    featuredGame = [...candidates].sort((a, b) => {
      const aHome = byTeamId.get(a.homeTeamId)?.rank ?? 200, aAway = byTeamId.get(a.awayTeamId)?.rank ?? 200;
      const bHome = byTeamId.get(b.homeTeamId)?.rank ?? 200, bAway = byTeamId.get(b.awayTeamId)?.rank ?? 200;
      const aTop = Number(aHome <= 25) + Number(aAway <= 25), bTop = Number(bHome <= 25) + Number(bAway <= 25);
      if (aTop !== bTop) return bTop - aTop;
      return aHome + aAway - (bHome + bAway);
    })[0] ?? null;
  }
  return {
    year: String(year),
    snapshot,
    latestWeek,
    currentWeek: schedule?.currentWeek ?? null,
    topRatings: [...currentRows].filter((t) => t.rank !== null).sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999)).slice(0, 5),
    featuredGame,
    featuredHome: featuredGame ? byTeamId.get(featuredGame.homeTeamId) ?? null : null,
    featuredAway: featuredGame ? byTeamId.get(featuredGame.awayTeamId) ?? null : null,
    bestOffense: bestByRank(currentRows, "adjORank"),
    bestDefense: bestByRank(currentRows, "adjDRank"),
    toughestSchedule: bestByRank(currentRows, "sosRank"),
    biggestRiser: [...currentRows].filter((r) => r.rankChange !== null && r.rankChange > 0).sort((a, b) => (b.rankChange ?? 0) - (a.rankChange ?? 0))[0] ?? null,
  };
}

export type PredictionsInitial = {
  season: number;
  selectedWeek: number;
  /** Full week list and labels, but games only for the selected week; other weeks load on demand. */
  schedule: ScheduleSeason;
  rankings: RankingsSeason;
  marketLines: MarketLinesSeason | null;
  /** The all-time model results strip above the table, computed here so it does not pop in and push the table down. */
  performance: PerformanceSummary | null;
};

const defaultWeek = (schedule: ScheduleSeason): number => {
  const week = schedule.weeks.find((w) => (schedule.byWeek[String(w)] ?? []).some((g) => !g.completed));
  return week ?? schedule.currentWeek;
};

export async function getPredictionsInitial(defaultWeekFn: (s: ScheduleSeason) => number = defaultWeek): Promise<PredictionsInitial | null> {
  const year = await getLatestYear();
  if (!year) return null;
  const meta = await getSiteMeta();
  const predictionYears = meta?.predictionYears?.length ? meta.predictionYears : [year];
  const [schedule, rankings, market, tracks] = await Promise.all([
    getScheduleServer(year),
    currentRankings(year),
    readPublicData(`market-lines/${year}.json`) as Promise<MarketLinesSeason | null>,
    Promise.all(predictionYears.map((y) => readPublicData(`prediction-track-record/${y}.json`) as Promise<PredictionsTrackRecord | null>)),
  ]);
  if (!schedule || !rankings) return null;
  const selectedWeek = defaultWeekFn(schedule);
  const games = schedule.byWeek[String(selectedWeek)] ?? [];
  const prior = rankings.weeks.filter((w) => w < selectedWeek);
  const ratingWeek = prior.length ? prior[prior.length - 1] : null;
  const ids = new Set(games.map((g) => String(g.gameId)));
  return {
    season: year,
    selectedWeek,
    schedule: { ...schedule, byWeek: Object.fromEntries(schedule.weeks.map((w) => [String(w), w === selectedWeek ? games : []])) },
    rankings: { ...rankings, byWeek: Object.fromEntries(rankings.weeks.map((w) => [String(w), w === ratingWeek ? rankings.byWeek[String(w)] ?? [] : []])) },
    performance: buildPerformanceSummary(tracks.filter((t): t is PredictionsTrackRecord => Boolean(t?.overall?.graded))),
    marketLines: market ? { ...market, games: Object.fromEntries(Object.entries(market.games ?? {}).filter(([id]) => ids.has(id))) } : null,
  };
}
