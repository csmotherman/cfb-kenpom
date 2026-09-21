"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { getMeta, getScheduleSeason, useRankingsSeason } from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type { RankingsRow, ScheduleGame, ScheduleSeason } from "@/lib/types";

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

function kickoffLabel(game: ScheduleGame | null): string {
  if (!game) return "Schedule publishing";
  if (game.completed) return "Final";
  if (game.startTimeTBD || !game.startDate) return "Time TBA";
  const date = new Date(game.startDate);
  if (Number.isNaN(date.getTime())) return "Time TBA";
  return date.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
    timeZoneName: "short",
  });
}

function bestByRank(rows: RankingsRow[], key: "adjORank" | "adjDRank" | "sosRank"): RankingsRow | null {
  return rows
    .filter((row) => row[key] !== null)
    .sort((a, b) => (a[key] ?? 999) - (b[key] ?? 999))[0] ?? null;
}

export default function HomeClient({ seo }: { seo?: ReactNode }) {
  const [year, setYear] = useState<string>("");
  const [snapshot, setSnapshot] = useState<PrimeRankingSnapshot | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null>(null);
  const season = useRankingsSeason(year || null);

  useEffect(() => {
    let cancelled = false;

    getMeta()
      .then(async (meta) => {
        const latest = meta.rankingsYears[meta.rankingsYears.length - 1];
        if (cancelled) return;
        setYear(String(latest));

        const [primeResponse, scheduleData] = await Promise.all([
          fetch(`/data/prime-rankings/${latest}.json`, { cache: "no-store" }),
          getScheduleSeason(latest),
        ]);

        if (cancelled) return;
        setSchedule(scheduleData);

        if (primeResponse.ok) {
          setSnapshot((await primeResponse.json()) as PrimeRankingSnapshot);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSnapshot(null);
          setSchedule(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const latestWeek = season?.weeks?.[season.weeks.length - 1];

  const currentRows = useMemo(() => {
    if (!season || latestWeek === undefined) return [];
    return season.byWeek[String(latestWeek)] ?? [];
  }, [season, latestWeek]);

  const topRatings = useMemo(
    () =>
      [...currentRows]
        .filter((team) => team.rank !== null)
        .sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999))
        .slice(0, 5),
    [currentRows],
  );

  const topRankings = (snapshot?.teams ?? []).slice(0, 5);

  const rowsByTeamId = useMemo(() => {
    const map = new Map<number, RankingsRow>();
    currentRows.forEach((row) => map.set(row.teamId, row));
    return map;
  }, [currentRows]);

  const featuredGame = useMemo(() => {
    if (!schedule) return null;

    const targetWeek =
      schedule.weeks.find((week) =>
        (schedule.byWeek[String(week)] ?? []).some((game) => !game.completed),
      ) ?? schedule.currentWeek;

    const candidates = (schedule.byWeek[String(targetWeek)] ?? []).filter((game) => !game.completed);
    if (!candidates.length) return null;

    return [...candidates].sort((a, b) => {
      const aHome = rowsByTeamId.get(a.homeTeamId)?.rank ?? 200;
      const aAway = rowsByTeamId.get(a.awayTeamId)?.rank ?? 200;
      const bHome = rowsByTeamId.get(b.homeTeamId)?.rank ?? 200;
      const bAway = rowsByTeamId.get(b.awayTeamId)?.rank ?? 200;

      const aTop25 = Number(aHome <= 25) + Number(aAway <= 25);
      const bTop25 = Number(bHome <= 25) + Number(bAway <= 25);
      if (aTop25 !== bTop25) return bTop25 - aTop25;

      return aHome + aAway - (bHome + bAway);
    })[0] ?? null;
  }, [schedule, rowsByTeamId]);

  const featuredHome = featuredGame ? rowsByTeamId.get(featuredGame.homeTeamId) ?? null : null;
  const featuredAway = featuredGame ? rowsByTeamId.get(featuredGame.awayTeamId) ?? null : null;

  const matchupEdge = useMemo(() => {
    if (!featuredHome || !featuredAway || featuredHome.adjEM === null || featuredAway.adjEM === null) return null;
    const diff = featuredHome.adjEM - featuredAway.adjEM;
    return {
      team: diff >= 0 ? featuredHome.team : featuredAway.team,
      value: Math.abs(diff),
    };
  }, [featuredHome, featuredAway]);

  const bestOffense = useMemo(() => bestByRank(currentRows, "adjORank"), [currentRows]);
  const bestDefense = useMemo(() => bestByRank(currentRows, "adjDRank"), [currentRows]);
  const toughestSchedule = useMemo(() => bestByRank(currentRows, "sosRank"), [currentRows]);
  const biggestRiser = useMemo(
    () =>
      [...currentRows]
        .filter((row) => row.rankChange !== null && row.rankChange > 0)
        .sort((a, b) => (b.rankChange ?? 0) - (a.rankChange ?? 0))[0] ?? null,
    [currentRows],
  );

  const displayWeek = snapshot?.throughWeek ?? latestWeek ?? schedule?.currentWeek ?? null;

  return (
    <>
      <a className="skip-link" href="#homeMain">Skip to PRIME dashboard</a>
      <SiteHeader tagline="College Football Analytics" />
      <SiteNav />

      <main className="prime-home-v2" id="homeMain">
        <section className="prime-home-v2__hero">
          <div className="prime-home-v2__hero-inner container">
            <div className="prime-home-v2__hero-copy">
              <span className="prime-home-v2__eyebrow">PRIME CFB Analytics</span>
              <h1>
                College Football,
                <span>Measured by Performance.</span>
              </h1>
              <p>Opponent-adjusted ratings. Data-driven rankings. Smarter predictions. A deeper look at the game.</p>
            </div>

            <aside className="prime-home-v2__hero-meta" aria-label="Current PRIME season">
              <span>{snapshot?.season ?? (year || "Current")} Season</span>
              <strong>{displayWeek !== null ? `Week ${displayWeek}` : "Live"}</strong>
              <i />
              <small>More signal.<br />Less noise.</small>
            </aside>
          </div>
        </section>

        <section className="prime-home-v2__dashboard container" aria-label="PRIME college football dashboard">
          <article className="prime-home-panel prime-home-panel--ratings">
            <header className="prime-home-panel__head">
              <div>
                <span>Performance</span>
                <h2>PRIME Ratings</h2>
                <p>Opponent-adjusted performance across all phases.</p>
              </div>
              <Link href="/ratings">Full Ratings →</Link>
            </header>

            <div className="prime-home-v2-table prime-home-v2-table--ratings">
              <div className="prime-home-v2-table__head">
                <span>#</span><span>Team</span><span>Overall</span><span>Off</span><span>Def</span>
              </div>
              {topRatings.map((team) => (
                <Link href={`/team/${team.slug}`} className="prime-home-v2-table__row" key={team.slug}>
                  <strong className="prime-home-v2-table__rank">{team.rank}</strong>
                  <span className="prime-home-v2-table__team">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
                    <b>{team.team}</b>
                  </span>
                  <b>{team.adjEM === null ? "—" : team.adjEM.toFixed(1)}</b>
                  <span>{team.adjO === null ? "—" : team.adjO.toFixed(1)}</span>
                  <span>{team.adjD === null ? "—" : team.adjD.toFixed(1)}</span>
                </Link>
              ))}
            </div>
          </article>

          <article className="prime-home-matchup">
            <header>
              <span>PRIME Matchup of the Week</span>
              <b>{featuredGame ? `Week ${featuredGame.week}` : "Next Up"}</b>
            </header>

            {featuredGame ? (
              <>
                <div className="prime-home-matchup__teams">
                  <div className="prime-home-matchup__team">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={logoUrl(featuredGame.awayTeamId, 160)} alt="" />
                    <span>{featuredAway?.rank ? `#${featuredAway.rank}` : "PRIME"}</span>
                    <strong>{featuredGame.awayTeam}</strong>
                    <small>{featuredAway?.record ?? featuredGame.awayConference ?? ""}</small>
                  </div>

                  <div className="prime-home-matchup__vs">{featuredGame.neutralSite ? "VS" : "@"}</div>

                  <div className="prime-home-matchup__team">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={logoUrl(featuredGame.homeTeamId, 160)} alt="" />
                    <span>{featuredHome?.rank ? `#${featuredHome.rank}` : "PRIME"}</span>
                    <strong>{featuredGame.homeTeam}</strong>
                    <small>{featuredHome?.record ?? featuredGame.homeConference ?? ""}</small>
                  </div>
                </div>

                <div className="prime-home-matchup__kickoff">
                  {kickoffLabel(featuredGame)}
                  {featuredGame.venue ? <span> · {featuredGame.venue}</span> : null}
                </div>

                <div className="prime-home-matchup__metrics" aria-label="Featured matchup PRIME ratings">
                  <div>
                    <span>Overall</span>
                    <strong>{featuredAway?.adjEM === null || featuredAway?.adjEM === undefined ? "—" : featuredAway.adjEM.toFixed(1)}</strong>
                    <small>{featuredAway?.rank ? `#${featuredAway.rank}` : ""}</small>
                  </div>
                  <div>
                    <span>Off</span>
                    <strong>{featuredAway?.adjO === null || featuredAway?.adjO === undefined ? "—" : featuredAway.adjO.toFixed(1)}</strong>
                    <small>{featuredAway?.adjORank ? `#${featuredAway.adjORank}` : ""}</small>
                  </div>
                  <div>
                    <span>Def</span>
                    <strong>{featuredAway?.adjD === null || featuredAway?.adjD === undefined ? "—" : featuredAway.adjD.toFixed(1)}</strong>
                    <small>{featuredAway?.adjDRank ? `#${featuredAway.adjDRank}` : ""}</small>
                  </div>

                  <div className="prime-home-matchup__metric-edge">
                    <span>PRIME Edge</span>
                    <strong>{matchupEdge ? `${matchupEdge.team} +${matchupEdge.value.toFixed(1)}` : "Preview"}</strong>
                  </div>

                  <div>
                    <span>Off</span>
                    <strong>{featuredHome?.adjO === null || featuredHome?.adjO === undefined ? "—" : featuredHome.adjO.toFixed(1)}</strong>
                    <small>{featuredHome?.adjORank ? `#${featuredHome.adjORank}` : ""}</small>
                  </div>
                  <div>
                    <span>Def</span>
                    <strong>{featuredHome?.adjD === null || featuredHome?.adjD === undefined ? "—" : featuredHome.adjD.toFixed(1)}</strong>
                    <small>{featuredHome?.adjDRank ? `#${featuredHome.adjDRank}` : ""}</small>
                  </div>
                  <div>
                    <span>Overall</span>
                    <strong>{featuredHome?.adjEM === null || featuredHome?.adjEM === undefined ? "—" : featuredHome.adjEM.toFixed(1)}</strong>
                    <small>{featuredHome?.rank ? `#${featuredHome.rank}` : ""}</small>
                  </div>
                </div>

                <Link className="prime-home-matchup__cta" href={`/matchup/${year}/${encodeURIComponent(featuredGame.gameId)}`}>
                  View Full Preview →
                </Link>
              </>
            ) : (
              <div className="prime-home-matchup__empty">
                <strong>Next slate loading</strong>
                <span>Upcoming games will appear as soon as the schedule refreshes.</span>
                <Link href="/predictions">View Weekly Predictions →</Link>
              </div>
            )}
          </article>

          <article className="prime-home-panel prime-home-panel--rankings">
            <header className="prime-home-panel__head">
              <div>
                <span>Résumé</span>
                <h2>The PRIME 25</h2>
                <p>What teams have earned through current-season results.</p>
              </div>
              <Link href="/rankings">Full Rankings →</Link>
            </header>

            <div className="prime-home-v2-table prime-home-v2-table--prime25">
              <div className="prime-home-v2-table__head">
                <span>#</span><span>Team</span><span>Record</span><span>SOR</span>
              </div>
              {topRankings.map((team) => (
                <Link href={`/team/${team.slug}`} className="prime-home-v2-table__row" key={team.slug}>
                  <strong className="prime-home-v2-table__rank">{team.rank}</strong>
                  <span className="prime-home-v2-table__team">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={logoUrl(team.teamId, 64)} alt="" loading="lazy" decoding="async" />
                    <b>{team.team}</b>
                  </span>
                  <span>{team.record}</span>
                  <b>#{team.sorRank}</b>
                </Link>
              ))}
            </div>
          </article>
        </section>

        <section className="prime-home-v2__insights container" aria-label="PRIME insights">
          <article className="prime-home-insight prime-home-insight--offense">
            <span>Best Offense</span>
            <div>
              {bestOffense ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={logoUrl(bestOffense.teamId, 96)} alt="" />
              ) : null}
              <strong>{bestOffense?.team ?? "—"}</strong>
            </div>
            <p>{bestOffense?.adjO === null || !bestOffense ? "Loading" : `${bestOffense.adjO.toFixed(1)} Off APR`}</p>
          </article>

          <article className="prime-home-insight prime-home-insight--riser">
            <span>Biggest Riser</span>
            <div>
              {biggestRiser ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={logoUrl(biggestRiser.teamId, 96)} alt="" />
              ) : null}
              <strong>{biggestRiser?.team ?? "—"}</strong>
            </div>
            <p>{biggestRiser?.rankChange ? `▲ ${biggestRiser.rankChange} spots` : "No major move yet"}</p>
          </article>

          <article className="prime-home-insight prime-home-insight--schedule">
            <span>Toughest Schedule</span>
            <div>
              {toughestSchedule ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={logoUrl(toughestSchedule.teamId, 96)} alt="" />
              ) : null}
              <strong>{toughestSchedule?.team ?? "—"}</strong>
            </div>
            <p>{toughestSchedule?.sosRank ? `#${toughestSchedule.sosRank} SOS` : "Loading"}</p>
          </article>

          <article className="prime-home-insight prime-home-insight--defense">
            <span>Best Defense</span>
            <div>
              {bestDefense ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img src={logoUrl(bestDefense.teamId, 96)} alt="" />
              ) : null}
              <strong>{bestDefense?.team ?? "—"}</strong>
            </div>
            <p>{bestDefense?.adjD === null || !bestDefense ? "Loading" : `${bestDefense.adjD.toFixed(1)} Def APR`}</p>
          </article>
        </section>

        <section className="prime-home-v2__explore container" aria-label="Explore PRIME">
          <h2>Explore More</h2>
          <div className="prime-home-v2__explore-grid">
            <Link href="/predictions">
              <span className="prime-home-v2__explore-icon">↗</span>
              <div><strong>Weekly Predictions</strong><small>Game-by-game forecasts and matchup previews.</small></div>
              <b>→</b>
            </Link>
            <Link href="/advanced">
              <span className="prime-home-v2__explore-icon">⌁</span>
              <div><strong>Advanced Stats</strong><small>EPA, success rate, explosiveness and more.</small></div>
              <b>→</b>
            </Link>
            <Link href="/ratings">
              <span className="prime-home-v2__explore-icon">▤</span>
              <div><strong>Team Profiles</strong><small>Find every FBS team through the ratings table.</small></div>
              <b>→</b>
            </Link>
            <Link href="/methodology">
              <span className="prime-home-v2__explore-icon">◎</span>
              <div><strong>Methodology</strong><small>See exactly how PRIME measures performance.</small></div>
              <b>→</b>
            </Link>
          </div>
        </section>

        <section className="prime-home-v2__definition container">
          <span><b>Ratings</b> = how well you&apos;ve played.</span>
          <i />
          <span><b>PRIME 25</b> = what you&apos;ve earned.</span>
        </section>
      </main>

      {seo}

      <SiteFooter note="PRIME Football — opponent-adjusted college football ratings, rankings, predictions, and advanced analytics." />
    </>
  );
}
