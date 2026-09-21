import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import SiteFooter from "@/components/SiteFooter";
import SiteNav from "@/components/SiteNav";
import { breadcrumbJsonLd, itemListJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getLatestSnapshot, getLatestYear, getTeamDirectory } from "@/lib/seoData";
import { conferenceName, fullTeamName } from "@/lib/teamMascots";
import TeamFilter from "./TeamFilter";

const DESCRIPTION = "Every FBS college football team with PRIME ratings, offensive and defensive efficiency, schedule strength, advanced stats and game results.";

export const metadata = pageMetadata({
  title: "FBS College Football Teams: Ratings & Analytics",
  description: DESCRIPTION,
  path: "/teams",
  image: { params: { kind: "ratings" }, alt: "PRIME college football team ratings" },
});

export default async function TeamsPage() {
  const [directory, year] = await Promise.all([getTeamDirectory(), getLatestYear()]);
  const { rows, week } = year ? await getLatestSnapshot(year) : { rows: [], week: null };
  const bySlug = new Map(rows.map((row) => [row.slug, row]));
  const groups = new Map<string, typeof directory>();
  for (const team of directory) {
    const key = team.conf || "IND";
    groups.set(key, [...(groups.get(key) ?? []), team]);
  }
  const ordered = [...groups.entries()].sort(([a], [b]) => conferenceName(a).localeCompare(conferenceName(b)));
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/teams", name: "FBS College Football Teams", description: DESCRIPTION, type: "CollectionPage" }),
        itemListJsonLd({ name: "FBS college football teams", path: "/teams", items: directory.map((t) => ({ name: fullTeamName(t.team), path: `/team/${t.slug}` })) }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Teams", path: "/teams" }]),
      ]} />
      <a className="skip-link" href="#teamsContent">Skip to teams</a>
      <SiteNav />
      <main id="teamsContent" className="container site-index">
        <header>
          <span className="eyebrow">{year ? `${year} season${week !== null ? ` · through Week ${week}` : ""}` : "Teams"}</span>
          <h1>FBS College Football Teams</h1>
          <p>
            Every FBS team has a PRIME profile with opponent-adjusted offensive and defensive ratings, strength of schedule and strength of record, a season schedule with results,
            and links to each game&rsquo;s matchup analytics. Teams are grouped by conference with their current record and PRIME rating rank
            {year ? `; ratings count completed FBS-vs-FBS games in ${year}` : ""}. See the <Link href="/ratings">full ratings table</Link> or <Link href="/rankings">The PRIME 25</Link>.
          </p>
        </header>
        <TeamFilter />
        {ordered.map(([conf, teams]) => {
          const ranked = teams.map((team) => bySlug.get(team.slug)).filter((row) => row?.rank).sort((a, b) => a!.rank! - b!.rank!);
          const best = ranked[0];
          return (
            <section key={conf} id={`conf-${conf.toLowerCase()}`} aria-labelledby={`conf-h-${conf.toLowerCase()}`} data-team-group>
              <h2 id={`conf-h-${conf.toLowerCase()}`}>{conferenceName(conf)}</h2>
              <p className="seo-note">
                {teams.length} {teams.length === 1 ? "team" : "teams"}
                {best ? <>; highest rated by PRIME: <Link href={`/team/${best.slug}`}>{best.team}</Link> (No. {best.rank})</> : null}.
              </p>
              <div className="site-index__grid">
                {teams.slice().sort((a, b) => a.team.localeCompare(b.team)).map((team) => {
                  const row = bySlug.get(team.slug);
                  return (
                    <div key={team.slug} className="site-index__team" data-team-name={team.team.toLowerCase()}>
                      <Link href={`/team/${team.slug}`}>{fullTeamName(team.team)}</Link>
                      {row ? <span className="seo-note">{row.record}{row.rank ? ` · No. ${row.rank}` : ""}</span> : null}
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </main>
      <SiteFooter note="Team pages use the same current-season methodology as the Ratings page." />
    </>
  );
}
