// Deterministic, data-derived copy for the public pages (team profiles, matchups, section intros).
// No runtime model calls: every sentence is chosen by rules from published ratings and schedule data, and a sentence
// is omitted whenever the data behind it is missing. Only public data appears here; predicted margins and win
// probabilities are premium and never used.
import type { RankingsRow, ScheduleGame } from "@/lib/types";
import type { GameContext, MatchupSide, TeamContent, TeamGameRow } from "@/lib/seoData";
import { conferenceName } from "@/lib/teamMascots";

export const ordinal = (n: number) => {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
};
export const noRank = (n: number | null | undefined) => (n ? `No. ${n}` : null);
export const signedRating = (n: number | null | undefined, digits = 1) =>
  n === null || n === undefined || Number.isNaN(n) ? null : `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function joinList(items: string[]) {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

const ET = "America/New_York";
export function formatGameDate(game: ScheduleGame, style: "long" | "short" = "long"): string | null {
  if (!game.startDate) return null;
  const d = new Date(game.startDate);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", style === "long" ? { weekday: "long", month: "long", day: "numeric", timeZone: ET } : { weekday: "short", month: "short", day: "numeric", timeZone: ET });
}
export function formatKickoff(game: ScheduleGame): string | null {
  if (!game.startDate || game.startTimeTBD) return null;
  const d = new Date(game.startDate);
  if (Number.isNaN(d.getTime())) return null;
  return `${d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: ET })} ET`;
}

// ---------------------------------------------------------------- team pages

const positionBand = (rank: number | null | undefined, total: number) => {
  if (!rank || total <= 0) return null;
  const share = rank / total;
  return share <= 0.2 ? "top" : share >= 0.8 ? "bottom" : null;
};

/** Link text for a game on a team page, e.g. "Michigan at Ohio State preview". */
export function teamGameLabel(row: TeamGameRow) {
  const { game } = row;
  return `${game.awayTeam} ${game.neutralSite ? "vs" : "at"} ${game.homeTeam}${game.completed ? " game analytics" : " preview"}`;
}

export function teamResultText(row: TeamGameRow): string | null {
  if (!row.result || row.pointsFor === null || row.pointsAgainst === null) return null;
  return `${row.result} ${row.pointsFor}–${row.pointsAgainst}`;
}

export function nextAndLast(content: TeamContent) {
  const upcoming = content.games.filter((g) => !g.game.completed);
  const completed = content.games.filter((g) => g.game.completed);
  return { next: upcoming[0] ?? null, last: completed[completed.length - 1] ?? null, upcoming, completed };
}

/** Two short paragraphs about the team's season so far, chosen from the ratings row and schedule. */
export function teamSummary(content: TeamContent): string[] {
  const { snapshot, totalRated } = content;
  const { entry, latest, year, prime25Rank } = snapshot;
  const short = entry.team;
  if (!latest || !year) return [];
  const conf = conferenceName(entry.conf);
  const first: string[] = [];
  const status = [`${short} is ${latest.record} against FBS opponents through ${content.weekLabel ?? "the latest week"} of the ${year} season`];
  if (latest.rank) {
    let line = `${status[0]} and ranks ${noRank(latest.rank)} of ${totalRated} teams in PRIME's opponent-adjusted ratings`;
    if (latest.rankChange && Math.abs(latest.rankChange) >= 1) line += `, ${latest.rankChange > 0 ? "up" : "down"} ${plural(Math.abs(latest.rankChange), "spot")} from the previous week`;
    if (prime25Rank) line += ` and ${noRank(prime25Rank)} in The PRIME 25`;
    first.push(`${line}.`);
  } else {
    first.push(`${status[0]}; a PRIME rating is not yet available.`);
  }
  if (content.confRank && content.confTotal > 1 && entry.conf !== "IND") {
    first.push(`Within the ${conf}, that is ${ordinal(content.confRank)} of ${content.confTotal} rated teams.`);
  } else if (entry.conf === "IND" && content.confTotal > 1 && content.confRank) {
    first.push(`Among the ${content.confTotal} rated FBS independents, that is ${ordinal(content.confRank)}.`);
  }

  const second: string[] = [];
  const { adjORank: o, adjDRank: d } = latest;
  if (o && d) {
    const gap = o - d; // positive = defense is the better-ranked unit
    if (Math.abs(gap) <= 15) second.push(`The offense (${noRank(o)}) and defense (${noRank(d)}) grade out at a similar level.`);
    else if (gap > 0) second.push(`The defense (${noRank(d)}) is the stronger unit, ahead of the offense (${noRank(o)}).`);
    else second.push(`The offense (${noRank(o)}) is the stronger unit, ahead of the defense (${noRank(d)}).`);
  } else if (o) second.push(`The offense ranks ${noRank(o)} nationally.`);
  else if (d) second.push(`The defense ranks ${noRank(d)} nationally.`);

  const { sorRank: sor, sosRank: sos } = latest;
  if (sor && sos) {
    let line = `Its strength of record ranks ${noRank(sor)} and its strength of schedule ${noRank(sos)}`;
    const band = positionBand(sos, totalRated);
    line += band === "top" ? ", one of the tougher schedules played so far" : band === "bottom" ? ", one of the lighter schedules played so far" : "";
    second.push(`${line}.`);
    if (latest.rank && sor <= latest.rank - 15) second.push("Its résumé ranks well ahead of its overall rating.");
    else if (latest.rank && sor >= latest.rank + 15) second.push("Its résumé ranks behind its overall rating.");
  } else if (sor) second.push(`Its strength of record ranks ${noRank(sor)}.`);
  else if (sos) second.push(`Its strength of schedule ranks ${noRank(sos)}.`);

  const { next, last } = nextAndLast(content);
  const bits: string[] = [];
  if (last && teamResultText(last)) bits.push(`${short}'s most recent game was ${last.result === "W" ? "a win over" : last.result === "L" ? "a loss to" : "a tie with"} ${last.opponent} (${teamResultText(last)?.slice(2)}).`);
  if (next) {
    const date = formatGameDate(next.game, "short");
    const opp = `${next.opponentRank && next.opponentRank <= 25 ? `No. ${next.opponentRank} ` : ""}${next.opponent}`;
    bits.push(`Next up: ${next.game.neutralSite ? "a neutral-site game with" : next.home ? "a home game against" : "a road game at"} ${opp}${date ? ` on ${date}` : ""}.`);
  }
  return [first.join(" "), [...second, ...bits].join(" ")].filter(Boolean);
}

export type Glance = { label: string; value: string; rank?: string | null };
export function teamGlance(content: TeamContent): Glance[] {
  const { latest, prime25Rank, entry } = content.snapshot;
  if (!latest) return [];
  return [
    { label: "Conference", value: conferenceName(entry.conf) },
    { label: "Record (vs FBS)", value: latest.record },
    { label: "PRIME 25", value: prime25Rank ? `No. ${prime25Rank}` : "Unranked" },
    { label: "Overall rating", value: signedRating(latest.adjEM) ?? "—", rank: noRank(latest.rank) },
    { label: "Offense", value: signedRating(latest.adjO, 2) ?? "—", rank: noRank(latest.adjORank) },
    { label: "Defense", value: signedRating(latest.adjD, 2) ?? "—", rank: noRank(latest.adjDRank) },
    { label: "Strength of record", value: signedRating(latest.sor, 2) ?? "—", rank: noRank(latest.sorRank) },
    { label: "Strength of schedule", value: signedRating(latest.sos, 1) ?? "—", rank: noRank(latest.sosRank) },
  ];
}

// ---------------------------------------------------------------- matchup pages

const METRICS: { key: "rank" | "adjORank" | "adjDRank" | "sorRank"; noun: string }[] = [
  { key: "rank", noun: "overall rating" },
  { key: "adjORank", noun: "offensive rating" },
  { key: "adjDRank", noun: "defensive rating" },
  { key: "sorRank", noun: "strength of record" },
];

function topBucket(rank: number) {
  return [5, 10, 15, 25, 50].find((n) => rank <= n) ?? null;
}

/** Sentences comparing the two teams; a comparison is included only when both sides have the data and the gap is meaningful. */
export function matchupComparison(ctx: GameContext): string[] {
  const a = ctx.away.row;
  const h = ctx.home.row;
  if (!a || !h) return [];
  const threshold = Math.max(8, Math.round(ctx.totalRated * 0.06));
  const edges = { away: [] as string[], home: [] as string[] };
  for (const m of METRICS) {
    const ar = a[m.key];
    const hr = h[m.key];
    if (!ar || !hr || Math.abs(ar - hr) < threshold) continue;
    (ar < hr ? edges.away : edges.home).push(m.noun);
  }
  const out: string[] = [];
  const name = (side: MatchupSide) => side.name;
  const clause = (side: MatchupSide, list: string[]) => `${name(side)} holds the edge in ${joinList(list)}`;
  if (edges.away.length && edges.home.length) {
    out.push(`${clause(ctx.away, edges.away)}, while ${name(ctx.home)} holds the edge in ${joinList(edges.home)}.`);
  } else if (edges.away.length || edges.home.length) {
    const side = edges.away.length ? ctx.away : ctx.home;
    const other = edges.away.length ? ctx.home : ctx.away;
    const list = edges.away.length ? edges.away : edges.home;
    out.push(`${clause(side, list)}; ${name(other)} does not lead in any of the compared ratings by a meaningful margin.`);
  } else {
    out.push("The two teams grade out closely across overall, offensive and defensive ratings and strength of record.");
  }
  if (a.sosRank && h.sosRank && Math.abs(a.sosRank - h.sosRank) >= threshold) {
    const tougher = a.sosRank < h.sosRank ? ctx.away : ctx.home;
    out.push(`${name(tougher)} has played the tougher schedule so far (${noRank(tougher.row!.sosRank)}).`);
  }
  return out;
}

/** One paragraph: what the game is, when and where, how the teams are rated, and (if completed) the result. */
export function matchupSummary(ctx: GameContext): string {
  const { game, away, home } = ctx;
  const parts: string[] = [];
  const date = formatGameDate(game);
  const kickoff = formatKickoff(game);
  const where = game.venue ? ` at ${game.venue}` : "";
  const when = `${date ? ` on ${date}` : ""}${!game.completed && kickoff ? ` at ${kickoff}` : ""}`;
  const slot = ctx.weekLabel.startsWith("Week") ? `${ctx.weekLabel} of the ${ctx.season} season` : `the ${ctx.season} ${ctx.weekLabel}`;
  parts.push(
    game.neutralSite
      ? `${away.fullName} and ${home.fullName} ${game.completed ? "met" : "meet"} at a neutral site${where} in ${slot}${when}.`
      : `${away.fullName} ${game.completed ? "visited" : "visit"} ${home.fullName}${where} in ${slot}${when}.`
  );
  if (game.completed && game.awayPoints !== null && game.homePoints !== null) {
    if (game.awayPoints === game.homePoints) parts.push(`The game ended in a ${game.awayPoints}-${game.homePoints} tie.`);
    else {
      const awayWon = game.awayPoints > game.homePoints;
      const [w, l] = awayWon ? [away, home] : [home, away];
      const wp = Math.max(game.awayPoints, game.homePoints);
      const lp = Math.min(game.awayPoints, game.homePoints);
      parts.push(`${w.name} won ${wp}-${lp} over ${l.name}${wp - lp >= 28 ? ", a lopsided result" : wp - lp <= 3 ? ", a one-possession finish" : ""}.`);
    }
  }
  const ar = away.rank;
  const hr = home.rank;
  if (ar && hr) {
    const both = topBucket(Math.max(ar, hr));
    const label = ctx.ratingBasis === "pregame" ? "Entering the game" : "By current ratings";
    const core = ctx.ratingBasis === "pregame"
      ? `${label}, ${away.name} ranked ${noRank(ar)} and ${home.name} ${noRank(hr)} in PRIME's opponent-adjusted ratings`
      : `${label}, ${away.name} ranks ${noRank(ar)} and ${home.name} ${noRank(hr)} in PRIME's opponent-adjusted ratings`;
    parts.push(`${core}${both && both <= 25 ? `, with both teams inside the top ${both}` : ""}.`);
  } else if (ar || hr) {
    const rated = ar ? away : home;
    parts.push(`${rated.name} is rated ${noRank(ar || hr)} in PRIME's opponent-adjusted ratings; ${(ar ? home : away).name} is not in the FBS rating pool.`);
  }
  parts.push(...matchupComparison(ctx));
  return parts.join(" ");
}

export function matchupBasisNote(ctx: GameContext): string | null {
  if (ctx.ratingWeek === null || !ctx.ratingBasis) return null;
  const through = `through Week ${ctx.ratingWeek}`;
  return ctx.ratingBasis === "pregame" ? `Pregame PRIME ratings ${through}` : `Current PRIME ratings ${through}${ctx.game.completed ? " (after this game)" : ""}`;
}

export type CompareRow = { label: string; away: string; home: string };
export function matchupCompareRows(ctx: GameContext): CompareRow[] {
  const a = ctx.away.row;
  const h = ctx.home.row;
  if (!a || !h) return [];
  const rating = (r: RankingsRow, key: "adjEM" | "adjO" | "adjD" | "sor" | "sos", rankKey: "rank" | "adjORank" | "adjDRank" | "sorRank" | "sosRank", digits: number) => {
    const v = signedRating(r[key], digits);
    const rk = noRank(r[rankKey]);
    return v ? `${v}${rk ? ` (${rk})` : ""}` : "—";
  };
  const rows: CompareRow[] = [
    { label: "Record (vs FBS)", away: `${ctx.away.overallRecord} (${ctx.away.fbsRecord})`, home: `${ctx.home.overallRecord} (${ctx.home.fbsRecord})` },
    { label: "PRIME rating rank", away: noRank(a.rank) ?? "—", home: noRank(h.rank) ?? "—" },
    { label: "Overall rating", away: rating(a, "adjEM", "rank", 1), home: rating(h, "adjEM", "rank", 1) },
    { label: "Offense", away: rating(a, "adjO", "adjORank", 2), home: rating(h, "adjO", "adjORank", 2) },
    { label: "Defense", away: rating(a, "adjD", "adjDRank", 2), home: rating(h, "adjD", "adjDRank", 2) },
    { label: "Strength of record", away: rating(a, "sor", "sorRank", 2), home: rating(h, "sor", "sorRank", 2) },
    { label: "Strength of schedule", away: rating(a, "sos", "sosRank", 1), home: rating(h, "sos", "sosRank", 1) },
  ];
  if (ctx.away.prime25 || ctx.home.prime25) rows.splice(2, 0, { label: "The PRIME 25", away: ctx.away.prime25 ? `No. ${ctx.away.prime25}` : "Unranked", home: ctx.home.prime25 ? `No. ${ctx.home.prime25}` : "Unranked" });
  return rows;
}

// ---------------------------------------------------------------- section intros

export function topByMetric(rows: RankingsRow[], key: "rank" | "adjORank" | "adjDRank" | "sorRank" | "sosRank", n: number) {
  return rows.filter((r) => r[key] !== null && r[key] !== undefined).sort((a, b) => (a[key] as number) - (b[key] as number)).slice(0, n);
}
