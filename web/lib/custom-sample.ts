// Custom game samples for Advanced Stats: recompute ONE team's numbers from a
// chosen subset of its games, independently per team.
//
// The math and the data contract are documented in scripts/custom_sample.py.
// In short: rate stats are sums of raw per-game counts; opponent-adjusted edges
// are ridge-fit averages whose per-game contributions are published with the
// (fixed, official) opponent ratings baked in, so a subset of games gives that
// team's edge given those games; an all-games selection is the official value.
//
// Pure functions only -- no React, no fetching -- so they can be unit tested.

export type SampleGame = {
  g: string; // gameId
  w: number; // site-week
  o: string | null; // opponent name
  os: string | null; // opponent slug (null for non-FBS)
  oi: number | null; // opponent team id (null for non-FBS)
  fbs: boolean; // FBS-vs-FBS: contributes to the adjusted fit
  ha: "H" | "A" | "N";
  pf: number | null;
  pa: number | null;
  win: boolean;
  r: number[]; // raw counts, aligned with meta.rawFields
  s: number | null; // opponent's walk-forward SRS (SOS)
  a: Array<number | null>; // 6 numbers per spec: [numO, denO, uO, numD, denD, uD]
  x?: number[]; // optional turnover/penalty counts, aligned with meta.exFields
};

export type SampleMeta = {
  version: string;
  season: number;
  weekThrough: number;
  lambda: number;
  rampGames: number;
  rawFields: string[];
  specs: string[];
  exFields: string[];
  consts: Record<string, { mu: number; kOff: number; kDef: number }>;
};

export type SampleTeam = { slug: string; team: string; teamId: number; games: SampleGame[] };
export type TeamSampleData = { meta: SampleMeta; team: SampleTeam };

export type SampleResult = {
  included: number;
  total: number;
  wins: number;
  losses: number;
  /** Raw per-game counts summed over the chosen games, keyed like AdvancedRow.wk. */
  raw: Record<string, number>;
  /** Recomputed opponent-adjusted snapshot values, keyed like AdvancedRow. */
  adjusted: Record<string, number | null>;
  /** Turnover/penalty counts (Exploratory), or null when not exported for this team. */
  ex: Record<string, number> | null;
};

// Directly published adjusted edges: [AdvancedRow key, spec, fit side, decimals].
// Havoc's fitted sides are swapped on purpose (see build_real_data.py).
const DIRECT: Array<[string, string, "offense" | "defense", number]> = [
  ["offExp", "Explosive", "offense", 4],
  ["defExp", "Explosive", "defense", 4],
  ["offFin", "Finishing", "offense", 2],
  ["defFin", "Finishing", "defense", 2],
  ["offHavoc", "Havoc", "defense", 4],
  ["defHavoc", "Havoc", "offense", 4],
];

// Confidence-blended EPA / Success edges: [AdvancedRow key prefix, spec].
const BLENDED: Array<[string, string]> = [
  ["success", "Success"], ["epa", "EPA"], ["passEpa", "PassEPA"], ["rushEpa", "RushEPA"],
  ["passEpaDown1", "PassEPADown1"], ["passEpaDown2", "PassEPADown2"], ["passEpaDown3", "PassEPADown3"],
  ["rushEpaDown1", "RushEPADown1"], ["rushEpaDown2", "RushEPADown2"], ["rushEpaDown3", "RushEPADown3"],
  ["passSuccess", "PassSuccess"], ["rushSuccess", "RushSuccess"],
  ["passSuccessDown1", "PassSuccessDown1"], ["passSuccessDown2", "PassSuccessDown2"], ["passSuccessDown3", "PassSuccessDown3"],
  ["rushSuccessDown1", "RushSuccessDown1"], ["rushSuccessDown2", "RushSuccessDown2"], ["rushSuccessDown3", "RushSuccessDown3"],
];

/** AdvancedRow keys this module can recompute for a custom sample. */
export const CUSTOM_ADJUSTED_KEYS: string[] = [
  ...DIRECT.map(([key]) => key),
  ...BLENDED.flatMap(([prefix]) => [`${prefix}Adj`, `${prefix}AdjAllowed`]),
];

const round = (value: number, digits: number) => {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
};

function adjustmentConfidence(gamesPlayed: number, rampGames: number): number {
  if (gamesPlayed <= 1) return 0;
  if (rampGames <= 1) return 1;
  return Math.min(1, (gamesPlayed - 1) / (rampGames - 1));
}

/**
 * Recompute a team's numbers from the games in `included` (null = every game).
 * Opponent ratings stay at their official values; only THIS team's sample changes.
 */
export function computeSample(data: TeamSampleData, included: ReadonlySet<string> | null): SampleResult {
  const { meta, team } = data;
  const games = included ? team.games.filter((game) => included.has(game.g)) : team.games;
  const raw: Record<string, number> = {};
  meta.rawFields.forEach((field) => { raw[field] = 0; });
  let wins = 0;
  let losses = 0;
  let sosSum = 0;
  let sosCount = 0;

  type Acc = { aO: number; wO: number; obsO: number; aD: number; wD: number; obsD: number; nO: number; dO: number; nD: number; dD: number };
  const accs: Acc[] = meta.specs.map(() => ({ aO: 0, wO: 0, obsO: 0, aD: 0, wD: 0, obsD: 0, nO: 0, dO: 0, nD: 0, dD: 0 }));
  const exCounts: Record<string, number> = {};
  let exGames = 0;

  for (const game of games) {
    if (game.win) wins += 1; else losses += 1;
    meta.rawFields.forEach((field, index) => { raw[field] += game.r[index] ?? 0; });
    if (game.s !== null && game.s !== undefined) { sosSum += game.s; sosCount += 1; }
    meta.specs.forEach((_, si) => {
      const base = si * 6;
      const numO = game.a[base] ?? 0;
      const denO = game.a[base + 1] ?? 0;
      const uO = game.a[base + 2];
      const numD = game.a[base + 3] ?? 0;
      const denD = game.a[base + 4] ?? 0;
      const uD = game.a[base + 5];
      const acc = accs[si];
      acc.nO += numO; acc.dO += denO; acc.nD += numD; acc.dD += denD;
      if (game.fbs && uO !== null && uO !== undefined) { acc.aO += numO + denO * uO; acc.wO += denO; acc.obsO += 1; }
      if (game.fbs && uD !== null && uD !== undefined) { acc.aD += denD * uD - numD; acc.wD += denD; acc.obsD += 1; }
    });
    if (game.x) {
      exGames += 1;
      meta.exFields.forEach((field, index) => { exCounts[field] = (exCounts[field] ?? 0) + (game.x![index] ?? 0); });
    }
  }
  raw.opponentSrsSum = sosSum;
  raw.opponentSrsCount = sosCount;
  raw.wins = wins;
  raw.losses = losses;

  const specIndex = new Map(meta.specs.map((spec, index) => [spec, index]));
  const edge = (spec: string, side: "offense" | "defense"): number | null => {
    const si = specIndex.get(spec);
    const c = meta.consts[spec];
    if (si === undefined || !c) return null;
    const acc = accs[si];
    if (side === "offense") return acc.obsO ? (acc.aO - c.kOff) / (acc.wO + meta.lambda) : null;
    return acc.obsD ? (acc.aD - c.kDef) / (acc.wD + meta.lambda) : null;
  };

  const adjusted: Record<string, number | null> = {};
  for (const [key, spec, side, digits] of DIRECT) {
    if (!specIndex.has(spec)) continue;
    const value = edge(spec, side);
    adjusted[key] = value === null ? null : round(value, digits);
  }
  const confidence = adjustmentConfidence(games.length, meta.rampGames);
  for (const [prefix, spec] of BLENDED) {
    const si = specIndex.get(spec);
    const c = meta.consts[spec];
    if (si === undefined || !c) continue;
    const acc = accs[si];
    for (const [side, suffix] of [["offense", "Adj"], ["defense", "AdjAllowed"]] as const) {
      const e = edge(spec, side);
      const rawRate = side === "offense" ? (acc.dO > 0 ? acc.nO / acc.dO : null) : (acc.dD > 0 ? acc.nD / acc.dD : null);
      if (e === null || rawRate === null) { adjusted[prefix + suffix] = null; continue; }
      const unadjusted = side === "defense" ? c.mu - rawRate : rawRate - c.mu;
      adjusted[prefix + suffix] = round(confidence * e + (1 - confidence) * unadjusted, 4);
    }
  }

  return {
    included: games.length,
    total: team.games.length,
    wins,
    losses,
    raw,
    adjusted,
    ex: exGames > 0 && exGames === games.length ? exCounts : null,
  };
}

/**
 * Fail-closed guard: with every game selected, the recomputed adjusted values
 * must equal the official Advanced row (to the published rounding). If they do
 * not -- a stale artifact, a model change -- custom samples are disabled rather
 * than showing numbers that disagree with the official table.
 */
export function verifyParity(data: TeamSampleData, official: Record<string, unknown>): { ok: boolean; checked: number; maxDiff: number } {
  const all = computeSample(data, null);
  let checked = 0;
  let maxDiff = 0;
  let ok = true;
  for (const key of CUSTOM_ADJUSTED_KEYS) {
    const mine = all.adjusted[key];
    const theirs = official[key];
    if (mine === undefined) continue;
    if (mine === null && (theirs === null || theirs === undefined)) continue;
    if (typeof mine !== "number" || typeof theirs !== "number") { ok = false; continue; }
    const diff = Math.abs(mine - theirs);
    // Published values are rounded to 2 or 4 decimals; allow one last-digit flip.
    const tolerance = key === "offFin" || key === "defFin" ? 0.0101 : 0.000101;
    checked += 1;
    maxDiff = Math.max(maxDiff, diff);
    if (diff > tolerance) ok = false;
  }
  return { ok: ok && checked > 0, checked, maxDiff };
}

/** `michigan:4018.4019;iowa:4020` <-> { michigan: [...], iowa: [...] } */
export function serializeExclusions(excluded: Record<string, string[]>): string {
  return Object.entries(excluded)
    .filter(([, ids]) => ids.length > 0)
    .map(([slug, ids]) => `${slug}:${ids.join(".")}`)
    .join(";");
}

export function parseExclusions(value: string | null | undefined): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  if (!value) return out;
  for (const part of value.split(";")) {
    const [slug, ids] = part.split(":");
    if (!slug || !/^[a-z0-9-]+$/.test(slug) || !ids) continue;
    const list = ids.split(".").filter((id) => /^\d{4,12}$/.test(id));
    if (list.length) out[slug] = [...new Set(list)];
  }
  return out;
}
