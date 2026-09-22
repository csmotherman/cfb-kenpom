import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { breadcrumbJsonLd, datasetJsonLd, itemListJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getRatingsInitial } from "@/lib/initialData";
import type { RankingsRow } from "@/lib/types";
import { logoUrl, teamCode } from "@/lib/teamCode";

const DESCRIPTION =
  "The Top 25 Power Ratings rank college football teams strictly by PRIME's current-season opponent-adjusted performance rating.";

export const metadata = pageMetadata({
  title: "Top 25 Power Ratings",
  description: DESCRIPTION,
  path: "/top25ratings",
  image: { params: { kind: "ratings" }, alt: "PRIME Top 25 Power Ratings" },
});

type RatedTeam = RankingsRow & { rank: number };

function PowerRatingTile({ team, featured = false }: { team: RatedTeam; featured?: boolean }) {
  return (
    <Link
      href={`/team/${team.slug}`}
      className={`prime25-tile${featured ? " prime25-tile--featured" : ""}${team.rank === 1 ? " prime25-tile--number-one" : ""}`}
    >
      <span className="prime25-tile__rank">{team.rank}</span>

      <span className="prime25-tile__body">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logoUrl(team.teamId, 96)} alt="" loading="lazy" decoding="async" />
        <span className="prime25-tile__copy">
          <strong>{team.team}</strong>
          <small>{team.conf}</small>
        </span>
        <span className="prime25-tile__code" aria-hidden="true">{teamCode(team.team)}</span>
      </span>

      <span className="prime25-tile__record">{team.record}</span>
    </Link>
  );
}

export default async function Top25RatingsPage() {
  const initial = await getRatingsInitial();
  const latestWeek = initial?.season.weeks.at(-1) ?? null;
  const rows = latestWeek !== null ? initial?.season.byWeek[String(latestWeek)] ?? [] : [];
  const teams = rows
    .filter((team): team is RatedTeam => team.rank !== null)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, 25);

  const topFive = teams.slice(0, 5);
  const rest = teams.slice(5);

  const items = teams.map((team) => ({ name: team.team, path: `/team/${team.slug}` }));

  return (
    <>
      <JsonLd data={[
        webPageJsonLd({
          path: "/top25ratings",
          name: "Top 25 Power Ratings",
          description: DESCRIPTION,
          dateModified: initial?.generatedAt ?? undefined,
        }),
        ...(items.length
          ? [itemListJsonLd({
              name: `Top 25 Power Ratings, ${initial?.year ?? "current season"} through Week ${latestWeek ?? "current"}`,
              path: "/top25ratings",
              items,
            })]
          : []),
        datasetJsonLd({
          path: "/top25ratings",
          name: "PRIME Top 25 Power Ratings",
          description: "The 25 highest-rated college football teams by PRIME's opponent-adjusted current-season performance model.",
          dateModified: initial?.generatedAt ?? undefined,
          temporalCoverage: initial?.year,
          keywords: ["college football power ratings", "top 25 power ratings", "opponent-adjusted ratings", "PRIME ratings"],
        }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Top 25 Power Ratings", path: "/top25ratings" }]),
      ]} />

      <a className="skip-link" href="#top25ratings">Skip to power ratings</a>
      <SiteHeader tagline="Top 25 Power Ratings" />
      <SiteNav />

      <main id="top25ratings" className="prime25-page">
        <div className="prime25-page__veil">
          <section className="prime25-stage">
            <header className="prime25-hero">
              <div className="prime25-hero__copy">
                <div className="prime25-hero__title">
                  <span className="prime25-hero__eyebrow">Top 25 Power Ratings</span>
                  <h1>
                    <span className="prime25-hero__gold">POWER</span>
                    <span>25</span>
                    <span className="sr-only"> Top 25 Power Ratings</span>
                  </h1>
                </div>
                <div className="prime25-hero__intro">
                  <p>Who has played like one of the nation&apos;s best?</p>
                  <p className="prime25-hero__trust">
                    Ranked strictly by current-season, opponent-adjusted performance. No résumé bonus, voter input, brand reputation, or preseason ranking.
                  </p>
                </div>
              </div>

              <div className="prime25-hero__meta">
                <div className="prime25-meta-card">
                  <span>Week</span>
                  <strong>{latestWeek ?? "—"}</strong>
                  <small>{initial?.year ?? 2026} season</small>
                </div>
                <div className="prime25-meta-card prime25-meta-card--wide">
                  <span>Power Rating</span>
                  <strong>PRIME Net APR</strong>
                  <small>Opponent adjusted</small>
                </div>
              </div>
            </header>

            <div className="prime25-divider" />

            <section className="prime25-top-five" aria-label="Top five power-rated teams">
              <div className="prime25-section-label">
                <strong>Top 5</strong>
                <span>Nation&apos;s highest-rated teams</span>
              </div>
              <div className="prime25-top-five__grid">
                {topFive.map((team) => (
                  <PowerRatingTile team={team} featured key={team.slug} />
                ))}
              </div>
            </section>

            <section className="prime25-rest" aria-label="Power ratings 6 through 25">
              <div className="prime25-section-label prime25-section-label--subtle">
                <strong>6–25</strong>
                <span>The rest of the Top 25 Power Ratings</span>
              </div>
              <div className="prime25-grid">
                {rest.map((team) => (
                  <PowerRatingTile team={team} key={team.slug} />
                ))}
              </div>
            </section>

            <footer className="prime25-stage__footer">
              <span>Power Ratings measure how well teams have played. The PRIME 25 rankings measure what they&apos;ve earned.</span>
              <Link href="/ratings">View Full Ratings →</Link>
            </footer>
          </section>
        </div>
      </main>

      <SiteFooter note="Top 25 Power Ratings are ordered by PRIME Net APR, the current-season opponent-adjusted performance rating used on the full Ratings page." />
    </>
  );
}
