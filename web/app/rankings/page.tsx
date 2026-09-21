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

function RankingColumn({ teams }: { teams: PrimeRankingTeam[] }) {
  return (
    <div className="prime-25__column">
      <div className="prime-25__column-head" aria-hidden="true">
        <span>RK</span>
        <span>TEAM</span>
        <span>W-L</span>
      </div>
      {teams.map((team) => (
        <Link
          href={`/team/${team.slug}`}
          className={`prime-25__row${team.rank <= 5 ? " prime-25__row--top5" : ""}`}
          key={team.slug}
        >
          <span className={`prime-25__rank${team.rank === 1 ? " prime-25__rank--one" : ""}`}>{team.rank}</span>
          <span className="prime-25__team">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
            <span className="prime-25__team-copy">
              <strong>{team.team}</strong>
              <small>{team.conf}</small>
            </span>
          </span>
          <span className="prime-25__record">{team.record}</span>
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
        if (!response.ok) throw new Error("Ranking snapshot unavailable");
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
      <a className="skip-link" href="#rankingsContent">Skip to rankings</a>
      <SiteHeader tagline="The PRIME 25" />
      <SiteNav />

      <main id="rankingsContent" className="prime-rankings container">
        <header className="prime-rankings__masthead">
          <div className="prime-rankings__brand">
            <span className="eyebrow">PRIME Rankings</span>
            <h1>The PRIME 25</h1>
            <p>Who has earned a spot among the nation&apos;s best?</p>
          </div>

          <div className="prime-rankings__meta">
            <div className="prime-rankings__issue">
              <span>{snapshot ? `Week ${snapshot.throughWeek}` : "Current"}</span>
              <strong>{snapshot?.season ?? 2026}</strong>
            </div>
            <div className="prime-rankings__drop">
              <span>New rankings</span>
              <strong>Sunday · 12 PM ET</strong>
            </div>
          </div>
        </header>

        <section className="prime-25" aria-label="The PRIME 25 college football rankings">
          <div className="prime-25__banner">
            <span>Performance + Résumé</span>
            <strong>THE PRIME 25</strong>
            <span>No preseason bias</span>
          </div>

          <div className="prime-25__grid">
            <RankingColumn teams={columns[0]} />
            <RankingColumn teams={columns[1]} />
          </div>
        </section>

        <div className="prime-rankings__underbar">
          <span>Ratings measure how well teams have played. The PRIME 25 measures what they&apos;ve earned.</span>
          <Link href="/ratings">View Performance Analytics →</Link>
        </div>
      </main>

      <SiteFooter note="The PRIME 25 is released every Sunday at 12 PM ET and combines current-season performance with strength of record. Teams receive no boost from preseason polls, brand name or reputation." />
    </>
  );
}
