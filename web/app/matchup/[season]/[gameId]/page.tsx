"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { TipTrigger } from "@/components/Tooltip";
import { getRankingsSeason, getScheduleSeason, getTeamStatsWeeklySeason } from "@/lib/data";
import { logoUrl, teamCode } from "@/lib/teamCode";
import type { RankingsRow, RankingsSeason, ScheduleGame, ScheduleSeason, TeamStatsRow, TeamStatsWeeklySeason } from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function pct(n: number | null | undefined): string {
  if (na(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function signed(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function rankText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `#${value}`;
}

// Rank is already direction-normalized everywhere it's computed (rank 1 is
// always the best value for that stat, whichever raw direction "best"
// means), so tiering by rank/totalTeams alone is safe for every row here.
function tier(rank: number | null | undefined, totalTeams: number): string | null {
  if (rank === null || rank === undefined || !totalTeams) return null;
  const pctile = rank / totalTeams;
  if (pctile <= 0.15) return "high";
  if (pctile <= 0.4) return "mid-high";
  if (pctile >= 0.85) return "low";
  if (pctile >= 0.6) return "mid-low";
  return null;
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
  const [teamStatsWeekly, setTeamStatsWeekly] = useState<TeamStatsWeeklySeason | null>(null);

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
    Promise.all([getScheduleSeason(season), getRankingsSeason(season), getTeamStatsWeeklySeason(season)])
      .then(([scheduleData, rankingData, teamStatsData]) => {
        if (cancelled) return;
        setSchedule(scheduleData);
        setRankings(rankingData);
        setTeamStatsWeekly(teamStatsData);
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

  // Same pregame week as the RPI snapshot above -- team-stats-weekly is
  // published per week specifically so this join can never pull in a later
  // week's (or the current, still-in-progress week's) results.
  const teamStats = useMemo(() => {
    if (!teamStatsWeekly || ratingWeek === null || !game) return { away: undefined, home: undefined };
    const rows = teamStatsWeekly.byWeek[String(ratingWeek)] || [];
    return {
      away: rows.find((row) => row.slug === game.awaySlug),
      home: rows.find((row) => row.slug === game.homeSlug),
    };
  }, [teamStatsWeekly, ratingWeek, game]);

  useEffect(() => {
    if (game) document.title = `${game.awayTeam} vs ${game.homeTeam} | GRID`;
  }, [game]);

  // Percentile tiering needs a denominator -- how many teams that week's
  // rank could possibly be drawn from. Rankings and team-stats-weekly are
  // separately published snapshots, so each gets its own count.
  const totalRated = rankings && ratingWeek !== null
    ? (rankings.byWeek[String(ratingWeek)] || []).filter((r) => r.rank !== null).length
    : 0;
  const totalStatted = teamStatsWeekly && ratingWeek !== null
    ? (teamStatsWeekly.byWeek[String(ratingWeek)] || []).length
    : 0;

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

        <section className="matchup-panels">
          <div className="weekly-section-heading">
            <div>
              <span className="eyebrow">Free Matchup View</span>
              <h2>Where the teams stand</h2>
            </div>
            <span>Value · national rank</span>
          </div>

          <div className="matchup-panel-grid">
            <MatchupPanel
              title="Overall"
              left={{ team: game.awayTeam, teamId: game.awayTeamId }}
              right={{ team: game.homeTeam, teamId: game.homeTeamId }}
              totalTeams={totalRated}
              rows={overallRows(ratings.away, ratings.home)}
            />
            <MatchupPanel
              title={`${teamCode(game.awayTeam)} Off vs ${teamCode(game.homeTeam)} Def`}
              left={{ team: game.awayTeam, teamId: game.awayTeamId }}
              right={{ team: game.homeTeam, teamId: game.homeTeamId }}
              totalTeams={totalStatted}
              rows={offenseVsDefenseRows(teamStats.away, teamStats.home)}
            />
            <MatchupPanel
              title={`${teamCode(game.homeTeam)} Off vs ${teamCode(game.awayTeam)} Def`}
              left={{ team: game.homeTeam, teamId: game.homeTeamId }}
              right={{ team: game.awayTeam, teamId: game.awayTeamId }}
              totalTeams={totalStatted}
              rows={offenseVsDefenseRows(teamStats.home, teamStats.away)}
            />
          </div>
        </section>

        <section className="matchup-next">
          <div>
            <span className="eyebrow">Where GRID is going</span>
            <h2>From comparison to matchup intelligence</h2>
            <p>
              This free page is the baseline: team quality, offense, defense, schedule context and how each side&rsquo;s offense lines up against the other&rsquo;s defense. The deeper matchup engine will add down-and-distance splits, situational edges and eventually full matchup intelligence without hiding the core team profile.
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

type PanelRowSpec = {
  label: React.ReactNode;
  leftValue: string;
  leftRank: number | null | undefined;
  rightValue: string;
  rightRank: number | null | undefined;
};

function overallRows(away?: RankingsRow, home?: RankingsRow): PanelRowSpec[] {
  return [
    { label: "RPI (AdjEM)", leftValue: signed(away?.adjEM), leftRank: away?.rank, rightValue: signed(home?.adjEM), rightRank: home?.rank },
    { label: "RPI-O", leftValue: signed(away?.adjO, 2), leftRank: away?.adjORank, rightValue: signed(home?.adjO, 2), rightRank: home?.adjORank },
    { label: "RPI-D", leftValue: signed(away?.adjD, 2), leftRank: away?.adjDRank, rightValue: signed(home?.adjD, 2), rightRank: home?.adjDRank },
    { label: "Strength of Schedule", leftValue: signed(away?.sos), leftRank: away?.sosRank, rightValue: signed(home?.sos), rightRank: home?.sosRank },
    { label: "Strength of Record", leftValue: signed(away?.sor), leftRank: away?.sorRank, rightValue: signed(home?.sor), rightRank: home?.sorRank },
  ];
}

function offenseVsDefenseRows(offense?: TeamStatsRow, defense?: TeamStatsRow): PanelRowSpec[] {
  return [
    {
      label: <>Success rate<TipTrigger text="Raw season-to-date success rate, not opponent-adjusted." /></>,
      leftValue: pct(offense?.successRate), leftRank: offense?.successRateRank,
      rightValue: pct(defense?.successRateAllowed), rightRank: defense?.successRateAllowedRank,
    },
    {
      label: <>Rush success<TipTrigger text="Raw season-to-date rushing success rate, not opponent-adjusted." /></>,
      leftValue: pct(offense?.rushSuccessRate), leftRank: offense?.rushSuccessRateRank,
      rightValue: pct(defense?.rushSuccessRateAllowed), rightRank: defense?.rushSuccessRateAllowedRank,
    },
    {
      label: <>Pass success<TipTrigger text="Raw season-to-date passing success rate, not opponent-adjusted." /></>,
      leftValue: pct(offense?.passSuccessRate), leftRank: offense?.passSuccessRateRank,
      rightValue: pct(defense?.passSuccessRateAllowed), rightRank: defense?.passSuccessRateAllowedRank,
    },
    {
      label: <>Yards / play<TipTrigger text="Raw season-to-date yards per play, not opponent-adjusted." /></>,
      leftValue: signed(offense?.yardsPerPlay, 2), leftRank: offense?.yardsPerPlayRank,
      rightValue: signed(defense?.yardsPerPlayAllowed, 2), rightRank: defense?.yardsPerPlayAllowedRank,
    },
    {
      label: <>Explosiveness (adj.)<TipTrigger text="GRID's opponent-adjusted explosiveness edge, a research-stage model snapshot -- not the raw explosive-play rate." /></>,
      leftValue: signed(offense?.adjustedExplosivenessOffense, 2), leftRank: offense?.adjustedExplosivenessOffenseRank,
      rightValue: signed(defense?.adjustedExplosivenessDefense, 2), rightRank: defense?.adjustedExplosivenessDefenseRank,
    },
    {
      label: <>Finishing drives (adj.)<TipTrigger text="GRID's opponent-adjusted finishing model, a research-stage snapshot -- how efficiently scoring opportunities turn into points." /></>,
      leftValue: signed(offense?.adjustedFinishingOffense, 2), leftRank: offense?.adjustedFinishingOffenseRank,
      rightValue: signed(defense?.adjustedFinishingDefense, 2), rightRank: defense?.adjustedFinishingDefenseRank,
    },
    {
      label: <>Havoc (adj.)<TipTrigger text="GRID's opponent-adjusted model of TFLs, sacks and turnovers -- higher is better for both sides here, since each is framed as beating expectation." /></>,
      leftValue: signed(offense?.adjustedHavocOffense, 3), leftRank: offense?.adjustedHavocOffenseRank,
      rightValue: signed(defense?.adjustedHavocDefense, 3), rightRank: defense?.adjustedHavocDefenseRank,
    },
  ];
}

function MatchupPanel({
  title,
  left,
  right,
  rows,
  totalTeams,
}: {
  title: string;
  left: { team: string; teamId: number };
  right: { team: string; teamId: number };
  rows: PanelRowSpec[];
  totalTeams: number;
}) {
  return (
    <div className="matchup-panel" role="table" aria-label={title}>
      <div className="matchup-panel__head" role="row">
        <span className="matchup-panel__title">{title}</span>
        <span className="matchup-panel__head-logo" role="columnheader">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoUrl(left.teamId, 64)} alt={left.team} decoding="async" />
        </span>
        <span className="matchup-panel__head-logo" role="columnheader">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoUrl(right.teamId, 64)} alt={right.team} decoding="async" />
        </span>
      </div>
      {rows.map((row, index) => (
        <div className="matchup-panel__row" role="row" key={index}>
          <div className="matchup-panel__label" role="rowheader">{row.label}</div>
          <div className={`matchup-panel__cell${tier(row.leftRank, totalTeams) ? ` matchup-panel__cell--${tier(row.leftRank, totalTeams)}` : ""}`} role="cell">
            <strong className="mono">{row.leftValue}</strong>
            <em className="mono">{rankText(row.leftRank)}</em>
          </div>
          <div className={`matchup-panel__cell${tier(row.rightRank, totalTeams) ? ` matchup-panel__cell--${tier(row.rightRank, totalTeams)}` : ""}`} role="cell">
            <strong className="mono">{row.rightValue}</strong>
            <em className="mono">{rankText(row.rightRank)}</em>
          </div>
        </div>
      ))}
    </div>
  );
}
