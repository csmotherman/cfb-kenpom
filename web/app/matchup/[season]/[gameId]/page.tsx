import type { Metadata } from "next";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import MatchupSeoIntro from "@/components/seo/MatchupSeoIntro";
import { noIndexMetadata } from "@/lib/seo";
import { getDataTimestamp, getGameContext, getLatestYear, getScheduleServer } from "@/lib/seoData";
import { matchupHeading, matchupJsonLd, matchupMetadata } from "@/lib/seoPages";
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
  if (ctx === undefined) return <MatchupClient season={season} gameId={gameId} heading="College football matchup analytics" intro={null} />;
  return (
    <>
      <JsonLd data={matchupJsonLd(ctx, await getDataTimestamp())} />
      <MatchupClient season={season} gameId={gameId} heading={matchupHeading(ctx)} intro={<MatchupSeoIntro ctx={ctx} />} />
    </>
  );
}
