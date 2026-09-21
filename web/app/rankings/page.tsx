"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

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

export default function RankingsPage() {
  const [snapshot, setSnapshot] = useState<PrimeRankingSnapshot | null>(null);

  useEffect(() => {
    fetch("/data/prime-rankings/2026.json", { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Ranking snapshot unavailable");
        return response.json();
      })
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, []);

  return (
    <>
      <a className="skip-link" href="#rankingsContent">Skip to rankings</a>
      <SiteHeader tagline="The PRIME Top 25" />
      <SiteNav />

      <main id="rankingsContent" className="prime-rankings container">
        <header className="prime-rankings__hero">
          <span className="eyebrow">PRIME Rankings</span>
          <h1>Who has earned it?</h1>
          <p>
            Ratings tell you how well a team has played. Rankings ask a different question:
            <strong> who deserves to be ranked highest right now?</strong>
          </p>
          <p className="prime-rankings__sub">
            Performance meets résumé. No preseason poll boost, brand-name bonus or reputation points.
          </p>
          <div className="prime-rankings__release">
            <span>New Top 25</span>
            <strong>Every Sunday · 12 PM ET</strong>
          </div>
        </header>

        <section className="prime-rankings__card" aria-label="PRIME Top 25">
          <div className="prime-rankings__card-head">
            <div>
              <span className="eyebrow">Current release</span>
              <h2>PRIME Top 25</h2>
            </div>
            <div className="prime-rankings__week">
              {snapshot ? <>Week {snapshot.throughWeek}<small>{snapshot.season}</small></> : "Loading"}
            </div>
          </div>

          <div className="prime-rankings__table">
            <div className="prime-rankings__row prime-rankings__row--head">
              <span>RK</span>
              <span>TEAM</span>
              <span>W-L</span>
              <span className="prime-rankings__context-col">RATING RK</span>
              <span className="prime-rankings__context-col">SOR RK</span>
            </div>
            {(snapshot?.teams ?? []).map((team) => (
              <Link href={`/team/${team.slug}`} className="prime-rankings__row" key={team.slug}>
                <span className="prime-rankings__rank">{team.rank}</span>
                <span className="prime-rankings__team"><strong>{team.team}</strong><small>{team.conf}</small></span>
                <span>{team.record}</span>
                <span className="prime-rankings__context-col">#{team.ratingRank}</span>
                <span className="prime-rankings__context-col">#{team.sorRank}</span>
              </Link>
            ))}
          </div>
        </section>

        <aside className="prime-rankings__explain">
          <strong>Why can Ratings and Rankings disagree?</strong>
          <span>
            A team can play like one of the best teams in the country without having one of the best résumés.
            Another can earn a great record without performing at the same level possession by possession.
          </span>
          <Link href="/ratings">Compare with PRIME Ratings →</Link>
        </aside>
      </main>

      <SiteFooter note="PRIME Rankings are a weekly Top 25 built from current-season performance and strength of record. Ratings remain the live measure of how well teams have performed." />
    </>
  );
}
