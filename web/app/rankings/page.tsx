"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { logoUrl } from "@/lib/teamCode";

type PrimeRankingTeam = {
  rank: number;
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  record: string;
  ratingRank: number;
  sorRank: number;
};

type PrimeRankingSnapshot = {
  season: number;
  throughWeek: number;
  releasedAt: string;
  teams: PrimeRankingTeam[];
};

function RankingTile({ team, featured = false }: { team: PrimeRankingTeam; featured?: boolean }) {
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
      </span>

      <span className="prime25-tile__record">{team.record}</span>
    </Link>
  );
}

export default function RankingsPage() {
  const [snapshot, setSnapshot] = useState<PrimeRankingSnapshot | null>(null);

  useEffect(() => {
    fetch("/data/prime-rankings/2026.json", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("PRIME rankings unavailable");
        return response.json();
      })
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, []);

  const teams = snapshot?.teams ?? [];
  const topFive = teams.slice(0, 5);
  const rest = teams.slice(5);

  return (
    <>
      <a className="skip-link" href="#prime25">Skip to rankings</a>
      <SiteHeader tagline="The PRIME 25" />
      <SiteNav />

      <main id="prime25" className="prime25-page">
        <div className="prime25-page__veil">
          <section className="prime25-stage">
            <header className="prime25-hero">
              <div className="prime25-hero__copy">
                <span className="prime25-hero__eyebrow">PRIME Rankings</span>
                <h1>
                  <span>The</span>
                  <span className="prime25-hero__gold">PRIME</span>
                  <span>25</span>
                </h1>
                <p>Who has earned a spot among the nation&apos;s best?</p>
              </div>

              <div className="prime25-hero__meta">
                <div className="prime25-meta-card">
                  <span>Week</span>
                  <strong>{snapshot?.throughWeek ?? "—"}</strong>
                  <small>{snapshot?.season ?? 2026} season</small>
                </div>
                <div className="prime25-meta-card prime25-meta-card--wide">
                  <span>New Rankings</span>
                  <strong>Sunday · 12 PM ET</strong>
                  <small>Performance + résumé</small>
                </div>
              </div>
            </header>

            <div className="prime25-divider" />

            <section className="prime25-top-five" aria-label="PRIME Top 5">
              <div className="prime25-section-label">
                <strong>Top 5</strong>
                <span>Nation&apos;s highest-ranked teams</span>
              </div>
              <div className="prime25-top-five__grid">
                {topFive.map((team) => (
                  <RankingTile team={team} featured key={team.slug} />
                ))}
              </div>
            </section>

            <section className="prime25-rest" aria-label="PRIME rankings 6 through 25">
              <div className="prime25-section-label prime25-section-label--subtle">
                <strong>6–25</strong>
                <span>The rest of the PRIME 25</span>
              </div>
              <div className="prime25-grid">
                {rest.map((team) => (
                  <RankingTile team={team} key={team.slug} />
                ))}
              </div>
            </section>

            <footer className="prime25-stage__footer">
              <span>Ratings measure how well teams have played. The PRIME 25 measures what they&apos;ve earned.</span>
              <Link href="/ratings">View Performance Analytics →</Link>
            </footer>
          </section>
        </div>
      </main>

      <SiteFooter note="The PRIME 25 is released every Sunday at 12 PM ET. Rankings combine current-season performance with strength of record; teams receive no boost from preseason polls, brand name, or reputation." />
    </>
  );
}
