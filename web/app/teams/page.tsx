import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import SiteFooter from "@/components/SiteFooter";
import SiteNav from "@/components/SiteNav";
import { breadcrumbJsonLd, itemListJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getDataTimestamp, getLatestYear, getTeamDirectory } from "@/lib/seoData";
import { fullTeamName } from "@/lib/teamMascots";
import TeamFilter from "./TeamFilter";

const DESCRIPTION = "Every FBS college football team with PRIME ratings, offensive and defensive efficiency, schedule strength, advanced stats and game results.";

export const metadata = pageMetadata({
  title: "FBS College Football Teams: Ratings & Analytics",
  description: DESCRIPTION,
  path: "/teams",
  image: { params: { kind: "ratings" }, alt: "PRIME college football team ratings" },
});

export default async function TeamsPage() {
  const [directory, year, modified] = await Promise.all([getTeamDirectory(), getLatestYear(), getDataTimestamp()]);
  const groups = new Map<string, typeof directory>();
  for (const team of directory) {
    const key = team.conf || "Independent";
    groups.set(key, [...(groups.get(key) ?? []), team]);
  }
  const ordered = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/teams", name: "FBS College Football Teams", description: DESCRIPTION, dateModified: modified, type: "CollectionPage" }),
        itemListJsonLd({ name: "FBS college football teams", path: "/teams", items: directory.map((t) => ({ name: fullTeamName(t.team), path: `/team/${t.slug}` })) }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Teams", path: "/teams" }]),
      ]} />
      <a className="skip-link" href="#teamsContent">Skip to teams</a>
      <SiteNav />
      <main id="teamsContent" className="container site-index">
        <header>
          <span className="eyebrow">{year ? `${year} season` : "Teams"}</span>
          <h1>FBS College Football Teams</h1>
          <p>Every FBS team&rsquo;s profile: PRIME ratings, offensive and defensive efficiency, schedule strength, game log and advanced breakdown.</p>
        </header>
        <TeamFilter />
        {ordered.map(([conf, teams]) => (
          <section key={conf} aria-label={conf} data-team-group>
            <h2>{conf}</h2>
            <div className="site-index__grid">
              {teams.slice().sort((a, b) => a.team.localeCompare(b.team)).map((team) => (
                <Link key={team.slug} href={`/team/${team.slug}`} data-team-name={team.team.toLowerCase()}>{fullTeamName(team.team)}</Link>
              ))}
            </div>
          </section>
        ))}
      </main>
      <SiteFooter note="Team pages use the same current-season methodology as the Ratings page." />
    </>
  );
}
