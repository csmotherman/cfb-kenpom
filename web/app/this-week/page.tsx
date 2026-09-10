"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { getMeta, getRankingsSeason, getScheduleSeason } from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type { RankingsRow, RankingsSeason, ScheduleGame, ScheduleSeason } from "@/lib/types";

function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function rankText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `#${value}`;
}

function weekLabel(schedule: ScheduleSeason, week: number): string {
  return schedule.weekLabels?.[String(week)] || `Week ${week}`;
}

function pregameRatingWeek(rankings: RankingsSeason, gameWeek: number): number | null {
  const prior = rankings.weeks.filter((week) => week < gameWeek);
  return prior.length ? prior[prior.length - 1] : null;
}

function gameDateLabel(game: ScheduleGame): string {
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
  });
}

export default function ThisWeekPage() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [season, setSeason] = useState<number | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
  const [selectedWeek, setSelectedWeek] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const meta = await getMeta();
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const [scheduleData, rankingData] = await Promise.all([
        getScheduleSeason(latestSeason),
        getRankingsSeason(latestSeason),
      ]);
      if (cancelled) return;
      setSeason(latestSeason);
      setSchedule(scheduleData);
      setRankings(rankingData);
      setSelectedWeek(scheduleData?.currentWeek ?? null);
    })().catch((error: Error) => {
      if (!cancelled) setLoadError(error);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    document.title = season ? `${season} Weekly Matchups | LEILA Ratings` : "Weekly Matchups | LEILA Ratings";
  }, [season]);

  const ratingWeek = useMemo(() => {
    if (!rankings || selectedWeek === null) return null;
    return pregameRatingWeek(rankings, selectedWeek);
  }, [rankings, selectedWeek]);

  const ratingsBySlug = useMemo(() => {
    const map = new Map<string, RankingsRow>();
    if (!rankings || ratingWeek === null) return map;
    for (const row of rankings.byWeek[String(ratingWeek)] || []) map.set(row.slug, row);
    return map;
  }, [rankings, ratingWeek]);

  const games = useMemo(() => {
    if (!schedule || selectedWeek === null) return [];
    return schedule.byWeek[String(selectedWeek)] || [];
  }, [schedule, selectedWeek]);

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#thisWeekContent">Skip to this week</a>
      <SiteHeader tagline="Weekly College Football Matchups" />
      <SiteNav />

      <section className="weekly-hero container">
        <div>
          <span className="eyebrow">LEILA Ratings Weekly Matchups</span>
          <h1>{season ? `${season} Matchups` : "Weekly Matchups"}</h1>
          <p>
            Every FBS-vs-FBS game in one place, paired with the latest pregame LEILA Ratings ratings so you can see where each matchup starts.
          </p>
        </div>
        <div className="weekly-hero__note">
          {ratingWeek === null ? "Pregame ratings unavailable before the opening week." : `Pregame ratings through Week ${ratingWeek}.`}
        </div>
      </section>

      <main id="thisWeekContent" className="container weekly-main">
        {schedule === undefined ? (
          <div className="weekly-state">Loading this week&rsquo;s slate…</div>
        ) : schedule === null ? (
          <div className="weekly-state">
            <h2>Weekly schedule data is publishing with the next ratings refresh</h2>
            <p>The page is ready; the public FBS schedule snapshot has not been generated on this deployment yet.</p>
          </div>
        ) : (
          <>
            <div className="weekly-controls">
              <span className="control-label">Week</span>
              <nav className="weekly-week-nav" aria-label="Schedule week">
                {schedule.weeks.map((week) => (
                  <button
                    key={week}
                    type="button"
                    className={week === selectedWeek ? "active" : undefined}
                    aria-pressed={week === selectedWeek}
                    onClick={() => setSelectedWeek(week)}
                  >
                    {schedule.weekLabels?.[String(week)] || `Wk ${week}`}
                  </button>
                ))}
              </nav>
              <span className="weekly-game-count">{games.length} games</span>
            </div>

            <div className="weekly-section-heading">
              <div>
                <span className="eyebrow">{selectedWeek === null ? "Schedule" : weekLabel(schedule, selectedWeek)}</span>
                <h2>FBS Matchups</h2>
              </div>
              <span>Offense and defense ranks use the latest available pregame snapshot.</span>
            </div>

            <div className="weekly-slate">
              {games.map((game) => (
                <WeeklyGame
                  key={game.gameId}
                  game={game}
                  season={season!}
                  awayRating={ratingsBySlug.get(game.awaySlug)}
                  homeRating={ratingsBySlug.get(game.homeSlug)}
                />
              ))}
              {games.length === 0 ? <div className="weekly-state">No FBS-vs-FBS games are listed for this week.</div> : null}
            </div>
          </>
        )}
      </main>

      <SiteFooter note="This Week uses the same FBS-vs-FBS universe as LEILA Ratings ratings. Pregame comparisons use the latest rating snapshot strictly before the selected game week; completed scores come from the trusted schedule refresh." />
    </>
  );
}

function WeeklyGame({
  game,
  season,
  awayRating,
  homeRating,
}: {
  game: ScheduleGame;
  season: number;
  awayRating?: RankingsRow;
  homeRating?: RankingsRow;
}) {
  const separator = game.neutralSite ? "vs" : "@";
  return (
    <article className="weekly-game">
      <div className="weekly-game__meta">
        <span>{gameDateLabel(game)}</span>
        {game.completed && game.awayPoints !== null && game.homePoints !== null ? (
          <strong className="mono">{game.awayPoints}–{game.homePoints}</strong>
        ) : game.conferenceGame ? (
          <span>Conference</span>
        ) : (
          <span>Non-conference</span>
        )}
      </div>

      <div className="weekly-game__teams">
        <WeeklyTeam team={game.awayTeam} teamId={game.awayTeamId} slug={game.awaySlug} rating={awayRating} />
        <span className="weekly-game__separator">{separator}</span>
        <WeeklyTeam team={game.homeTeam} teamId={game.homeTeamId} slug={game.homeSlug} rating={homeRating} />
      </div>

      <div className="weekly-game__edges" aria-label="Pregame rating matchups">
        <div className="weekly-edge-row">
          <span>{game.awayTeam} O</span>
          <b className="mono">{rankText(awayRating?.adjORank)}</b>
          <em>vs</em>
          <span>{game.homeTeam} D</span>
          <b className="mono">{rankText(homeRating?.adjDRank)}</b>
        </div>
        <div className="weekly-edge-row">
          <span>{game.homeTeam} O</span>
          <b className="mono">{rankText(homeRating?.adjORank)}</b>
          <em>vs</em>
          <span>{game.awayTeam} D</span>
          <b className="mono">{rankText(awayRating?.adjDRank)}</b>
        </div>
      </div>

      <Link className="weekly-game__link" href={`/matchup/${season}/${encodeURIComponent(game.gameId)}`}>
        View matchup <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

function WeeklyTeam({
  team,
  teamId,
  slug,
  rating,
}: {
  team: string;
  teamId: number;
  slug: string;
  rating?: RankingsRow;
}) {
  return (
    <div className="weekly-team">
      <Link href={`/team/${encodeURIComponent(slug)}`} className="weekly-team__identity" prefetch={false}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logoUrl(teamId)} alt="" loading="lazy" decoding="async" />
        <span>
          <strong>{rating?.rank ? `#${rating.rank} ${team}` : team}</strong>
          <small>{rating?.record || "—"}</small>
        </span>
      </Link>
      <span className="weekly-team__adjnet mono">AdjNet {signed(rating?.adjEM)}</span>
    </div>
  );
}
