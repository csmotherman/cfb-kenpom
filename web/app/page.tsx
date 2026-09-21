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
      .slice(0, 10);
  }, [season, latestWeek]);

  return (
    <>
      <a className="skip-link" href="#homeChoices">Skip to Ratings and Rankings</a>
      <SiteHeader tagline="College Football, Measured Two Ways" />
      <SiteNav />

      <main className="prime-home" id="homeChoices">
        <section className="prime-home__hero container">
          <div className="prime-home__hero-copy">
            <span className="eyebrow">Two ways to see college football</span>
            <h1>Who&apos;s good. Who&apos;s earned it.</h1>
            <p>Ratings measure the performance. Rankings judge the résumé.</p>
          </div>
          <div className="prime-home__principles" aria-label="PRIME ranking principles">
            <span>No preseason poll boost</span>
            <span>No brand-name bonus</span>
            <span>Earn it this season</span>
          </div>
        </section>

        <section className="prime-choice-grid container" aria-label="Choose Ratings or Rankings">
          <article className="prime-choice prime-choice--ratings">
            <div className="prime-choice__copy">
              <div className="prime-choice__titleline">
                <span className="prime-choice__kicker">Ratings</span>
                <span className="prime-choice__status">LIVE</span>
              </div>
              <h2>Who&apos;s actually playing the best?</h2>
              <p className="prime-choice__desktop-copy">
                A deeper look at how well teams have performed on the field — efficiency, dominance and the
                competition they&apos;ve faced. Think team quality beyond just the record.
              </p>
              <p className="prime-choice__mobile-copy">
                How well teams have actually performed on the field, beyond just wins and losses.
              </p>
              <div className="prime-choice__actionline">
                <span className="prime-choice__cadence">Updated as games are completed.</span>
                <Link className="prime-choice__button" href="/ratings">View Ratings <span>→</span></Link>
              </div>
            </div>

            <div className="prime-choice__preview" aria-label="Current Top 10 Ratings">
              <div className="prime-choice__preview-head">
                <span>Current Top 10</span>
                <span>{latestWeek !== undefined ? `Through Week ${latestWeek}` : "Live"}</span>
              </div>
              <div className="prime-mini-table prime-mini-table--ratings">
                <div className="prime-mini-table__head">
                  <span>RK</span><span>TEAM</span><span>W-L</span><span>RATING</span>
                </div>
                {topRatings.map((team) => (
                  <Link className="prime-mini-table__row" href={`/team/${team.slug}`} key={team.slug}>
                    <span className="prime-mini-table__rank">{team.rank}</span>
                    <strong className="prime-mini-table__team">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
                      <span>{team.team}</span>
                    </strong>
                    <span>{team.record}</span>
                    <span className="prime-mini-table__value">{team.adjEM === null ? "—" : team.adjEM.toFixed(1)}</span>
                  </Link>
                ))}
              </div>
              <Link className="prime-choice__view-all" href="/ratings">View all Ratings →</Link>
            </div>
          </article>

          <article className="prime-choice prime-choice--rankings">
            <div className="prime-choice__copy">
              <div className="prime-choice__titleline">
                <span className="prime-choice__kicker">Rankings</span>
                <span className="prime-choice__status prime-choice__status--gold">SUNDAY · 12 ET</span>
              </div>
              <h2>Who deserves to be in the Top 25?</h2>
              <p className="prime-choice__desktop-copy">
                A poll-style view that weighs how well a team has played with the strength of the record it has
                earned. No voters rewarding a logo, reputation or preseason ranking.
              </p>
              <p className="prime-choice__mobile-copy">
                A Top 25-style view based on performance and the strength of each team&apos;s record.
              </p>
              <div className="prime-choice__actionline">
                <span className="prime-choice__cadence">New PRIME Top 25 every Sunday at 12 PM ET.</span>
                <Link className="prime-choice__button" href="/rankings">View Rankings <span>→</span></Link>
              </div>
            </div>

            <div className="prime-choice__preview" aria-label="Current PRIME Top 10 Rankings">
              <div className="prime-choice__preview-head">
                <span>PRIME Top 10</span>
                <span>{snapshot ? `Week ${snapshot.throughWeek}` : "Sunday release"}</span>
              </div>
              <div className="prime-mini-table prime-mini-table--rankings">
                <div className="prime-mini-table__head">
                  <span>RK</span><span>TEAM</span><span>W-L</span>
                </div>
                {(snapshot?.teams ?? []).slice(0, 10).map((team) => (
                  <Link className="prime-mini-table__row" href={`/team/${team.slug}`} key={team.slug}>
                    <span className="prime-mini-table__rank">{team.rank}</span>
                    <strong className="prime-mini-table__team">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
                      <span>{team.team}</span>
                    </strong>
                    <span>{team.record}</span>
                  </Link>
                ))}
              </div>
              <Link className="prime-choice__view-all" href="/rankings">View all Rankings →</Link>
            </div>
          </article>
        </section>

        <section className="prime-home__difference container">
          <div><strong>Ratings</strong><span>How good have they played?</span></div>
          <div className="prime-home__difference-mark" aria-hidden="true">≠</div>
          <div><strong>Rankings</strong><span>What have they earned?</span></div>
        </section>
      </main>

      <SiteFooter note="PRIME Ratings measure on-field performance. PRIME Rankings combine performance with the strength of the record a team has earned. A team's own place is not boosted by preseason polls, brand name or reputation." />
    </>
  );
}
