import Link from "next/link";
import type { ReactNode } from "react";
import { getLatestSnapshot, readPublicData, getLatestYear, getPrimeRankingsServer, getScheduleServer, getSiteMeta, getTeamDirectory } from "@/lib/seoData";
import { conferenceName } from "@/lib/teamMascots";
import { formatGameDate, formatKickoff, noRank, signedRating, topByMetric } from "@/lib/seoContent";
import type { RankingsRow, ScheduleGame } from "@/lib/types";

const teamLink = (row: { team: string; slug: string }) => <Link href={`/team/${row.slug}`}>{row.team}</Link>;

function inline(nodes: ReactNode[]) {
  return nodes.map((node, i) => (
    <span key={i}>
      {node}
      {i < nodes.length - 2 ? ", " : i === nodes.length - 2 ? (nodes.length > 2 ? ", and " : " and ") : ""}
    </span>
  ));
}

async function slate(year: number, rows: RankingsRow[]) {
  const schedule = await getScheduleServer(year);
  if (!schedule) return null;
  const all = Object.values(schedule.byWeek).flat();
  const upcomingWeeks = [...new Set(all.filter((g) => !g.completed).map((g) => g.week))].sort((a, b) => a - b);
  const week = upcomingWeeks[0] ?? null;
  if (week === null) return null;
  const games = all.filter((g) => g.week === week);
  const rankOf = new Map(rows.map((r) => [r.slug, r.rank]));
  const featured = games
    .map((g) => ({ g, a: rankOf.get(g.awaySlug) ?? null, h: rankOf.get(g.homeSlug) ?? null }))
    .filter((x): x is { g: ScheduleGame; a: number; h: number } => !!x.a && !!x.h)
    .sort((x, y) => x.a + x.h - (y.a + y.h));
  return { week, label: schedule.weekLabels?.[String(week)] || `Week ${week}`, total: games.length, featured };
}

export async function RatingsSeoContent() {
  const year = await getLatestYear();
  if (!year) return null;
  const { rows, week, season } = await getLatestSnapshot(year);
  if (!rows.length) return null;
  const meta = await getSiteMeta();
  const rated = rows.filter((r) => r.rank !== null);
  const top = topByMetric(rows, "rank", 10);
  const leader = top[0];
  const weekLabel = week === null ? "the latest week" : season?.weekLabels?.[String(week)] || `Week ${week}`;
  const firstYear = meta?.rankingsYears?.length ? Math.min(...meta.rankingsYears) : null;
  const lists: { title: string; rows: RankingsRow[]; value: (r: RankingsRow) => string }[] = [
    { title: "Best overall", rows: top, value: (r) => signedRating(r.adjEM) ?? "" },
    { title: "Best offenses", rows: topByMetric(rows, "adjORank", 5), value: (r) => signedRating(r.adjO, 2) ?? "" },
    { title: "Best defenses", rows: topByMetric(rows, "adjDRank", 5), value: (r) => signedRating(r.adjD, 2) ?? "" },
    { title: "Best strength of record", rows: topByMetric(rows, "sorRank", 5), value: (r) => signedRating(r.sor, 2) ?? "" },
    { title: "Toughest schedules", rows: topByMetric(rows, "sosRank", 5), value: (r) => signedRating(r.sos) ?? "" },
  ];
  return (
    <section className="container seo-section" aria-labelledby="ratings-about-heading">
      <h2 id="ratings-about-heading">How to Read the {year} PRIME Ratings</h2>
      <p>
        PRIME rates every FBS team on how well it has played this season after adjusting for the strength of the opponents it faced.
        Through {weekLabel}, {rated.length} teams are rated{leader ? <>, led by {teamLink(leader)} at {signedRating(leader.adjEM)}</> : null}.
        A team&rsquo;s overall rating is its offensive rating plus its defensive rating, and zero is roughly an average FBS team.
        Strength of record (SOR) measures wins above what an average team would expect against the same schedule, so it is a résumé measure separate from the overall rating.
        {firstYear ? <> Ratings are available back to {firstYear}; use the season selector above.</> : null}
      </p>
      <div className="seo-leaders">
        {lists.map((list) => (
          <div key={list.title}>
            <h3>{list.title}</h3>
            <ol>
              {list.rows.map((row) => (
                <li key={row.slug}>{teamLink(row)} <span className="seo-note">{list.value(row)}</span></li>
              ))}
            </ol>
          </div>
        ))}
      </div>
      <p>
        See <Link href="/rankings">The PRIME 25</Link> for the résumé-based ranking, <Link href="/predictions">weekly predictions</Link> for upcoming games,
        the <Link href="/teams">directory of every FBS team</Link>, or <Link href="/methodology">how the ratings are calculated</Link>.
      </p>
    </section>
  );
}

export async function RankingsSeoContent() {
  const year = await getLatestYear();
  const prime = year ? await getPrimeRankingsServer(year) : null;
  if (!prime?.teams.length) return null;
  const top = prime.teams.slice(0, 5);
  const byConf = new Map<string, number>();
  for (const team of prime.teams) byConf.set(team.conf, (byConf.get(team.conf) ?? 0) + 1);
  const confs = [...byConf.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).filter(([, n]) => n >= 2);
  const released = new Date(prime.releasedAt);
  const releasedText = Number.isNaN(released.getTime()) ? null : released.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "America/New_York" });
  return (
    <section className="container seo-section" aria-labelledby="rankings-about-heading">
      <h2 id="rankings-about-heading">The PRIME 25 Through Week {prime.throughWeek}, {prime.season}</h2>
      <p>
        The PRIME 25 ranks the teams that have earned it this season. It combines a team&rsquo;s opponent-adjusted performance rating with its strength of record,
        and it ignores preseason polls, brand names and voter opinion.
        In the {releasedText ? `${releasedText} ` : ""}release, {inline(top.map((t) => <span key={t.slug}>{teamLink(t)} ({t.record})</span>))} make up the top five.
        {confs.length ? <> The {conferenceName(confs[0][0])} has the most teams in the PRIME 25 with {confs[0][1]}{confs.length > 1 ? <>, followed by {inline(confs.slice(1, 3).map(([c, n]) => <span key={c}>{conferenceName(c)} ({n})</span>))}</> : null}.</> : null}
      </p>
      <p>
        The ranking differs from the <Link href="/ratings">PRIME Ratings</Link>, which measure how well a team has played; the PRIME 25 also rewards what a team has accomplished on its schedule.
        Read <Link href="/methodology">the methodology</Link>, browse <Link href="/teams">every FBS team</Link>, or see <Link href="/predictions">this week&rsquo;s predictions</Link>.
      </p>
    </section>
  );
}

export async function PredictionsSeoIntro() {
  const year = await getLatestYear();
  if (!year) return null;
  const { rows } = await getLatestSnapshot(year);
  const s = await slate(year, rows);
  return (
    <section className="seo-lede" aria-labelledby="predictions-heading">
      <h1 id="predictions-heading">{year} College Football Predictions</h1>
      <p>
        PRIME publishes a model-generated prediction and matchup breakdown for FBS games each week, built from opponent-adjusted ratings.
        {s ? ` The next slate is ${s.label}, with ${s.total} games on the schedule.` : ""} Predictions are projections, not betting advice.
      </p>
    </section>
  );
}

export async function PredictionsSeoContent() {
  const year = await getLatestYear();
  if (!year) return null;
  const { rows } = await getLatestSnapshot(year);
  const s = await slate(year, rows);
  if (!s) return null;
  const show = s.featured.slice(0, 12);
  return (
    <section className="container seo-section" aria-labelledby="predictions-slate-heading">
      <h2 id="predictions-slate-heading">{s.label} Matchups to Watch</h2>
      <p>
        {s.total} games are scheduled for {s.label} of the {year} season.
        {show.length ? " These are the games between the highest-rated teams by current PRIME rating; each page compares the two teams side by side." : ""}
      </p>
      {show.length ? (
        <ul className="seo-list">
          {show.map(({ g, a, h }) => {
            const date = formatGameDate(g, "short");
            const time = formatKickoff(g);
            return (
              <li key={g.gameId}>
                <Link href={`/matchup/${year}/${g.gameId}`}>{g.awayTeam} {g.neutralSite ? "vs" : "at"} {g.homeTeam} prediction</Link>{" "}
                <span className="seo-note">({noRank(a)} vs {noRank(h)}{date ? `, ${date}` : ""}{time ? `, ${time}` : ""})</span>
              </li>
            );
          })}
        </ul>
      ) : null}
      <p>Ratings behind these comparisons are explained on the <Link href="/ratings">Ratings page</Link>, and every team has a <Link href="/teams">profile</Link>. See <Link href="/predictions/performance">how PRIME&rsquo;s past predictions performed</Link>.</p>
    </section>
  );
}

export async function HomeSeoContent() {
  const year = await getLatestYear();
  if (!year) return null;
  const [{ rows, week }, prime, directory] = await Promise.all([getLatestSnapshot(year), getPrimeRankingsServer(year), getTeamDirectory()]);
  const s = await slate(year, rows);
  const top = (prime?.teams ?? []).slice(0, 5);
  return (
    <section className="container seo-section" aria-labelledby="home-about-heading">
      <h2 id="home-about-heading">Opponent-Adjusted College Football Analytics</h2>
      <p>
        PRIME rates {rows.filter((r) => r.rank !== null).length || directory.length || "every"} FBS teams by how well they play once opponent strength is removed, ranks the teams that have earned it in The PRIME 25, and
        publishes weekly predictions and matchup breakdowns.
        {week !== null && top.length ? <> Through Week {week} of the {year} season, the top of The PRIME 25 is {inline(top.map((t) => teamLink(t)))}.</> : null}
      </p>
      {s?.featured.length ? (
        <p>
          Featured {s.label} matchups: {inline(s.featured.slice(0, 3).map(({ g }) => <Link key={g.gameId} href={`/matchup/${year}/${g.gameId}`}>{g.awayTeam} {g.neutralSite ? "vs" : "at"} {g.homeTeam}</Link>))}.
        </p>
      ) : null}
      <p>
        Explore the <Link href="/ratings">college football ratings</Link>, the <Link href="/rankings">PRIME 25</Link>, <Link href="/predictions">weekly predictions</Link>,
        the <Link href="/teams">team directory</Link>, or read <Link href="/methodology">how it all works</Link>.
      </p>
    </section>
  );
}

type TrackRecordOverall = { games?: number; graded?: number; correct?: number; accuracySU?: number; avgAbsMarginError?: number; within7Pct?: number; within14Pct?: number };
type TrackRecordMarket = { games?: number; primeSU?: number; marketSU?: number; primeMAE?: number; marketMAE?: number };

/** Visible H1 and a factual summary of the published, graded track record (the same numbers the page shows once loaded). */
export async function PerformanceSeoIntro() {
  const year = await getLatestYear();
  const record = year ? ((await readPublicData(`prediction-track-record/${year}.json`)) as { overall?: TrackRecordOverall; market?: TrackRecordMarket } | null) : null;
  const o = record?.overall;
  const facts = o?.graded && o.correct !== undefined && o.accuracySU !== undefined && o.avgAbsMarginError !== undefined
    ? ` Through the latest graded week of ${year}, PRIME picked the winner in ${o.correct} of ${o.graded} graded games (${(o.accuracySU * 100).toFixed(1)}%) with an average margin error of ${o.avgAbsMarginError.toFixed(1)} points.`
    : "";
  const m = record?.market;
  const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
  const spread = o?.within7Pct !== undefined && o.within14Pct !== undefined
    ? ` ${pct(o.within7Pct)} of graded games landed within 7 points of the final margin and ${pct(o.within14Pct)} within 14.`
    : "";
  const market = m?.games && m.primeSU !== undefined && m.marketSU !== undefined && m.primeMAE !== undefined && m.marketMAE !== undefined
    ? ` On the ${m.games} graded games that also have a betting-market line, PRIME picked ${pct(m.primeSU)} of winners against ${pct(m.marketSU)} for the market, with an average margin error of ${m.primeMAE.toFixed(1)} points against ${m.marketMAE.toFixed(1)}.`
    : "";
  return (
    <section className="seo-lede" aria-labelledby="performance-heading">
      <h1 id="performance-heading">Model Performance</h1>
      <p>
        Every PRIME prediction is frozen before kickoff and graded against the final score, with winner accuracy, margin error and calibration published for anyone to check.{facts}{spread}{market}{" "}
        See <Link href="/predictions">this week&rsquo;s predictions</Link> and <Link href="/methodology">the methodology</Link>.
      </p>
    </section>
  );
}
