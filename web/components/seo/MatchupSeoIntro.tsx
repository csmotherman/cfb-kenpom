import Link from "next/link";
import type { GameContext } from "@/lib/seoData";
import { matchupDescription, matchupHeading } from "@/lib/seoPages";

/** Server-rendered matchup summary shown while the interactive analysis loads: text plus links to both team profiles. */
export default function MatchupSeoIntro({ ctx }: { ctx: GameContext }) {
  return (
    <section className="container weekly-state seo-intro" aria-label="Matchup summary">
      <h1>{matchupHeading(ctx)}</h1>
      <p>{matchupDescription(ctx)}</p>
      <p className="seo-intro__links">
        <Link href={`/team/${ctx.away.slug}`}>{ctx.away.fullName} analytics</Link> ·{" "}
        <Link href={`/team/${ctx.home.slug}`}>{ctx.home.fullName} analytics</Link> ·{" "}
        <Link href="/predictions">Weekly predictions</Link> · <Link href="/ratings">Full PRIME Ratings</Link>
      </p>
    </section>
  );
}
