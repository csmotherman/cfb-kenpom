import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import SiteFooter from "@/components/SiteFooter";
import SiteNav from "@/components/SiteNav";
import { breadcrumbJsonLd, itemListJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getLatestSnapshot, getLatestYear, getTeamDirectory } from "@/lib/seoData";
import { conferenceName, conferenceSlug, fullTeamName } from "@/lib/teamMascots";
import { logoUrl } from "@/lib/teamCode";
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
  const seasonLabel = year ? `${year} season${week !== null ? ` · through Week ${week}` : ""}` : "Current FBS directory";

  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/teams", name: "FBS College Football Teams", description: DESCRIPTION, type: "CollectionPage" }),
        itemListJsonLd({ name: "FBS college football teams", path: "/teams", items: directory.map((t) => ({ name: fullTeamName(t.team), path: `/team/${t.slug}` })) }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Teams", path: "/teams" }]),
      ]} />
      <a className="skip-link" href="#teamsContent">Skip to teams</a>
      <SiteNav />

      <main id="teamsContent" className="prime-teams">
        <section className="prime-teams__hero">
          <div className="container prime-teams__hero-inner">
            <div className="prime-teams__hero-copy">
              <span className="prime-teams__eyebrow">{seasonLabel}</span>
              <h1>FBS College Football <span>Teams</span></h1>
              <p>
                Find any FBS program and jump straight into its PRIME profile: opponent-adjusted ratings,
                schedule, results, advanced metrics, and matchup analytics.
              </p>
              <div className="prime-teams__hero-links">
                <Link href="/ratings">View full ratings <span aria-hidden="true">→</span></Link>
                <Link href="/rankings">See the PRIME 25 <span aria-hidden="true">→</span></Link>
              </div>
            </div>

            <div className="prime-teams__hero-stats" aria-label="Team directory summary">
              <div>
                <span>FBS Programs</span>
                <strong>{directory.length}</strong>
              </div>
              <i aria-hidden="true" />
              <div>
                <span>Conferences</span>
                <strong>{ordered.length}</strong>
              </div>
              <small>Every profile. One place.</small>
            </div>
          </div>
        </section>

        <div className="container prime-teams__content">
          <section className="prime-teams__finder" aria-labelledby="team-finder-heading">
            <div className="prime-teams__finder-copy">
              <span>Team Directory</span>
              <h2 id="team-finder-heading">Find your program</h2>
              <p>Search by school name or jump directly to a conference.</p>
            </div>
            <TeamFilter />
          </section>

          <nav className="prime-teams__conference-nav" aria-label="Jump to conference">
            {ordered.map(([conf]) => (
              <a key={conf} href={`#conf-${conf.toLowerCase()}`}>
                {conferenceName(conf)}
              </a>
            ))}
          </nav>

          <div className="prime-teams__conferences">
            {ordered.map(([conf, teams]) => {
              const ranked = teams
                .map((team) => bySlug.get(team.slug))
                .filter((row) => row?.rank)
                .sort((a, b) => a!.rank! - b!.rank!);
              const best = ranked[0];
              const slug = conferenceSlug(conf);

              return (
                <section
                  key={conf}
                  id={`conf-${conf.toLowerCase()}`}
                  className="prime-teams__conference"
                  aria-labelledby={`conf-h-${conf.toLowerCase()}`}
                  data-team-group
                >
                  <header className="prime-teams__conference-head">
                    <div>
                      <span className="prime-teams__conference-kicker">{teams.length} {teams.length === 1 ? "program" : "programs"}</span>
                      <h2 id={`conf-h-${conf.toLowerCase()}`}>
                        {slug ? <Link href={`/conference/${slug}`}>{conferenceName(conf)}</Link> : conferenceName(conf)}
                      </h2>
                    </div>
                    {best ? (
                      <div className="prime-teams__conference-leader">
                        <span>Highest PRIME rating</span>
                        <Link href={`/team/${best.slug}`}>
                          <b>{best.team}</b>
                          <em>No. {best.rank}</em>
                        </Link>
                      </div>
                    ) : null}
                  </header>

                  <div className="prime-teams__grid">
                    {teams.slice().sort((a, b) => a.team.localeCompare(b.team)).map((team) => {
                      const row = bySlug.get(team.slug);
                      return (
                        <Link
                          key={team.slug}
                          className="prime-team-card"
                          href={`/team/${team.slug}`}
                          data-team-name={team.team.toLowerCase()}
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={logoUrl(team.teamId, 96)} alt="" loading="lazy" decoding="async" />
                          <span className="prime-team-card__identity">
                            <strong>{fullTeamName(team.team)}</strong>
                            <small>{conferenceName(conf)}</small>
                          </span>
                          <span className="prime-team-card__meta">
                            <span>
                              <small>Record</small>
                              <b>{row?.record ?? "—"}</b>
                            </span>
                            <span>
                              <small>PRIME</small>
                              <b>{row?.rank ? `#${row.rank}` : "—"}</b>
                            </span>
                          </span>
                          <span className="prime-team-card__arrow" aria-hidden="true">→</span>
                        </Link>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      </main>

      <SiteFooter note="Team pages use the same current-season methodology as the Ratings page." />
    </>
  );
}
