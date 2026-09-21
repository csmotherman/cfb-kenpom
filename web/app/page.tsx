"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { getMeta, useRankingsSeason } from "@/lib/data";
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

export default function HomePage() {
  const [year, setYear] = useState<string>("");
  const [snapshot, setSnapshot] = useState<PrimeRankingSnapshot | null>(null);
  const season = useRankingsSeason(year || null);

  useEffect(() => {
    getMeta()
      .then((meta) => {
        const latest = meta.rankingsYears[meta.rankingsYears.length - 1];
        setYear(String(latest));
        return fetch(`/data/prime-rankings/${latest}.json`, { cache: "no-store" });
      })
      .then((response) => {
        if (!response.ok) throw new Error("PRIME ranking snapshot unavailable");
        return response.json();
      })
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, []);

  const latestWeek = season?.weeks?.[season.weeks.length - 1];
  const topRatings = useMemo(() => {
    if (!season || latestWeek === undefined) return [];
    return [...(season.byWeek[String(latestWeek)] ?? [])]
      .filter((team) => team.rank !== null)
      .sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999))
      .slice(0, 5);
  }, [season, latestWeek]);

  const topRankings = (snapshot?.teams ?? []).slice(0, 5);

  return (
    <>
      <a className="skip-link" href="#homeChoices">Skip to Ratings and Rankings</a>
      <SiteHeader tagline="College Football Analytics" />
      <SiteNav />

      <main className="prime-home" id="homeChoices">
        <section className="prime-home__intro container">
          <span className="prime-home__eyebrow">PRIME College Football</span>
          <h1>Ratings and rankings answer different questions.</h1>
          <p>
            Ratings measure how well teams have played. The PRIME 25 measures what they&apos;ve earned.
          </p>
        </section>

        <section className="prime-home__cards container" aria-label="Choose Ratings or Rankings">
          <article className="prime-home-card prime-home-card--ratings">
            <header className="prime-home-card__header">
              <div>
                <span className="prime-home-card__label">Ratings</span>
                <h2>Performance Analytics</h2>
                <p>Opponent-adjusted performance and advanced team efficiency.</p>
              </div>
              <div className="prime-home-card__meta">
                <span>Live</span>
                <strong>{latestWeek !== undefined ? `Through Week ${latestWeek}` : "Current"}</strong>
              </div>
            </header>

            <div className="prime-home-card__preview">
              <div className="prime-home-card__preview-title">
                <strong>Top 5 Ratings</strong>
                <span>Overall APR</span>
              </div>

              <div className="prime-home-list">
                {topRatings.map((team) => (
                  <Link href={`/team/${team.slug}`} className="prime-home-list__row" key={team.slug}>
                    <span className="prime-home-list__rank">{team.rank}</span>
                    <span className="prime-home-list__team">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
                      <strong>{team.team}</strong>
                    </span>
                    <span className="prime-home-list__record">{team.record}</span>
                    <span className="prime-home-list__value">
                      {team.adjEM === null ? "—" : team.adjEM.toFixed(1)}
                    </span>
                  </Link>
                ))}
              </div>
            </div>

            <div className="prime-home-card__footer">
              <span>Updated as completed games are processed.</span>
              <Link href="/ratings">View Ratings <span>→</span></Link>
            </div>
          </article>

          <article className="prime-home-card prime-home-card--rankings">
            <header className="prime-home-card__header">
              <div>
                <span className="prime-home-card__label">Rankings</span>
                <h2>The PRIME 25</h2>
                <p>Current-season performance and strength of record.</p>
                <p className="prime-home-card__trust">
                  No preseason rankings, brand reputation, or voter input.
                </p>
              </div>
              <div className="prime-home-card__meta prime-home-card__meta--gold">
                <span>{snapshot ? `Week ${snapshot.throughWeek}` : "Current"}</span>
                <strong>Sunday · 12 PM ET</strong>
              </div>
            </header>

            <div className="prime-home-card__preview">
              <div className="prime-home-card__preview-title">
                <strong>PRIME Top 5</strong>
                <span>{snapshot ? `${snapshot.season} season` : "Current season"}</span>
              </div>

              <div className="prime-home-list prime-home-list--rankings">
                {topRankings.map((team) => (
                  <Link href={`/team/${team.slug}`} className="prime-home-list__row" key={team.slug}>
                    <span className={`prime-home-list__rank${team.rank === 1 ? " prime-home-list__rank--one" : ""}`}>{team.rank}</span>
                    <span className="prime-home-list__team">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
                      <span className="prime-home-list__team-copy">
                        <strong>{team.team}</strong>
                        <small>{team.conf}</small>
                      </span>
                    </span>
                    <span className="prime-home-list__record">{team.record}</span>
                  </Link>
                ))}
              </div>
            </div>

            <div className="prime-home-card__footer">
              <span>New PRIME 25 every Sunday at 12 PM ET.</span>
              <Link href="/rankings">View Rankings <span>→</span></Link>
            </div>
          </article>
        </section>

        <section className="prime-home__explain container" aria-label="Difference between Ratings and Rankings">
          <div>
            <strong>Ratings</strong>
            <span>How well has the team played?</span>
          </div>
          <div className="prime-home__explain-divider" aria-hidden="true" />
          <div>
            <strong>Rankings</strong>
            <span>What has the team earned?</span>
          </div>
        </section>
      </main>

      <SiteFooter note="PRIME Ratings measure on-field performance. The PRIME 25 combines current-season performance with strength of record." />
    </>
  );
}
