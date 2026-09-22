import Link from "next/link";
import type { ReactNode } from "react";
import type { GameContext, MatchupSide } from "@/lib/seoData";
import { matchupBasisNote, matchupCompareRows, matchupSummary, teamResultText } from "@/lib/seoContent";
import Breadcrumbs from "@/components/seo/Breadcrumbs";
import { matchupHeading, matchupPath } from "@/lib/seoPages";

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

function Form({ side }: { side: MatchupSide }) {
  if (!side.form.length) return null;
  return (
    <div>
      <h3>{side.name} recent results</h3>
      <ul>
        {side.form.map((row) => (
          <li key={row.game.gameId}>
            {teamResultText(row) ?? "Final"} {row.home ? "vs" : row.game.neutralSite ? "vs" : "at"} {row.opponent}
            {row.opponentHasProfile ? "" : " (FCS)"} <span>(Week {row.game.week})</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TeamLink({ side }: { side: MatchupSide }) {
  return side.hasProfile ? <Link href={`/team/${side.slug}`}>{side.fullName} analytics and ratings</Link> : <>{side.name} (FCS; no PRIME profile)</>;
}

function Facts({ ctx }: { ctx: GameContext }) {
  const rows = matchupCompareRows(ctx);
  const note = matchupBasisNote(ctx);
  const hasForm = ctx.away.form.length > 0 || ctx.home.form.length > 0;
  return (
    <>
      {rows.length ? (
        <section className="seo-section" aria-labelledby="matchup-compare-heading">
          <h2 id="matchup-compare-heading">{ctx.away.name} vs {ctx.home.name} Team Comparison</h2>
          <div className="seo-table-wrap">
            <table className="seo-table seo-table--compare">
              <thead>
                <tr>
                  <th scope="col">{ctx.away.name}</th>
                  <th scope="col"><span className="sr-only">Metric</span></th>
                  <th scope="col">{ctx.home.name}</th>
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
            {note ? `${note}. ` : ""}Records show overall results first, with FBS-only records in parentheses. Ratings and ranks count FBS-vs-FBS games only. Rating values are opponent-adjusted; strength of schedule rank 1 is the toughest schedule.
          </p>
        </section>
      ) : null}
      {hasForm ? (
        <section className="seo-section" aria-labelledby="matchup-form-heading">
          <h2 id="matchup-form-heading">Recent Form Entering {ctx.weekLabel}</h2>
          <div className="seo-form">
            <Form side={ctx.away} />
            <Form side={ctx.home} />
          </div>
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
