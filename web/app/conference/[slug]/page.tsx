import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import JsonLd from "@/components/JsonLd";
import Breadcrumbs from "@/components/seo/Breadcrumbs";
import SiteFooter from "@/components/SiteFooter";
import SiteNav from "@/components/SiteNav";
import { breadcrumbJsonLd, itemListJsonLd, noIndexMetadata, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { formatGameDate, formatKickoff, noRank, ordinal, signedRating } from "@/lib/seoContent";
import { getConferenceHub, getDataTimestamp, type ConferenceHub } from "@/lib/seoData";
import { CONFERENCE_CODES, conferenceFromSlug, conferenceName, conferenceSlug, fullTeamName } from "@/lib/teamMascots";

type Params = { params: Promise<{ slug: string }> };

export const dynamicParams = false;
export function generateStaticParams() {
  return CONFERENCE_CODES.map((code) => ({ slug: conferenceSlug(code)! }));
}

const titleFor = (hub: ConferenceHub) => `${conferenceName(hub.code)} Football Ratings & Team Analytics`;

function summary(hub: ConferenceHub): string {
  const name = conferenceName(hub.code);
  const leader = hub.teams[0];
  const parts = [`PRIME rates ${hub.teams.length} ${name} teams through the latest week of the ${hub.year} season${leader ? `, led by ${leader.team} (${noRank(leader.rank)} nationally)` : ""}.`];
  if (hub.confRank && hub.avgRating !== null) parts.push(`By average PRIME rating (${signedRating(hub.avgRating)}), the ${name} is ${ordinal(hub.confRank)} of ${hub.confCount} conferences.`);
  if (hub.nonConf) parts.push(`Against rated FBS teams from other conferences, ${name} teams are ${hub.nonConf.wins}-${hub.nonConf.losses}.`);
  if (hub.bestOffense && hub.bestDefense) {
    parts.push(hub.bestOffense.slug === hub.bestDefense.slug
      ? `${hub.bestOffense.team} has both the best offense and the best defense in the conference.`
      : `${hub.bestOffense.team} has the conference's best offense and ${hub.bestDefense.team} its best defense.`);
  }
  return parts.join(" ");
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const code = conferenceFromSlug((await params).slug);
  const hub = code ? await getConferenceHub(code) : null;
  if (!hub) return noIndexMetadata("Conference ratings", "College football conference ratings from PRIME.");
  return pageMetadata({
    title: titleFor(hub),
    description: `${conferenceName(hub.code)} team ratings for ${hub.year}: PRIME rating, offense, defense, strength of record and strength of schedule for all ${hub.teams.length} teams, plus non-conference results.`,
    path: `/conference/${conferenceSlug(hub.code)}`,
    image: { params: { kind: "ratings" }, alt: `${conferenceName(hub.code)} football ratings from PRIME` },
  });
}

export default async function ConferencePage({ params }: Params) {
  const code = conferenceFromSlug((await params).slug);
  const hub = code ? await getConferenceHub(code) : null;
  if (!hub) notFound();
  const name = conferenceName(hub.code);
  const path = `/conference/${conferenceSlug(hub.code)}`;
  const crumbs = [{ name: "Home", path: "/" }, { name: "Teams", path: "/teams" }, { name, path }];
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path, name: titleFor(hub), description: summary(hub), dateModified: await getDataTimestamp(), type: "CollectionPage" }),
        itemListJsonLd({ name: `${name} football teams by PRIME rating`, path, items: hub.teams.map((t) => ({ name: fullTeamName(t.team), path: `/team/${t.slug}` })) }),
        breadcrumbJsonLd(crumbs),
      ]} />
      <a className="skip-link" href="#conferenceContent">Skip to ratings</a>
      <SiteNav />
      <main id="conferenceContent" className="container site-index">
        <Breadcrumbs items={crumbs} />
        <header>
          <span className="eyebrow">{hub.year} season{hub.week !== null ? ` · through Week ${hub.week}` : ""}</span>
          <h1>{titleFor(hub)}</h1>
          <p>{summary(hub)}</p>
        </header>
        <section aria-labelledby="conference-table-heading">
          <h2 id="conference-table-heading">{name} Teams by PRIME Rating</h2>
          <div className="seo-table-wrap">
            <table className="seo-table">
              <thead>
                <tr>
                  <th scope="col">Team</th><th scope="col">Record (vs FBS)</th><th scope="col">National rank</th><th scope="col">Overall</th>
                  <th scope="col">Offense</th><th scope="col">Defense</th><th scope="col">SOR</th><th scope="col">SOS</th>
                </tr>
              </thead>
              <tbody>
                {hub.teams.map((t) => (
                  <tr key={t.slug}>
                    <th scope="row"><Link href={`/team/${t.slug}`}>{fullTeamName(t.team)}</Link></th>
                    <td>{t.record}</td>
                    <td>{noRank(t.rank)}</td>
                    <td>{signedRating(t.adjEM)}</td>
                    <td>{signedRating(t.adjO, 2)} ({noRank(t.adjORank) ?? "—"})</td>
                    <td>{signedRating(t.adjD, 2)} ({noRank(t.adjDRank) ?? "—"})</td>
                    <td>{signedRating(t.sor, 2)} ({noRank(t.sorRank) ?? "—"})</td>
                    <td>{signedRating(t.sos)} ({noRank(t.sosRank) ?? "—"})</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="seo-note">Ranks are national among rated FBS teams. Records count completed FBS-vs-FBS games only; strength of schedule rank 1 is the toughest schedule.</p>
        </section>
        {hub.upcoming.length ? (
          <section aria-labelledby="conference-games-heading">
            <h2 id="conference-games-heading">{hub.weekLabel} {name} Games</h2>
            <ul className="seo-list">
              {hub.upcoming.map(({ game, awayRank, homeRank }) => (
                <li key={game.gameId}>
                  <Link href={`/matchup/${hub.year}/${game.gameId}`}>{game.awayTeam} {game.neutralSite ? "vs" : "at"} {game.homeTeam} prediction</Link>{" "}
                  <span className="seo-note">({noRank(awayRank)} vs {noRank(homeRank)} PRIME rank{formatGameDate(game, "short") ? `, ${formatGameDate(game, "short")}` : ""}{formatKickoff(game) ? `, ${formatKickoff(game)}` : ""})</span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        <p>Compare with <Link href="/ratings">every FBS team&rsquo;s ratings</Link>, <Link href="/rankings">The PRIME 25</Link> or <Link href="/teams">all teams by conference</Link>.</p>
      </main>
      <SiteFooter note="Conference pages use the same current-season methodology as the Ratings page." />
    </>
  );
}
