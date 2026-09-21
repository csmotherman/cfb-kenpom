import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import Breadcrumbs from "@/components/seo/Breadcrumbs";
import SiteFooter from "@/components/SiteFooter";
import SiteNav from "@/components/SiteNav";
import { breadcrumbJsonLd, itemListJsonLd, noIndexMetadata, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { formatGameDate, formatKickoff, noRank } from "@/lib/seoContent";
import { MIN_HUB_GAMES, getDataTimestamp, getLatestYear, getScheduleServer, getWeekHub, type WeekHub } from "@/lib/seoData";
import { gameModified } from "@/lib/seoPages";

type Params = { params: Promise<{ week: string }> };

// Current-season weeks only, prebuilt from the published schedule. There is one URL per week (15 at most), never per filter.
export const dynamicParams = false;
export async function generateStaticParams() {
  const year = await getLatestYear();
  const schedule = year ? await getScheduleServer(year) : null;
  return (schedule?.weeks ?? []).map((week) => ({ week: String(week) }));
}

const parseWeek = (value: string) => (/^\d{1,2}$/.test(value) ? Number.parseInt(value, 10) : null);
const titleFor = (hub: WeekHub) => `${hub.label} College Football Schedule & Matchup Analytics`;

function summary(hub: WeekHub): string {
  const games = hub.games;
  const topPairs = games.filter((g) => g.awayRank! <= 25 && g.homeRank! <= 25).length;
  const top = games[0];
  const parts = [
    `${hub.label} of the ${hub.year} college football season has ${games.length} FBS-vs-FBS ${games.length === 1 ? "game" : "games"} with PRIME ratings on both sides.`,
  ];
  if (topPairs > 0) parts.push(`${topPairs} ${topPairs === 1 ? "game features" : "games feature"} two teams from PRIME's top 25 by rating.`);
  if (top && top.awayRank! + top.homeRank! < 60) parts.push(`The highest-rated matchup is ${top.game.awayTeam} ${top.game.neutralSite ? "vs" : "at"} ${top.game.homeTeam} (${noRank(top.awayRank)} vs ${noRank(top.homeRank)}).`);
  if (hub.played) parts.push("All of these games have been played; open a game for the final result and team comparison.");
  return parts.join(" ");
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const week = parseWeek((await params).week);
  const hub = week === null ? null : await getWeekHub(week);
  if (!hub) return noIndexMetadata("Week schedule", "College football weekly schedule and matchup analytics from PRIME.");
  return pageMetadata({
    title: titleFor(hub),
    description: `${hub.label} of the ${hub.year} college football season: every FBS-vs-FBS game with PRIME rating ranks, kickoff times or final scores, and links to each matchup's analytics.`,
    path: `/week/${hub.week}`,
    noindex: hub.games.length < MIN_HUB_GAMES,
    follow: true,
    image: { params: { kind: "predictions" }, alt: `${hub.label} college football matchups from PRIME` },
  });
}

export default async function WeekPage({ params }: Params) {
  const week = parseWeek((await params).week);
  const hub = week === null ? null : await getWeekHub(week);
  if (!hub) notFound();
  const modified = hub.played
    ? gameModified({ completed: true, startDate: hub.games.map((g) => g.game.startDate ?? "").sort().pop() || null }, await getDataTimestamp())
    : await getDataTimestamp();
  const path = `/week/${hub.week}`;
  const crumbs = [{ name: "Home", path: "/" }, { name: "Predictions", path: "/predictions" }, { name: hub.label, path }];
  const idx = hub.weeks.findIndex((w) => w.week === hub.week);
  const prev = idx > 0 ? hub.weeks[idx - 1] : null;
  const next = idx < hub.weeks.length - 1 ? hub.weeks[idx + 1] : null;
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path, name: titleFor(hub), description: summary(hub), dateModified: modified, type: "CollectionPage" }),
        itemListJsonLd({ name: `${hub.label} ${hub.year} college football games`, path, items: hub.games.map((g) => ({ name: `${g.game.awayTeam} ${g.game.neutralSite ? "vs" : "at"} ${g.game.homeTeam}`, path: `/matchup/${hub.year}/${g.game.gameId}` })) }),
        breadcrumbJsonLd(crumbs),
      ]} />
      <a className="skip-link" href="#weekContent">Skip to games</a>
      <SiteNav />
      <main id="weekContent" className="container site-index">
        <Breadcrumbs items={crumbs} />
        <header>
          <span className="eyebrow">{hub.year} season</span>
          <h1>{titleFor(hub)}</h1>
          <p>{summary(hub)}</p>
        </header>
        <section aria-labelledby="week-games-heading">
          <h2 id="week-games-heading">{hub.label} Games by PRIME Rating</h2>
          <div className="seo-table-wrap">
            <table className="seo-table">
              <thead>
                <tr><th scope="col">Matchup</th><th scope="col">Date</th><th scope="col">{hub.played ? "Result" : "Kickoff"}</th><th scope="col">PRIME rating ranks</th></tr>
              </thead>
              <tbody>
                {hub.games.map(({ game, awayRank, homeRank }) => (
                  <tr key={game.gameId}>
                    <td><Link href={`/matchup/${hub.year}/${game.gameId}`}>{game.awayTeam} {game.neutralSite ? "vs" : "at"} {game.homeTeam} {game.completed ? "game analytics" : "prediction"}</Link></td>
                    <td>{formatGameDate(game, "short") ?? "TBA"}</td>
                    <td>{game.completed && game.awayPoints !== null && game.homePoints !== null ? `${game.awayTeam} ${game.awayPoints}, ${game.homeTeam} ${game.homePoints}` : formatKickoff(game) ?? "Time TBA"}</td>
                    <td>{noRank(awayRank)} vs {noRank(homeRank)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="seo-note">Ranks are current PRIME rating ranks among rated FBS teams. Games against FCS opponents are not rated and are omitted. Kickoff times are Eastern.</p>
        </section>
        <nav aria-label="Other weeks">
          <h2>Other Weeks</h2>
          <ul className="seo-hub-nav">
            {hub.weeks.map((w) => (
              <li key={w.week}>{w.week === hub.week ? <span aria-current="page">{w.label}</span> : <Link href={`/week/${w.week}`}>{w.label}</Link>}</li>
            ))}
          </ul>
          {prev || next ? <p className="seo-note">{prev ? <Link href={`/week/${prev.week}`}>&larr; {prev.label}</Link> : null}{prev && next ? " · " : ""}{next ? <Link href={`/week/${next.week}`}>{next.label} &rarr;</Link> : null}</p> : null}
        </nav>
        <p>See <Link href="/predictions">weekly predictions</Link>, <Link href="/ratings">PRIME ratings</Link> and <Link href="/rankings">The PRIME 25</Link>.</p>
      </main>
      <SiteFooter note="Week pages list current-season FBS-vs-FBS games with the latest PRIME rating ranks." />
    </>
  );
}
