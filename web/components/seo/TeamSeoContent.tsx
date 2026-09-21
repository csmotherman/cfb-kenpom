/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import type { ReactNode } from "react";
import type { TeamContent } from "@/lib/seoData";
import { formatGameDate, formatKickoff, nextAndLast, signedRating, teamGameLabel, teamResultText, teamSummary } from "@/lib/seoContent";
import { conferenceName } from "@/lib/teamMascots";
import { logoUrl } from "@/lib/teamCode";

export type TeamSeoParts = { loading: ReactNode; summary: ReactNode; after: ReactNode };

const rankText = (n: number | null | undefined) => (n ? `#${n}` : "—");

function Tile({ label, short, value, rank }: { label: string; short: string; value: string; rank: number | null | undefined }) {
  return (
    <div className="team-v2-rating-tile">
      <div>
        <span>{label}</span>
        <small>{short}</small>
      </div>
      <span className="team-v2-stat">
        <strong className="mono">{value}</strong>
        <em className="team-v2-rank">{rankText(rank)}</em>
      </span>
    </div>
  );
}

/** Server copy of the profile masthead and rating strip, shown until the interactive profile has loaded. */
function Hero({ content }: { content: TeamContent }) {
  const { snapshot } = content;
  const { latest, entry, fullName, prime25Rank, year } = snapshot;
  if (!latest) {
    return (
      <section className="team-v2-masthead">
        <div className="team-v2-identity">
          <img src={logoUrl(entry.teamId, 192)} alt="" width={96} height={96} decoding="async" />
          <div><span>{conferenceName(entry.conf)}</span><h1>{fullName} <small className="team-v2-h1-sub">Football Analytics</small></h1></div>
        </div>
      </section>
    );
  }
  return (
    <>
      <section className="team-v2-masthead">
        <div className="team-v2-identity">
          <img src={logoUrl(entry.teamId, 192)} alt="" width={96} height={96} decoding="async" />
          <div>
            <span>{latest.conf} · {year} through {content.weekLabel}</span>
            <h1>{fullName} <small className="team-v2-h1-sub">Football Analytics</small></h1>
            <p>
              <strong>{latest.record}</strong>
              {" · "}
              {prime25Rank ? `PRIME 25 Rank #${prime25Rank}` : "PRIME 25 Rank —"}
              {" · "}
              {latest.rank ? `Power Rating #${latest.rank}` : "Power Rating unranked"}
            </p>
          </div>
        </div>
        <div className="team-v2-masthead__note">Value · national rank</div>
      </section>
      <section className="team-v2-rating-strip" aria-label="Current ratings">
        <Tile label="Overall" short="Power Rating" value={signedRating(latest.adjEM) ?? "—"} rank={latest.rank} />
        <Tile label="Offense" short="Off Rating" value={signedRating(latest.adjO, 2) ?? "—"} rank={latest.adjORank} />
        <Tile label="Defense" short="Def Rating" value={signedRating(latest.adjD, 2) ?? "—"} rank={latest.adjDRank} />
        <Tile label="Schedule" short="SOS" value={signedRating(latest.sos) ?? "—"} rank={latest.sosRank} />
        <Tile label="Résumé" short="SOR" value={signedRating(latest.sor) ?? "—"} rank={latest.sorRank} />
      </section>
    </>
  );
}

function Summary({ content }: { content: TeamContent }) {
  const paragraphs = teamSummary(content);
  if (!paragraphs.length) {
    const { fullName, year, entry } = content.snapshot;
    return (
      <section className="seo-section" aria-labelledby="team-glance-heading">
        <h2 id="team-glance-heading">{entry.team} at a Glance</h2>
        <p>{fullName} does not have a published PRIME rating for the {year} season yet. Ratings appear once a team has enough completed FBS-vs-FBS games.</p>
      </section>
    );
  }
  return (
    <section className="seo-section" aria-labelledby="team-glance-heading">
      <h2 id="team-glance-heading">{content.snapshot.entry.team} at a Glance</h2>
      {paragraphs.map((text) => <p key={text}>{text}</p>)}
    </section>
  );
}

function After({ content }: { content: TeamContent }) {
  const { snapshot, games } = content;
  const { entry, fullName, year, prime25Rank } = snapshot;
  const { next } = nextAndLast(content);
  return (
    <>
      {games.length ? (
        <section className="seo-section" aria-labelledby="team-schedule-heading">
          <h2 id="team-schedule-heading">{fullName} {year} Schedule and Results</h2>
          <div className="seo-table-wrap">
            <table className="seo-table">
              <thead>
                <tr><th scope="col">Week</th><th scope="col">Date</th><th scope="col">Opponent</th><th scope="col">Result</th><th scope="col">Game page</th></tr>
              </thead>
              <tbody>
                {games.map((row) => {
                  const { game } = row;
                  const date = formatGameDate(game, "short");
                  const kickoff = formatKickoff(game);
                  const opp = (
                    <>
                      {row.home ? "vs " : game.neutralSite ? "vs " : "at "}
                      {row.opponentRank && row.opponentRank <= 25 ? `No. ${row.opponentRank} ` : ""}
                      {row.opponentHasProfile ? <Link href={`/team/${row.opponentSlug}`}>{row.opponent}</Link> : <>{row.opponent} (FCS)</>}
                    </>
                  );
                  return (
                    <tr key={game.gameId}>
                      <td>{game.week}</td>
                      <td>{date ?? "TBA"}</td>
                      <td>{opp}</td>
                      <td>{teamResultText(row) ?? kickoff ?? (game.startTimeTBD ? "Time TBA" : "Upcoming")}</td>
                      <td><Link href={`/matchup/${snapshot.year}/${game.gameId}`}>{teamGameLabel(row)}</Link></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="seo-note">Ratings and records count completed FBS-vs-FBS games only. Ranks shown beside opponents are current PRIME rating ranks.</p>
        </section>
      ) : null}
      <nav className="seo-section seo-links" aria-labelledby="team-links-heading">
        <h2 id="team-links-heading">Explore {entry.team} Analytics</h2>
        <ul>
          <li><Link href="/ratings">PRIME college football ratings</Link></li>
          <li><Link href="/rankings">{prime25Rank ? `The PRIME 25 (${entry.team} is No. ${prime25Rank})` : "The PRIME 25 rankings"}</Link></li>
          <li><Link href="/predictions">Weekly college football predictions</Link></li>
          {next ? <li><Link href={`/matchup/${year}/${next.game.gameId}`}>{teamGameLabel(next)}</Link></li> : null}
          <li><Link href={`/teams#conf-${entry.conf.toLowerCase()}`}>All {conferenceName(entry.conf)} teams</Link></li>
          <li><Link href="/methodology">How PRIME ratings are calculated</Link></li>
        </ul>
      </nav>
    </>
  );
}

export function buildTeamSeoParts(content: TeamContent): TeamSeoParts {
  const summary = <Summary content={content} />;
  const after = <After content={content} />;
  return {
    summary,
    after,
    loading: (
      <main id="teamContent" className="container team-v2-main">
        <Hero content={content} />
        {summary}
        {after}
      </main>
    ),
  };
}
