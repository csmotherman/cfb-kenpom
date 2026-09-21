import type { Metadata } from "next";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import { buildMatchupSeoParts } from "@/components/seo/MatchupSeoContent";
import { noIndexMetadata } from "@/lib/seo";
import { getDataTimestamp, getGameContext, getLatestYear, getScheduleServer } from "@/lib/seoData";
import { gameModified, matchupHeading, matchupJsonLd, matchupMetadata } from "@/lib/seoPages";
import MatchupClient from "./MatchupClient";

type Params = { params: Promise<{ season: string; gameId: string }> };

// Current-season games are prebuilt; any other season's game is rendered on demand from the same published schedule.
export async function generateStaticParams() {
  const year = await getLatestYear();
  const schedule = year ? await getScheduleServer(year) : null;
  if (!year || !schedule) return [];
  return Object.values(schedule.byWeek).flat().map((game) => ({ season: String(year), gameId: String(game.gameId) }));
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { season, gameId } = await params;
  const ctx = await getGameContext(season, gameId);
  if (!ctx) return noIndexMetadata("Matchup analytics", "College football matchup analytics from PRIME.");
  return matchupMetadata(ctx);
}

export default async function MatchupPage({ params }: Params) {
  const { season, gameId } = await params;
  const ctx = await getGameContext(season, gameId);
  if (ctx === null) notFound();
  if (ctx === undefined) return <MatchupClient season={season} gameId={gameId} heading="College football matchup analytics" seo={null} />;
  return (
    <>
      <JsonLd data={matchupJsonLd(ctx, gameModified(ctx.game, await getDataTimestamp()))} />
      <MatchupClient season={season} gameId={gameId} heading={matchupHeading(ctx)} seo={buildMatchupSeoParts(ctx)} />
    </>
  );
}
