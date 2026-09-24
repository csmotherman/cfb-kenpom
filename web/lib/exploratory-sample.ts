// Custom game samples for Exploratory stats. Every Exploratory number is
// (sum of raw counts) / (sum of raw counts), so a team's numbers for a chosen
// subset of its games are just the sums over those games (see
// scripts/export_exploratory_data.py build_games_payload). Pure functions.

export type ExploratorySampleGame = {
  g: string; w: number; o: string | null; oi: number | null; fbs: boolean;
  ha: "H" | "A" | "N"; pf: number | null; pa: number | null; win: boolean;
  x: number[]; // counts aligned with meta.fields
};
export type ExploratorySampleData = {
  meta: { version: string; season: number; weekThrough: number; fields: string[] };
  team: { slug: string; team: string; teamId: number; games: ExploratorySampleGame[] };
};

/** Summed raw counts (keyed like ExploratoryRow.wk) over the chosen games (null = all). */
export function sumExploratory(data: ExploratorySampleData, included: ReadonlySet<string> | null) {
  const games = included ? data.team.games.filter((game) => included.has(game.g)) : data.team.games;
  const counts: Record<string, number> = {};
  data.meta.fields.forEach((field) => { counts[field] = 0; });
  for (const game of games) data.meta.fields.forEach((field, index) => { counts[field] += game.x[index] ?? 0; });
  return { counts, included: games.length, total: data.team.games.length };
}

/** Fail closed: all games must sum to the official season-to-date counts. */
export function verifyExploratoryParity(data: ExploratorySampleData, official: Record<string, number | undefined>): boolean {
  const { counts } = sumExploratory(data, null);
  return data.meta.fields.every((field) => {
    const expected = official[field] ?? 0;
    return Math.abs(counts[field] - expected) <= 1e-4 + 1e-6 * Math.abs(expected);
  });
}
