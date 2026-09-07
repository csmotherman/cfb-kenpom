import type { AdvancedSeason, PredictionsWeek, RankingsSeason, SearchIndexEntry, SiteMeta } from "./types";

const rankingsCache = new Map<string, Promise<RankingsSeason>>();
const advancedCache = new Map<string, Promise<AdvancedSeason>>();
let metaPromise: Promise<SiteMeta> | null = null;
let searchIndexPromise: Promise<SearchIndexEntry[]> | null = null;

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export function getMeta(): Promise<SiteMeta> {
  if (!metaPromise) metaPromise = fetchJson<SiteMeta>("/data/meta.json");
  return metaPromise;
}

export function getSearchIndex(): Promise<SearchIndexEntry[]> {
  if (!searchIndexPromise) searchIndexPromise = fetchJson<SearchIndexEntry[]>("/data/search-index.json");
  return searchIndexPromise;
}

export function getRankingsSeason(year: number | string): Promise<RankingsSeason> {
  const key = String(year);
  let entry = rankingsCache.get(key);
  if (!entry) {
    entry = fetchJson<RankingsSeason>(`/data/rankings/${key}.json`);
    rankingsCache.set(key, entry);
  }
  return entry;
}

export function getAdvancedSeason(year: number | string): Promise<AdvancedSeason> {
  const key = String(year);
  let entry = advancedCache.get(key);
  if (!entry) {
    entry = fetchJson<AdvancedSeason>(`/data/advanced/${key}.json`);
    advancedCache.set(key, entry);
  }
  return entry;
}

export async function getPredictionsWeek(season: number | string, week: number | string): Promise<PredictionsWeek | null> {
  try {
    return await fetchJson<PredictionsWeek>(`/data/predictions/${season}-${week}.json`);
  } catch {
    return null;
  }
}
