import { useEffect, useSyncExternalStore } from "react";
import { extendRankingsToCurrentWeek } from "./rankingsExtend";
import type { ConferenceOnlySampleResponse, TeamSampleData } from "./custom-sample";
import type { ExploratorySampleData } from "./exploratory-sample";
import type { AdvancedSeason, CfpSeasonResult, ExploratorySeason, GameLogSeason, MarketLinesSeason, PredictionsTrackRecord, PredictionsWeek, ProjectionSeason, RankingsSeason, ScheduleSeason, SearchIndexEntry, SiteMeta, TeamStatsSeason, TeamStatsWeeklySeason } from "./types";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-cache", signal: AbortSignal.timeout(20000) });
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

async function fetchOptionalJson<T>(path: string): Promise<T | null> {
  const res = await fetch(path, { cache: "no-cache", signal: AbortSignal.timeout(20000) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export class PremiumAccessError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "PremiumAccessError";
    this.status = status;
    this.code = code;
  }
}

async function fetchPremiumJson<T>(path: string): Promise<T> {
  const res = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    signal: AbortSignal.timeout(20000),
  });

  if (res.ok) return res.json() as Promise<T>;

  let payload: { code?: string; message?: string } = {};
  try {
    payload = (await res.json()) as { code?: string; message?: string };
  } catch {
    // Preserve the HTTP status even if a proxy or host returned non-JSON.
  }

  if (res.status === 401 || res.status === 403) {
    throw new PremiumAccessError(
      res.status,
      payload.code ?? (res.status === 401 ? "SIGN_IN_REQUIRED" : "UPGRADE_REQUIRED"),
      payload.message ?? "A PRIME Advanced subscription is required to view this data."
    );
  }

  throw new Error(payload.message ?? `Failed to load ${path}: ${res.status}`);
}

// Two-tier cache: `data` holds already-resolved seasons for synchronous,
// zero-flicker reads (via useSyncExternalStore below); `inflight` dedupes
// concurrent requests for the same season. Once a season lands in `data` it
// never needs to be fetched again for the life of the tab, so switching back
// to a season you've already viewed -- a year button, a tab, a week range --
// renders instantly instead of re-showing a loading skeleton.
const listeners = new Set<() => void>();
const dataErrors = new Map<string, Error>();
function notify() {
  listeners.forEach((l) => l());
}
function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

const rankingsData = new Map<string, RankingsSeason>();
const rankingsInflight = new Map<string, Promise<RankingsSeason>>();

const advancedData = new Map<string, AdvancedSeason>();
const advancedInflight = new Map<string, Promise<AdvancedSeason>>();
const exploratoryData = new Map<string, ExploratorySeason>();
const exploratoryInflight = new Map<string, Promise<ExploratorySeason>>();

const scheduleData = new Map<string, ScheduleSeason | null>();
const scheduleInflight = new Map<string, Promise<ScheduleSeason | null>>();

const marketLinesData = new Map<string, MarketLinesSeason | null>();
const marketLinesInflight = new Map<string, Promise<MarketLinesSeason | null>>();

const gameLogData = new Map<string, GameLogSeason | null>();
const gameLogInflight = new Map<string, Promise<GameLogSeason | null>>();

const teamStatsData = new Map<string, TeamStatsSeason | null>();
const teamStatsInflight = new Map<string, Promise<TeamStatsSeason | null>>();

const teamStatsWeeklyData = new Map<string, TeamStatsWeeklySeason | null>();
const teamStatsWeeklyInflight = new Map<string, Promise<TeamStatsWeeklySeason | null>>();

const predictionsTrackRecordData = new Map<string, PredictionsTrackRecord | null>();
const predictionsTrackRecordInflight = new Map<string, Promise<PredictionsTrackRecord | null>>();

const projectionData = new Map<string, ProjectionSeason | null>();
const projectionInflight = new Map<string, Promise<ProjectionSeason | null>>();

const cfpResultsData = new Map<string, CfpSeasonResult | null>();
const cfpResultsInflight = new Map<string, Promise<CfpSeasonResult | null>>();

let metaPromise: Promise<SiteMeta> | null = null;
let searchIndexPromise: Promise<SearchIndexEntry[]> | null = null;

function extendAdvancedToCurrentWeek(season: AdvancedSeason, schedule: ScheduleSeason | null): AdvancedSeason {
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
      // Snapshot values carry forward until the model is refit. Raw weekly
      // counts must not carry forward or selected-week ranges would double-count.
      wk: {},
    }));
    byWeek[String(week)] = previousRows;
    weeks.push(week);
    const label = schedule.weekLabels?.[String(week)];
    if (label) weekLabels[String(week)] = label;
  }

  return { ...season, weeks, weekLabels, byWeek };
}

// ---- Server-provided initial data -------------------------------------------------------------------------
// A server component that already read a public dataset passes it to the page's client component, which seeds these
// caches (client-side only) so the first render and every later reader share that one copy and nothing is fetched
// again. Seeding never overwrites data that is already cached, and never notifies: it happens during render.
export function seedMeta(meta: SiteMeta) {
  if (typeof window !== "undefined" && !metaPromise) metaPromise = Promise.resolve(meta);
}
export function seedRankingsSeason(year: number | string, season: RankingsSeason) {
  if (typeof window !== "undefined" && !rankingsData.has(String(year))) rankingsData.set(String(year), season);
}
export function seedScheduleSeason(year: number | string, season: ScheduleSeason | null) {
  if (typeof window !== "undefined" && !scheduleData.has(String(year))) scheduleData.set(String(year), season);
}
export function seedProjectionSeason(year: number | string, record: ProjectionSeason | null) {
  if (typeof window !== "undefined" && !projectionData.has(String(year))) projectionData.set(String(year), record);
}
export function seedCfpResultsSeason(year: number | string, result: CfpSeasonResult | null) {
  if (typeof window !== "undefined" && !cfpResultsData.has(String(year))) cfpResultsData.set(String(year), result);
}
export function seedMarketLinesSeason(year: number | string, season: MarketLinesSeason | null) {
  if (typeof window !== "undefined" && !marketLinesData.has(String(year))) marketLinesData.set(String(year), season);
}

export function getMeta(): Promise<SiteMeta> {
  if (!metaPromise) metaPromise = fetchJson<SiteMeta>("/data/meta.json").catch((error) => { metaPromise = null; throw error; });
  return metaPromise;
}

export function getSearchIndex(): Promise<SearchIndexEntry[]> {
  if (!searchIndexPromise) searchIndexPromise = fetchJson<SearchIndexEntry[]>("/data/search-index.json").catch((error) => { searchIndexPromise = null; throw error; });
  return searchIndexPromise;
}

export function getRankingsSeasonSync(year: number | string): RankingsSeason | undefined {
  return rankingsData.get(String(year));
}

export function getRankingsSeason(year: number | string): Promise<RankingsSeason> {
  const key = String(year);
  const cached = rankingsData.get(key);
  if (cached) return Promise.resolve(cached);
  let entry = rankingsInflight.get(key);
  if (!entry) {
    entry = Promise.all([
      fetchJson<RankingsSeason>(`/data/rankings/${key}.json`),
      getScheduleSeason(key),
    ]).then(([season, schedule]) => {
      const currentSeason = extendRankingsToCurrentWeek(season, schedule);
      dataErrors.delete(`rankings:${key}`);
      rankingsData.set(key, currentSeason);
      rankingsInflight.delete(key);
      notify();
      return currentSeason;
    });
    entry = entry.catch((error: Error) => {
      rankingsInflight.delete(key);
      dataErrors.set(`rankings:${key}`, error);
      notify();
      throw error;
    });
    rankingsInflight.set(key, entry);
  }
  return entry;
}

export function getScheduleSeason(year: number | string): Promise<ScheduleSeason | null> {
  const key = String(year);
  if (scheduleData.has(key)) return Promise.resolve(scheduleData.get(key) ?? null);
  let entry = scheduleInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<ScheduleSeason>(`/data/schedule/${key}.json`).then((season) => {
      scheduleData.set(key, season);
      scheduleInflight.delete(key);
      return season;
    });
    entry = entry.catch((error: Error) => {
      scheduleInflight.delete(key);
      throw error;
    });
    scheduleInflight.set(key, entry);
  }
  return entry;
}

export function getMarketLinesSeason(year: number | string): Promise<MarketLinesSeason | null> {
  const key = String(year);
  if (marketLinesData.has(key)) return Promise.resolve(marketLinesData.get(key) ?? null);
  let entry = marketLinesInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<MarketLinesSeason>(`/data/market-lines/${key}.json`).then((season) => {
      marketLinesData.set(key, season);
      marketLinesInflight.delete(key);
      return season;
    });
    entry = entry.catch((error: Error) => {
      marketLinesInflight.delete(key);
      throw error;
    });
    marketLinesInflight.set(key, entry);
  }
  return entry;
}

// Prototype-stage: served as a public static file (like schedule), NOT
// routed through /api/premium the way Advanced's own numbers are. Advanced
// itself is gated at app/advanced/layout.tsx, but this JSON is directly
// fetchable by URL -- fine for testing the game-log-modal UX, but this
// should move behind the same premium_datasets + /api/premium pattern as
// getAdvancedSeason before shipping, since it exposes the same box-score
// detail the Advanced paywall is meant to protect.
export function getGameLogSeason(year: number | string): Promise<GameLogSeason | null> {
  const key = String(year);
  if (gameLogData.has(key)) return Promise.resolve(gameLogData.get(key) ?? null);
  let entry = gameLogInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<GameLogSeason>(`/data/gamelogs/${key}.json`).then((season) => {
      gameLogData.set(key, season);
      gameLogInflight.delete(key);
      return season;
    });
    entry = entry.catch((error: Error) => {
      gameLogInflight.delete(key);
      throw error;
    });
    gameLogInflight.set(key, entry);
  }
  return entry;
}

export function getTeamStatsSeason(year: number | string): Promise<TeamStatsSeason | null> {
  const key = String(year);
  if (teamStatsData.has(key)) return Promise.resolve(teamStatsData.get(key) ?? null);
  let entry = teamStatsInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<TeamStatsSeason>(`/data/team-stats/${key}.json`).then((season) => {
      teamStatsData.set(key, season);
      teamStatsInflight.delete(key);
      return season;
    });
    entry = entry.catch((error: Error) => {
      teamStatsInflight.delete(key);
      throw error;
    });
    teamStatsInflight.set(key, entry);
  }
  return entry;
}

export function getTeamStatsWeeklySeason(year: number | string): Promise<TeamStatsWeeklySeason | null> {
  const key = String(year);
  if (teamStatsWeeklyData.has(key)) return Promise.resolve(teamStatsWeeklyData.get(key) ?? null);
  let entry = teamStatsWeeklyInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<TeamStatsWeeklySeason>(`/data/team-stats-weekly/${key}.json`).then((season) => {
      teamStatsWeeklyData.set(key, season);
      teamStatsWeeklyInflight.delete(key);
      return season;
    });
    entry = entry.catch((error: Error) => {
      teamStatsWeeklyInflight.delete(key);
      throw error;
    });
    teamStatsWeeklyInflight.set(key, entry);
  }
  return entry;
}

// Custom-sample ingredients for ONE team (~10 KB), fetched only when a user
// opens that team's game selector (or a shared link references it) and kept for
// the life of the tab. `null` = not published for this team/season.
const teamSampleData = new Map<string, TeamSampleData | null>();
const teamSampleInflight = new Map<string, Promise<TeamSampleData | null>>();
const conferenceOnlySampleData = new Map<string, ConferenceOnlySampleResponse | null>();
const conferenceOnlySampleInflight = new Map<string, Promise<ConferenceOnlySampleResponse | null>>();

export function getConferenceOnlySamples(year: number | string): Promise<ConferenceOnlySampleResponse | null> {
  const key = String(year);
  if (conferenceOnlySampleData.has(key)) return Promise.resolve(conferenceOnlySampleData.get(key) ?? null);
  let entry = conferenceOnlySampleInflight.get(key);
  if (!entry) {
    entry = fetchPremiumJson<ConferenceOnlySampleResponse>(`/api/premium/advanced/${key}/conference-only`)
      .then((data) => data, (error: Error) => {
        if (error instanceof PremiumAccessError) throw error;
        if (/404|not available/i.test(error.message)) return null;
        throw error;
      })
      .then((data) => {
        conferenceOnlySampleData.set(key, data);
        conferenceOnlySampleInflight.delete(key);
        return data;
      }, (error: Error) => {
        conferenceOnlySampleInflight.delete(key);
        throw error;
      });
    conferenceOnlySampleInflight.set(key, entry);
  }
  return entry;
}


export function getTeamSample(year: number | string, teamId: number | string): Promise<TeamSampleData | null> {
  const key = `${year}:${teamId}`;
  if (teamSampleData.has(key)) return Promise.resolve(teamSampleData.get(key) ?? null);
  let entry = teamSampleInflight.get(key);
  if (!entry) {
    entry = fetchPremiumJson<TeamSampleData>(`/api/premium/advanced/${year}/games/${teamId}`)
      .then((data) => data, (error: Error) => {
        if (error instanceof PremiumAccessError) throw error;
        if (/404|not available/i.test(error.message)) return null;
        throw error;
      })
      .then((data) => {
        teamSampleData.set(key, data);
        teamSampleInflight.delete(key);
        return data;
      }, (error: Error) => {
        teamSampleInflight.delete(key);
        throw error;
      });
    teamSampleInflight.set(key, entry);
  }
  return entry;
}

// Same idea for Exploratory: one team's per-game counts (~5 KB), on demand.
const exploratorySampleData = new Map<string, ExploratorySampleData | null>();
const exploratorySampleInflight = new Map<string, Promise<ExploratorySampleData | null>>();

export function getExploratoryTeamSample(year: number | string, teamId: number | string): Promise<ExploratorySampleData | null> {
  const key = `${year}:${teamId}`;
  if (exploratorySampleData.has(key)) return Promise.resolve(exploratorySampleData.get(key) ?? null);
  let entry = exploratorySampleInflight.get(key);
  if (!entry) {
    entry = fetchPremiumJson<ExploratorySampleData>(`/api/premium/exploratory/${year}/games/${teamId}`)
      .catch((error: Error) => {
        if (error instanceof PremiumAccessError) throw error;
        if (/not available/i.test(error.message)) return null;
        throw error;
      })
      .then((data) => { exploratorySampleData.set(key, data); exploratorySampleInflight.delete(key); return data; },
        (error: Error) => { exploratorySampleInflight.delete(key); throw error; });
    exploratorySampleInflight.set(key, entry);
  }
  return entry;
}

export function getAdvancedSeasonSync(year: number | string): AdvancedSeason | undefined {
  return advancedData.get(String(year));
}

export function getAdvancedSeason(year: number | string): Promise<AdvancedSeason> {
  const key = String(year);
  const cached = advancedData.get(key);
  if (cached) return Promise.resolve(cached);
  let entry = advancedInflight.get(key);
  if (!entry) {
    entry = Promise.all([
      fetchPremiumJson<AdvancedSeason>(`/api/premium/advanced/${key}`),
      getScheduleSeason(key),
    ]).then(([season, schedule]) => {
      const currentSeason = extendAdvancedToCurrentWeek(season, schedule);
      dataErrors.delete(`advanced:${key}`);
      advancedData.set(key, currentSeason);
      advancedInflight.delete(key);
      notify();
      return currentSeason;
    });
    entry = entry.catch((error: Error) => {
      advancedInflight.delete(key);
      dataErrors.set(`advanced:${key}`, error);
      notify();
      throw error;
    });
    advancedInflight.set(key, entry);
  }
  return entry;
}

/** Fire off (and cache) every rankings season in the background, so year/tab
 * switches later just read the already-resolved cache instead of fetching. */
export function prefetchAllRankings(years: (number | string)[]): void {
  years.forEach((y) => {
    getRankingsSeason(y).catch(() => {});
  });
}

export function prefetchAllAdvanced(years: (number | string)[]): void {
  years.forEach((y) => {
    getAdvancedSeason(y).catch(() => {});
  });
}

/** Subscribes to the rankings cache for one season -- returns the season the
 * instant it's available (synchronously, with no render flicker, if it was
 * already fetched/prefetched) and re-renders when it arrives otherwise. */
export function useRankingsSeason(year: string | null): RankingsSeason | undefined {
  useEffect(() => {
    if (year) getRankingsSeason(year).catch(() => {});
  }, [year]);
  return useSyncExternalStore(
    subscribe,
    () => {
      const error = year ? dataErrors.get(`rankings:${year}`) : undefined;
      if (error) throw error;
      return year ? rankingsData.get(year) : undefined;
    },
    () => undefined
  );
}

export function useAdvancedSeason(year: string | null): AdvancedSeason | undefined {
  useEffect(() => {
    if (year) getAdvancedSeason(year).catch(() => {});
  }, [year]);
  return useSyncExternalStore(
    subscribe,
    () => {
      const error = year ? dataErrors.get(`advanced:${year}`) : undefined;
      if (error) throw error;
      return year ? advancedData.get(year) : undefined;
    },
    () => undefined
  );
}

// Research-stage Exploratory. Deliberately simpler than getAdvancedSeason:
// no rankings merge (Exploratory has no headline-rating columns) and no
// extend-to-current-week carry-forward -- this shows exactly what's been
// published, nothing synthesized between publishes.
export function getExploratorySeason(year: number | string): Promise<ExploratorySeason> {
  const key = String(year);
  const cached = exploratoryData.get(key);
  if (cached) return Promise.resolve(cached);
  let entry = exploratoryInflight.get(key);
  if (!entry) {
    entry = fetchPremiumJson<ExploratorySeason>(`/api/premium/exploratory/${key}`).then((season) => {
      dataErrors.delete(`exploratory:${key}`);
      exploratoryData.set(key, season);
      exploratoryInflight.delete(key);
      notify();
      return season;
    });
    entry = entry.catch((error: Error) => {
      exploratoryInflight.delete(key);
      dataErrors.set(`exploratory:${key}`, error);
      notify();
      throw error;
    });
    exploratoryInflight.set(key, entry);
  }
  return entry;
}

export function useExploratorySeason(year: string | null): ExploratorySeason | undefined {
  useEffect(() => {
    if (year) getExploratorySeason(year).catch(() => {});
  }, [year]);
  return useSyncExternalStore(
    subscribe,
    () => {
      const error = year ? dataErrors.get(`exploratory:${year}`) : undefined;
      if (error) throw error;
      return year ? exploratoryData.get(year) : undefined;
    },
    () => undefined
  );
}

// Public and ungated, unlike getPredictionsWeek's picks -- this is aggregate
// accuracy only (no game-by-game predictions), so it's meant to be shown to
// visitors who haven't subscribed yet, e.g. on the /upgrade paywall itself.
export function getPredictionsTrackRecord(year: number | string): Promise<PredictionsTrackRecord | null> {
  const key = String(year);
  if (predictionsTrackRecordData.has(key)) return Promise.resolve(predictionsTrackRecordData.get(key) ?? null);
  let entry = predictionsTrackRecordInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<PredictionsTrackRecord>(`/data/prediction-track-record/${key}.json`).then((record) => {
      predictionsTrackRecordData.set(key, record);
      predictionsTrackRecordInflight.delete(key);
      return record;
    });
    entry = entry.catch((error: Error) => {
      predictionsTrackRecordInflight.delete(key);
      throw error;
    });
    predictionsTrackRecordInflight.set(key, entry);
  }
  return entry;
}

// Public and ungated -- the model itself (a full-field ranking from prior
// results, recruiting and QB continuity), not the weekly picks derived
// from it, which stay behind getPredictionsWeek's gate.
// Public, free historical fact (see lib/types.ts's CfpSeasonResult). Missing
// for a season whose CFP hasn't been played yet, or is still in progress --
// that's a real, expected 404, not an error.
export function getCfpResultsSeason(year: number | string): Promise<CfpSeasonResult | null> {
  const key = String(year);
  if (cfpResultsData.has(key)) return Promise.resolve(cfpResultsData.get(key) ?? null);
  let entry = cfpResultsInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<CfpSeasonResult>(`/data/cfp-results/${key}.json`).then((result) => {
      cfpResultsData.set(key, result);
      cfpResultsInflight.delete(key);
      notify();
      return result;
    });
    entry = entry.catch((error: Error) => {
      cfpResultsInflight.delete(key);
      throw error;
    });
    cfpResultsInflight.set(key, entry);
  }
  return entry;
}

export function useCfpResultsSeason(year: string | null): CfpSeasonResult | null | undefined {
  useEffect(() => {
    if (year) getCfpResultsSeason(year).catch(() => {});
  }, [year]);
  return useSyncExternalStore(
    subscribe,
    () => (year ? cfpResultsData.get(year) : undefined),
    () => undefined
  );
}

export async function getPredictionsWeek(season: number | string, week: number | string): Promise<PredictionsWeek | null> {
  const path = `/api/premium/predictions/${season}/${week}`;
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    signal: AbortSignal.timeout(20000),
  });
  if (response.status === 404) return null;
  if (response.ok) return response.json() as Promise<PredictionsWeek>;

  let payload: { code?: string; message?: string } = {};
  try {
    payload = (await response.json()) as { code?: string; message?: string };
  } catch {
    // Fall through to status-based messaging below.
  }

  if (response.status === 401 || response.status === 403) {
    throw new PremiumAccessError(
      response.status,
      payload.code ?? (response.status === 401 ? "SIGN_IN_REQUIRED" : "UPGRADE_REQUIRED"),
      payload.message ?? "A PRIME Advanced subscription is required to view Predictions."
    );
  }

  throw new Error(payload.message ?? "Predictions are temporarily unavailable");
}


// Public forward-looking Projection. A missing file (season without a published projection) is a normal null.
export function getProjectionSeason(year: number | string): Promise<ProjectionSeason | null> {
  const key = String(year);
  if (projectionData.has(key)) return Promise.resolve(projectionData.get(key) ?? null);
  let entry = projectionInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<ProjectionSeason>(`/data/projection/${key}.json`).then((record) => {
      projectionData.set(key, record);
      projectionInflight.delete(key);
      notify();
      return record;
    });
    entry = entry.catch((error: Error) => {
      projectionInflight.delete(key);
      throw error;
    });
    projectionInflight.set(key, entry);
  }
  return entry;
}

export function useProjectionSeason(year: string | null): ProjectionSeason | null | undefined {
  useEffect(() => {
    if (year) getProjectionSeason(year).catch(() => {});
  }, [year]);
  return useSyncExternalStore(
    subscribe,
    () => (year ? projectionData.get(year) : undefined),
    () => undefined
  );
}
