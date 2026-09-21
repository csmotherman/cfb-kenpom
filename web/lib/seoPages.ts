// Page-specific metadata and structured data for the dynamic routes (team profiles and matchups).
import type { Metadata } from "next";
import {
  breadcrumbJsonLd,
  clampDescription,
  pageMetadata,
  sportsEventJsonLd,
  sportsTeamJsonLd,
  webPageJsonLd,
  absoluteUrl,
  type JsonLd,
} from "@/lib/seo";
import { isIndexableGame, type GameContext, type TeamSnapshot } from "@/lib/seoData";
import { formatGameDate } from "@/lib/seoContent";
import { logoUrl } from "@/lib/teamCode";
import { conferenceName } from "@/lib/teamMascots";

const ordinalRank = (n: number | null | undefined) => (n ? `#${n}` : null);

export function teamPath(slug: string) {
  return `/team/${slug}`;
}

export function matchupPath(season: number | string, gameId: string) {
  return `/matchup/${season}/${gameId}`;
}

/** Stable, readable title; the changing numbers live in the description and page, never the title. */
export function teamTitle(snapshot: TeamSnapshot) {
  return `${snapshot.fullName} Football Analytics`;
}

export function teamDescription(snapshot: TeamSnapshot) {
  const { fullName, entry, latest, year, week, prime25Rank } = snapshot;
  const base = "Opponent-adjusted efficiency ratings, schedule strength, advanced stats and game results.";
  if (!latest || !year) {
    return `${fullName} ratings, offensive and defensive efficiency, schedule strength, advanced stats and game results from PRIME's opponent-adjusted college football analytics.`;
  }
  const parts = [
    `${fullName} (${latest.record}, ${conferenceName(entry.conf)})`,
    prime25Rank ? `#${prime25Rank} in The PRIME 25` : null,
    ordinalRank(latest.rank) ? `${ordinalRank(latest.rank)} PRIME power rating` : null,
    ordinalRank(latest.adjORank) && ordinalRank(latest.adjDRank) ? `offense ${ordinalRank(latest.adjORank)}, defense ${ordinalRank(latest.adjDRank)}` : null,
  ].filter(Boolean);
  return `${parts.join(", ")}. ${year}${week !== null ? ` through Week ${week}` : ""}. ${base}`;
}

export function teamMetadata(snapshot: TeamSnapshot): Metadata {
  return pageMetadata({
    title: teamTitle(snapshot),
    description: teamDescription(snapshot),
    path: teamPath(snapshot.entry.slug),
    // A team with no published rating this season has nothing to show beyond a schedule: keep it reachable, out of results.
    noindex: !snapshot.latest,
    follow: true,
    image: { params: { kind: "team", slug: snapshot.entry.slug }, alt: `${snapshot.fullName} football analytics from PRIME` },
  });
}

export function teamJsonLd(snapshot: TeamSnapshot, dateModified: string | null): JsonLd[] {
  const path = teamPath(snapshot.entry.slug);
  return [
    { ...webPageJsonLd({ path, name: `${snapshot.fullName} Football Analytics`, description: teamDescription(snapshot), dateModified }), mainEntity: sportsTeamJsonLd({ name: snapshot.fullName, path, conference: conferenceName(snapshot.entry.conf), logo: logoUrl(snapshot.entry.teamId, 128) }) },
    breadcrumbJsonLd([
      { name: "Home", path: "/" },
      { name: "Teams", path: "/teams" },
      { name: snapshot.fullName, path },
    ]),
  ];
}

/** Completed games are final at kickoff-day content; upcoming games change with every ratings refresh. Never later than the data timestamp. */
export function gameModified(game: { completed: boolean; startDate: string | null }, generated: string | null | undefined): string | null {
  if (!game.completed) return generated ?? null;
  const t = game.startDate ? new Date(game.startDate).getTime() : NaN;
  if (Number.isNaN(t)) return null;
  return generated && t > new Date(generated).getTime() ? generated : new Date(t).toISOString();
}

export function matchupHeading(ctx: GameContext) {
  return ctx.game.completed
    ? `${ctx.away.name} vs ${ctx.home.name} Game Analytics & Result`
    : `${ctx.away.name} vs ${ctx.home.name} Prediction & Analytics`;
}

export function matchupDescription(ctx: GameContext) {
  const when = ctx.game.startDate ? formatGameDate(ctx.game, "short") : null;
  const where = ctx.game.venue ? ` at ${ctx.game.venue}` : "";
  const ranks = ctx.away.rank && ctx.home.rank ? ` PRIME power ratings: ${ctx.away.name} #${ctx.away.rank}, ${ctx.home.name} #${ctx.home.rank}.` : "";
  const score = ctx.game.completed && ctx.game.awayPoints !== null && ctx.game.homePoints !== null
    ? ` Final: ${ctx.away.name} ${ctx.game.awayPoints}, ${ctx.home.name} ${ctx.game.homePoints}.`
    : "";
  return `${ctx.away.fullName} ${ctx.game.neutralSite ? "vs" : "at"} ${ctx.home.fullName}${where}, ${ctx.weekLabel} of the ${ctx.season} college football season${when ? ` (${when})` : ""}.${score}${ranks} Matchup analytics, efficiency comparisons and PRIME's game breakdown.`;
}

// Public metadata only: the predicted margin and win probability are premium data and are never placed here.
export function matchupMetadata(ctx: GameContext): Metadata {
  return pageMetadata({
    title: matchupHeading(ctx),
    description: matchupDescription(ctx),
    path: matchupPath(ctx.season, String(ctx.game.gameId)),
    // FBS-vs-FCS games have no rating comparison to offer; keep them reachable (noindex, follow) but out of search results.
    noindex: !isIndexableGame(ctx),
    follow: true,
    image: { params: { kind: "matchup", season: ctx.season, game: String(ctx.game.gameId) }, alt: `${ctx.away.name} vs ${ctx.home.name} matchup analytics from PRIME` },
  });
}

export function matchupJsonLd(ctx: GameContext, dateModified: string | null): JsonLd[] {
  const path = matchupPath(ctx.season, String(ctx.game.gameId));
  const name = `${ctx.away.name} vs ${ctx.home.name}`;
  return [
    { ...webPageJsonLd({ path, name: matchupHeading(ctx), description: matchupDescription(ctx), dateModified }), about: { "@id": `${absoluteUrl(path)}#event` } },
    { ...sportsEventJsonLd({ path, name, startDate: ctx.game.startDate, homeTeam: ctx.home.fullName, awayTeam: ctx.away.fullName, venue: ctx.game.venue, description: matchupDescription(ctx) }), "@id": `${absoluteUrl(path)}#event` },
    breadcrumbJsonLd([
      { name: "Home", path: "/" },
      { name: "Predictions", path: "/predictions" },
      { name, path },
    ]),
  ];
}

export { clampDescription };
