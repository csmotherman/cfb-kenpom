"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
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

function RankColumn({ teams }: { teams: PrimeRankingTeam[] }) {
  return (
    <div className="prime25-column">
      <div className="prime25-column__head" aria-hidden="true">
        <span>Rank</span>
        <span>Team</span>
        <span>W-L</span>
      </div>

      {teams.map((team) => (
        <Link
          href={`/team/${team.slug}`}
          className={`prime25-row${team.rank === 1 ? " prime25-row--number-one" : ""}`}
          key={team.slug}
        >
          <span className="prime25-row__rank">{team.rank}</span>
          <span className="prime25-row__team">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
            <span className="prime25-row__team-copy">
              <strong>{team.team}</strong>
              <small>{team.conf}</small>
            </span>
          </span>
          <span className="prime25-row__record">{team.record}</span>
        </Link>
      ))}
    </div>
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

  const columns = useMemo(() => {
    const teams = snapshot?.teams ?? [];
    return [teams.slice(0, 13), teams.slice(13, 25)];
  }, [snapshot]);

  return (
    <>
      <a className="skip-link" href="#prime25">Skip to rankings</a>
      <SiteHeader tagline="The PRIME 25" />
      <SiteNav />

      <main id="prime25" className="prime25-page">
        <div className="prime25-page__veil">
          <section className="prime25-shell container">
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
                  <span>{snapshot ? `Week ${snapshot.throughWeek}` : "Current"}</span>
                  <strong>{snapshot?.season ?? 2026}</strong>
                </div>
                <div className="prime25-meta-card prime25-meta-card--wide">
                  <span>New Rankings</span>
                  <strong>Sunday · 12 PM ET</strong>
                </div>
              </div>
            </header>

            <section className="prime25-board" aria-label="The PRIME 25 college football rankings">
              <div className="prime25-board__strap">
                <span>Performance + Résumé</span>
                <strong>The PRIME 25</strong>
                <span>No preseason bias</span>
              </div>

              <div className="prime25-board__grid">
                <RankColumn teams={columns[0]} />
                <RankColumn teams={columns[1]} />
              </div>
            </section>

            <div className="prime25-underbar">
              <span>Ratings measure how well teams have played. The PRIME 25 measures what they&apos;ve earned.</span>
              <Link href="/">View Performance Analytics →</Link>
            </div>
          </section>
        </div>
      </main>

      <SiteFooter note="The PRIME 25 is released every Sunday at 12 PM ET. Rankings combine current-season performance with strength of record; teams receive no boost from preseason polls, brand name, or reputation." />
    </>
  );
}
