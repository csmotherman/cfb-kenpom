import { useEffect, useSyncExternalStore } from "react";
import type { AdvancedSeason, PredictionsTrackRecord, PredictionsWeek, PreseasonPower, RankingsSeason, ScheduleSeason, SearchIndexEntry, SiteMeta, TeamStatsSeason, TeamStatsWeeklySeason } from "./types";

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
      payload.message ?? "A LEILA Pro subscription is required to view this data."
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

const scheduleData = new Map<string, ScheduleSeason | null>();
const scheduleInflight = new Map<string, Promise<ScheduleSeason | null>>();

const teamStatsData = new Map<string, TeamStatsSeason | null>();
const teamStatsInflight = new Map<string, Promise<TeamStatsSeason | null>>();

const teamStatsWeeklyData = new Map<string, TeamStatsWeeklySeason | null>();
const teamStatsWeeklyInflight = new Map<string, Promise<TeamStatsWeeklySeason | null>>();

const predictionsTrackRecordData = new Map<string, PredictionsTrackRecord | null>();
const predictionsTrackRecordInflight = new Map<string, Promise<PredictionsTrackRecord | null>>();

const preseasonPowerData = new Map<string, PreseasonPower | null>();
const preseasonPowerInflight = new Map<string, Promise<PreseasonPower | null>>();

let metaPromise: Promise<SiteMeta> | null = null;
let searchIndexPromise: Promise<SearchIndexEntry[]> | null = null;

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
    entry = fetchJson<RankingsSeason>(`/data/rankings/${key}.json`).then((season) => {
      dataErrors.delete(`rankings:${key}`);
      rankingsData.set(key, season);
      rankingsInflight.delete(key);
      notify();
      return season;
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

export function getAdvancedSeasonSync(year: number | string): AdvancedSeason | undefined {
  return advancedData.get(String(year));
}

export function getAdvancedSeason(year: number | string): Promise<AdvancedSeason> {
  const key = String(year);
  const cached = advancedData.get(key);
  if (cached) return Promise.resolve(cached);
  let entry = advancedInflight.get(key);
  if (!entry) {
    entry = fetchPremiumJson<AdvancedSeason>(`/api/premium/advanced/${key}`).then((season) => {
      dataErrors.delete(`advanced:${key}`);
      advancedData.set(key, season);
      advancedInflight.delete(key);
      notify();
      return season;
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
export function getPreseasonPower(year: number | string): Promise<PreseasonPower | null> {
  const key = String(year);
  if (preseasonPowerData.has(key)) return Promise.resolve(preseasonPowerData.get(key) ?? null);
  let entry = preseasonPowerInflight.get(key);
  if (!entry) {
    entry = fetchOptionalJson<PreseasonPower>(`/data/preseason-power-${key}.json`).then((record) => {
      preseasonPowerData.set(key, record);
      preseasonPowerInflight.delete(key);
      return record;
    });
    entry = entry.catch((error: Error) => {
      preseasonPowerInflight.delete(key);
      throw error;
    });
    preseasonPowerInflight.set(key, entry);
  }
  return entry;
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
      payload.message ?? "A LEILA Pro subscription is required to view Predictions."
    );
  }

  throw new Error(payload.message ?? "Predictions are temporarily unavailable");
}
