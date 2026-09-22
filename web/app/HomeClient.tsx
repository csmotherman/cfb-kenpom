"use client";

import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import type { HomeInitial } from "@/lib/initialData";
import { logoUrl } from "@/lib/teamCode";
import type { ScheduleGame } from "@/lib/types";

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

export default function HomeClient({ seo, initial }: { seo?: ReactNode; initial?: HomeInitial | null }) {
  // Everything below was computed on the server (lib/initialData.ts), so the cards are in the first HTML and the
  // browser fetches nothing for this page.
  const year = initial?.year ?? "";
  const snapshot = initial?.snapshot ?? null;
  const latestWeek = initial?.latestWeek ?? undefined;
  const topRatings = initial?.topRatings ?? [];
  const topRankings = (snapshot?.teams ?? []).slice(0, 5);
  const featuredMatchups = initial?.featuredMatchups ?? [];
  const [watchlistIndex, setWatchlistIndex] = useState(0);
  const [watchlistDirection, setWatchlistDirection] = useState<"next" | "prev">("next");
  const [touchStartX, setTouchStartX] = useState<number | null>(null);
  const activeMatchup = featuredMatchups[watchlistIndex] ?? featuredMatchups[0] ?? null;
  const featuredGame = activeMatchup?.game ?? null;
  const featuredHome = activeMatchup?.home ?? null;
  const featuredAway = activeMatchup?.away ?? null;

  const moveWatchlist = (direction: -1 | 1) => {
    if (featuredMatchups.length <= 1) return;
    setWatchlistDirection(direction > 0 ? "next" : "prev");
    setWatchlistIndex((current) => (current + direction + featuredMatchups.length) % featuredMatchups.length);
  };

  const matchupEdge = useMemo(() => {
    if (!featuredHome || !featuredAway || featuredHome.adjEM === null || featuredAway.adjEM === null) return null;
    const diff = featuredHome.adjEM - featuredAway.adjEM;
    return {
      team: diff >= 0 ? featuredHome.team : featuredAway.team,
      value: Math.abs(diff),
    };
  }, [featuredHome, featuredAway]);

  const bestOffense = initial?.bestOffense ?? null;
  const bestDefense = initial?.bestDefense ?? null;
  const toughestSchedule = initial?.toughestSchedule ?? null;
  const biggestRiser = initial?.biggestRiser ?? null;

  const displayWeek = snapshot?.throughWeek ?? latestWeek ?? initial?.currentWeek ?? null;

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

          <article
            className="prime-home-matchup"
            onTouchStart={(event) => setTouchStartX(event.touches[0]?.clientX ?? null)}
            onTouchEnd={(event) => {
              if (touchStartX === null || featuredMatchups.length <= 1) return;
              const endX = event.changedTouches[0]?.clientX ?? touchStartX;
              const delta = endX - touchStartX;
              if (Math.abs(delta) >= 40) moveWatchlist(delta < 0 ? 1 : -1);
              setTouchStartX(null);
            }}
          >
            <header>
              <div className="prime-home-matchup__header-copy">
                <span>Weekend Watchlist</span>
                <b>{featuredGame ? `Week ${featuredGame.week}` : "Next Up"}</b>
              </div>
              {featuredMatchups.length > 1 ? (
                <div className="prime-home-matchup__nav" aria-label="Weekend Watchlist navigation">
                  <button type="button" onClick={() => moveWatchlist(-1)} aria-label="Previous matchup">‹</button>
                  <span aria-live="polite">{watchlistIndex + 1} / {featuredMatchups.length}</span>
                  <button type="button" onClick={() => moveWatchlist(1)} aria-label="Next matchup">›</button>
                </div>
              ) : null}
            </header>

            {featuredGame ? (
              <div
                key={featuredGame.gameId}
                className={`prime-home-matchup__slide prime-home-matchup__slide--${watchlistDirection}`}
              >
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
              </div>
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
