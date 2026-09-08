"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { getRankingsSeason, getScheduleSeason } from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type { RankingsRow, RankingsSeason, ScheduleGame, ScheduleSeason } from "@/lib/types";

function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function rankText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `#${value}`;
}

function pregameRatingWeek(rankings: RankingsSeason, gameWeek: number): number | null {
  const prior = rankings.weeks.filter((week) => week < gameWeek);
  return prior.length ? prior[prior.length - 1] : null;
}

function findGame(schedule: ScheduleSeason, gameId: string): ScheduleGame | null {
  for (const week of schedule.weeks) {
    const match = (schedule.byWeek[String(week)] || []).find((game) => game.gameId === gameId);
    if (match) return match;
  }
  return null;
}

function gameTime(game: ScheduleGame): string {
  if (game.completed) return "Final";
  if (game.startTimeTBD || !game.startDate) return "Time TBA";
  const date = new Date(game.startDate);
  if (Number.isNaN(date.getTime())) return "Time TBA";
  return date.toLocaleString("en-US", {
    weekday: "long",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function MatchupPage({ params }: { params: Promise<{ season: string; gameId: string }> }) {
  const { season: seasonParam, gameId } = use(params);
  const season = Number.parseInt(seasonParam, 10);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!Number.isFinite(season)) {
      Promise.resolve().then(() => {
        if (!cancelled) setSchedule(null);
      });
      return () => {
        cancelled = true;
      };
    }
    Promise.all([getScheduleSeason(season), getRankingsSeason(season)])
      .then(([scheduleData, rankingData]) => {
        if (cancelled) return;
        setSchedule(scheduleData);
        setRankings(rankingData);
      })
      .catch((error: Error) => {
        if (!cancelled) setLoadError(error);
      });
    return () => {
      cancelled = true;
    };
  }, [season]);

  const game = useMemo(() => (schedule ? findGame(schedule, gameId) : null), [schedule, gameId]);
  const ratingWeek = useMemo(() => {
    if (!rankings || !game) return null;
    return pregameRatingWeek(rankings, game.week);
  }, [rankings, game]);

  const ratings = useMemo(() => {
    if (!rankings || ratingWeek === null || !game) return { away: undefined, home: undefined };
    const rows = rankings.byWeek[String(ratingWeek)] || [];
    return {
      away: rows.find((row) => row.slug === game.awaySlug),
      home: rows.find((row) => row.slug === game.homeSlug),
    };
  }, [rankings, ratingWeek, game]);

  useEffect(() => {
    if (game) document.title = `${game.awayTeam} vs ${game.homeTeam} | GRID`;
  }, [game]);

  if (loadError) throw loadError;

  if (schedule === undefined) {
    return (
      <>
        <SiteHeader tagline="College Football Matchup Analysis" />
        <SiteNav />
        <main className="container weekly-state">Loading matchup…</main>
      </>
    );
  }

  if (!schedule || !game) {
    return (
      <>
        <SiteHeader tagline="College Football Matchup Analysis" />
        <SiteNav />
        <main className="container weekly-state">
          <h2>Matchup not found</h2>
          <p>This game is not in the published FBS-vs-FBS schedule snapshot.</p>
          <Link href="/this-week">Back to This Week →</Link>
        </main>
      </>
    );
  }

  const weekName = schedule.weekLabels?.[String(game.week)] || `Week ${game.week}`;
  const separator = game.neutralSite ? "vs" : "@";

  return (
    <>
      <a className="skip-link" href="#matchupContent">Skip to matchup</a>
      <SiteHeader tagline="College Football Matchup Analysis" />
      <SiteNav />

      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/this-week">This Week</Link>
        <span className="crumb-sep">/</span>
        <span className="crumb-current">{game.awayTeam} {separator} {game.homeTeam}</span>
      </nav>

      <main id="matchupContent" className="container matchup-main">
        <section className="matchup-hero">
          <div className="matchup-hero__meta">
            <span className="eyebrow">{season} · {weekName}</span>
            <span>{gameTime(game)}</span>
          </div>
          <div className="matchup-hero__teams">
            <MatchupTeam game={game} side="away" rating={ratings.away} />
            <span className="matchup-hero__separator">{separator}</span>
            <MatchupTeam game={game} side="home" rating={ratings.home} />
          </div>
          <p className="matchup-hero__context">
            {ratingWeek === null
              ? "No GRID rating existed before the opening week, so this page only shows schedule context."
              : `Pregame snapshot through Week ${ratingWeek}. These numbers do not use results from this game week.`}
          </p>
        </section>

        <section className="matchup-comparison">
          <div className="weekly-section-heading">
            <div>
              <span className="eyebrow">Free Matchup View</span>
              <h2>Where the teams stand</h2>
            </div>
            <span>Value · national rank</span>
          </div>

          <div className="matchup-table" role="table" aria-label={`${game.awayTeam} and ${game.homeTeam} GRID comparison`}>
            <MatchupRow
              label="Overall RPI"
              leftValue={signed(ratings.away?.adjEM)}
              leftRank={ratings.away?.rank}
              rightValue={signed(ratings.home?.adjEM)}
              rightRank={ratings.home?.rank}
            />
            <MatchupRow
              label={`${game.awayTeam} offense / ${game.homeTeam} defense`}
              leftValue={signed(ratings.away?.adjO, 2)}
              leftRank={ratings.away?.adjORank}
              rightValue={signed(ratings.home?.adjD, 2)}
              rightRank={ratings.home?.adjDRank}
              leftTag="RPI-O"
              rightTag="RPI-D"
            />
            <MatchupRow
              label={`${game.homeTeam} offense / ${game.awayTeam} defense`}
              leftValue={signed(ratings.away?.adjD, 2)}
              leftRank={ratings.away?.adjDRank}
              rightValue={signed(ratings.home?.adjO, 2)}
              rightRank={ratings.home?.adjORank}
              leftTag="RPI-D"
              rightTag="RPI-O"
            />
            <MatchupRow
              label="Strength of schedule"
              leftValue={signed(ratings.away?.sos)}
              leftRank={ratings.away?.sosRank}
              rightValue={signed(ratings.home?.sos)}
              rightRank={ratings.home?.sosRank}
              leftTag="SOS"
              rightTag="SOS"
            />
          </div>
        </section>

        <section className="matchup-next">
          <div>
            <span className="eyebrow">Where GRID is going</span>
            <h2>From comparison to matchup intelligence</h2>
            <p>
              This free page is the baseline: team quality, offense, defense and schedule context. The deeper matchup engine will layer in rushing, passing, explosiveness, down-and-distance and other validated edges without hiding the core team profile.
            </p>
          </div>
          <Link href="/this-week" className="utility-link">Back to the full slate →</Link>
        </section>
      </main>

      <SiteFooter note="Matchup pages use the most recent GRID rating snapshot strictly before the selected game week. RPI, RPI-O and RPI-D describe opponent-adjusted performance; they are not a betting line or a game prediction." />
    </>
  );
}

function MatchupTeam({ game, side, rating }: { game: ScheduleGame; side: "away" | "home"; rating?: RankingsRow }) {
  const team = side === "away" ? game.awayTeam : game.homeTeam;
  const teamId = side === "away" ? game.awayTeamId : game.homeTeamId;
  const slug = side === "away" ? game.awaySlug : game.homeSlug;
  return (
    <Link href={`/team/${encodeURIComponent(slug)}`} className="matchup-team" prefetch={false}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={logoUrl(teamId, 256)} alt="" decoding="async" />
      <span>
        <small>{rating?.rank ? `#${rating.rank}` : "Unranked"}</small>
        <strong>{team}</strong>
        <em className="mono">{rating?.record || "—"}</em>
      </span>
    </Link>
  );
}

function MatchupRow({
  label,
  leftValue,
  leftRank,
  rightValue,
  rightRank,
  leftTag,
  rightTag,
}: {
  label: string;
  leftValue: string;
  leftRank: number | null | undefined;
  rightValue: string;
  rightRank: number | null | undefined;
  leftTag?: string;
  rightTag?: string;
}) {
  return (
    <div className="matchup-table__row" role="row">
      <div className="matchup-table__value matchup-table__value--left" role="cell">
        <span>{leftTag}</span>
        <strong className="mono">{leftValue}</strong>
        <em className="mono">{rankText(leftRank)}</em>
      </div>
      <div className="matchup-table__label" role="rowheader">{label}</div>
      <div className="matchup-table__value matchup-table__value--right" role="cell">
        <span>{rightTag}</span>
        <strong className="mono">{rightValue}</strong>
        <em className="mono">{rankText(rightRank)}</em>
      </div>
    </div>
  );
}
