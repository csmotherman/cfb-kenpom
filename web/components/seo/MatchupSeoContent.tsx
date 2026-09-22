import Link from "next/link";
import type { ReactNode } from "react";
import type { GameContext, MatchupSide } from "@/lib/seoData";
import { matchupCompareRows, matchupSummary } from "@/lib/seoContent";
import Breadcrumbs from "@/components/seo/Breadcrumbs";
import { matchupHeading, matchupPath } from "@/lib/seoPages";
import { logoUrl } from "@/lib/teamCode";

export type MatchupSeoParts = { loading: ReactNode; lede: ReactNode; facts: ReactNode };

/** Shared by the visible breadcrumbs and the BreadcrumbList JSON-LD. */
export const matchupCrumbs = (ctx: GameContext) => [
  { name: "Home", path: "/" },
  { name: "Predictions", path: "/predictions" },
  { name: `${ctx.away.name} vs ${ctx.home.name}`, path: matchupPath(ctx.season, String(ctx.game.gameId)) },
];

function Lede({ ctx }: { ctx: GameContext }) {
  return (
    <section className="seo-lede" aria-labelledby="matchup-heading">
      <Breadcrumbs items={matchupCrumbs(ctx)} />
      <h1 id="matchup-heading">{matchupHeading(ctx)}</h1>
      <p>{matchupSummary(ctx)}</p>
    </section>
  );
}

function TeamLink({ side }: { side: MatchupSide }) {
  return side.hasProfile ? <Link href={`/team/${side.slug}`}>{side.fullName} analytics and ratings</Link> : <>{side.name} (FCS; no PRIME profile)</>;
}

function Facts({ ctx }: { ctx: GameContext }) {
  const rows = matchupCompareRows(ctx);
  return (
    <>
      {rows.length ? (
        <section className="seo-section matchup-comparison" aria-labelledby="matchup-compare-heading">
          <h2 id="matchup-compare-heading">Team Comparison</h2>
          <div className="seo-table-wrap">
            <table className="seo-table seo-table--compare">
              <thead>
                <tr>
                  <th scope="col">
                    <div className="matchup-comparison__team">
                      <img src={logoUrl(ctx.game.awayTeamId, 128)} alt="" width={56} height={56} decoding="async" />
                      <span>{ctx.away.name}</span>
                    </div>
                  </th>
                  <th scope="col"><span className="matchup-comparison__versus" aria-hidden="true">VS</span><span className="sr-only">Metric</span></th>
                  <th scope="col">
                    <div className="matchup-comparison__team">
                      <img src={logoUrl(ctx.game.homeTeamId, 128)} alt="" width={56} height={56} decoding="async" />
                      <span>{ctx.home.name}</span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.label}>
                    <td>{row.away}</td>
                    <th scope="row">{row.label}</th>
                    <td>{row.home}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="seo-note">
            Stats include games completed before this matchup. Records show overall results first, with FBS-only records in parentheses. Neutral-site games are excluded from home and road records.
          </p>
        </section>
      ) : null}
      <nav className="seo-section seo-links" aria-labelledby="matchup-links-heading">
        <h2 id="matchup-links-heading">More {ctx.away.name} and {ctx.home.name} Analytics</h2>
        <ul>
          <li><TeamLink side={ctx.away} /></li>
          <li><TeamLink side={ctx.home} /></li>
          {ctx.currentSeason ? <li><Link href={`/predictions?week=${ctx.game.week}`}>All {ctx.weekLabel} college football games</Link></li> : null}
          <li><Link href="/predictions">Weekly college football predictions</Link></li>
          <li><Link href="/ratings">PRIME college football ratings</Link></li>
          <li><Link href="/rankings">The PRIME 25 rankings</Link></li>
        </ul>
      </nav>
    </>
  );
}

export function buildMatchupSeoParts(ctx: GameContext): MatchupSeoParts {
  const lede = <Lede ctx={ctx} />;
  const facts = <Facts ctx={ctx} />;
  return {
    lede,
    facts,
    loading: (
      <main id="matchupContent" className="container matchup-v2-main">
        {lede}
        {facts}
      </main>
    ),
  };
}
