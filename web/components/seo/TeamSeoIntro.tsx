import Link from "next/link";
import { fullTeamName } from "@/lib/teamMascots";
import { getLatestYear, getScheduleServer, type TeamSnapshot } from "@/lib/seoData";
import { teamDescription } from "@/lib/seoPages";

/** Server-rendered team summary shown while the interactive profile loads: real text and real links for crawlers and no-JS readers. */
export default async function TeamSeoIntro({ snapshot }: { snapshot: TeamSnapshot }) {
  const year = await getLatestYear();
  const schedule = year ? await getScheduleServer(year) : null;
  const games = schedule
    ? Object.values(schedule.byWeek).flat().filter((g) => g.homeSlug === snapshot.entry.slug || g.awaySlug === snapshot.entry.slug)
    : [];
  return (
    <main id="teamContent" className="container weekly-state seo-intro">
      <h1>{snapshot.fullName}</h1>
      <p>{teamDescription(snapshot)}</p>
      {games.length ? (
        <>
          <h2>{snapshot.fullName} {year} schedule and results</h2>
          <ul className="seo-intro__list">
            {games.map((g) => {
              const home = g.homeSlug === snapshot.entry.slug;
              const opponent = home ? g.awayTeam : g.homeTeam;
              const score = g.completed && g.homePoints !== null && g.awayPoints !== null
                ? `, ${home ? g.homePoints : g.awayPoints}-${home ? g.awayPoints : g.homePoints}`
                : "";
              return (
                <li key={g.gameId}>
                  <Link href={`/matchup/${year}/${g.gameId}`}>
                    {g.awayTeam} {g.neutralSite ? "vs" : "at"} {g.homeTeam}
                  </Link>{" "}
                  <span>(Week {g.week}{score}; {home ? "home" : "away"} vs {fullTeamName(opponent)})</span>
                </li>
              );
            })}
          </ul>
        </>
      ) : null}
      <p className="seo-intro__links">
        <Link href="/ratings">Full PRIME Ratings</Link> · <Link href="/rankings">The PRIME 25</Link> · <Link href="/teams">All FBS teams</Link>
      </p>
    </main>
  );
}
