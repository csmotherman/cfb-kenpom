import { useSyncExternalStore } from "react";
import type { AdvancedSeason, PredictionsWeek, RankingsSeason, SearchIndexEntry, SiteMeta } from "./types";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

// Two-tier cache: `data` holds already-resolved seasons for synchronous,
// zero-flicker reads (via useSyncExternalStore below); `inflight` dedupes
// concurrent requests for the same season. Once a season lands in `data` it
// never needs to be fetched again for the life of the tab, so switching back
// to a season you've already viewed -- a year button, a tab, a week range --
// renders instantly instead of re-showing a loading skeleton.
const listeners = new Set<() => void>();
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

let metaPromise: Promise<SiteMeta> | null = null;
let searchIndexPromise: Promise<SearchIndexEntry[]> | null = null;

export function getMeta(): Promise<SiteMeta> {
  if (!metaPromise) metaPromise = fetchJson<SiteMeta>("/data/meta.json");
  return metaPromise;
}

export function getSearchIndex(): Promise<SearchIndexEntry[]> {
  if (!searchIndexPromise) searchIndexPromise = fetchJson<SearchIndexEntry[]>("/data/search-index.json");
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
      rankingsData.set(key, season);
      rankingsInflight.delete(key);
      notify();
      return season;
    });
    rankingsInflight.set(key, entry);
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
    entry = fetchJson<AdvancedSeason>(`/data/advanced/${key}.json`).then((season) => {
      advancedData.set(key, season);
      advancedInflight.delete(key);
      notify();
      return season;
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
  return useSyncExternalStore(
    subscribe,
    () => (year ? rankingsData.get(year) : undefined),
    () => undefined
  );
}

export function useAdvancedSeason(year: string | null): AdvancedSeason | undefined {
  return useSyncExternalStore(
    subscribe,
    () => (year ? advancedData.get(year) : undefined),
    () => undefined
  );
}

export async function getPredictionsWeek(season: number | string, week: number | string): Promise<PredictionsWeek | null> {
  try {
    return await fetchJson<PredictionsWeek>(`/data/predictions/${season}-${week}.json`);
  } catch {
    return null;
  }
}
