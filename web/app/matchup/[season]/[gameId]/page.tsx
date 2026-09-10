"use client";
/* eslint-disable @next/next/no-img-element */

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import {
  getRankingsSeason,
  getScheduleSeason,
  getTeamStatsWeeklySeason,
} from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type {
  AdvancedRow,
  AdvancedSeason,
  RankingsRow,
  RankingsSeason,
  ScheduleGame,
  ScheduleSeason,
  TeamStatsRow,
  TeamStatsWeeklySeason,
} from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function pct(n: number | null | undefined): string {
  if (na(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function pctEdge(n: number | null | undefined): string {
  if (na(n)) return "—";
  const value = n * 100;
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function signed(value: number | null | undefined, digits = 2): string {
  if (na(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function rankText(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `#${value}`;
}

function rankBand(rank: number | null | undefined, totalTeams: number): string | null {
  if (rank === null || rank === undefined || totalTeams <= 0) return null;
  const rankShare = rank / totalTeams;
  if (rankShare <= 0.2) return "elite";
  if (rankShare <= 0.4) return "good";
  if (rankShare <= 0.6) return "middle";
  if (rankShare <= 0.8) return "poor";
  return "bad";
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
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

async function getMatchupAdvancedSeason(year: number): Promise<AdvancedSeason | null> {
  const response = await fetch(`/api/matchup-advanced/${year}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Failed to load matchup analytics: ${response.status}`);
  return response.json() as Promise<AdvancedSeason>;
}

function advancedNumber(row: AdvancedRow | undefined, key: keyof AdvancedRow): number | null {
  if (!row) return null;
  const value = row[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

type RankInfo = { rank: number | null; total: number };

function advancedRankInfo(
  rows: AdvancedRow[],
  slug: string,
  key: keyof AdvancedRow,
  lowerBetter = false,
): RankInfo {
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: advancedNumber(row, key) }))
    .filter((row): row is { slug: string; value: number } => row.value !== null)
    .sort((a, b) => lowerBetter ? a.value - b.value : b.value - a.value);
  const index = ranked.findIndex((row) => row.slug === slug);
  return { rank: index >= 0 ? index + 1 : null, total: ranked.length };
}

type StatDatum = {
  value: string;
  rank: number | null | undefined;
  totalTeams: number;
};

type SideRow = {
  label: string;
  offense: StatDatum;
  defense: StatDatum;
};

type HeadlineRow = {
  label: string;
  left: StatDatum;
  right: StatDatum;
};

export default function MatchupPage({ params }: { params: Promise<{ season: string; gameId: string }> }) {
  const { season: seasonParam, gameId } = use(params);
  const season = Number.parseInt(seasonParam, 10);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
  const [teamStatsWeekly, setTeamStatsWeekly] = useState<TeamStatsWeeklySeason | null>(null);
  const [advanced, setAdvanced] = useState<AdvancedSeason | null>(null);

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

    Promise.all([
      getScheduleSeason(season),
      getRankingsSeason(season),
      getTeamStatsWeeklySeason(season),
      getMatchupAdvancedSeason(season),
    ])
      .then(([scheduleData, rankingData, teamStatsData, advancedData]) => {
        if (cancelled) return;
        setSchedule(scheduleData);
        setRankings(rankingData);
        setTeamStatsWeekly(teamStatsData);
        setAdvanced(advancedData);
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

  const teamStats = useMemo(() => {
    if (!teamStatsWeekly || ratingWeek === null || !game) return { away: undefined, home: undefined };
    const rows = teamStatsWeekly.byWeek[String(ratingWeek)] || [];
    return {
      away: rows.find((row) => row.slug === game.awaySlug),
      home: rows.find((row) => row.slug === game.homeSlug),
    };
  }, [teamStatsWeekly, ratingWeek, game]);

  const advancedRows = useMemo(() => {
    if (!advanced || ratingWeek === null) return [];
    return advanced.byWeek[String(ratingWeek)] || [];
  }, [advanced, ratingWeek]);

  const advancedTeams = useMemo(() => {
    if (!game) return { away: undefined, home: undefined };
    return {
      away: advancedRows.find((row) => row.slug === game.awaySlug),
      home: advancedRows.find((row) => row.slug === game.homeSlug),
    };
  }, [advancedRows, game]);

  useEffect(() => {
    if (game) document.title = `${game.awayTeam} vs ${game.homeTeam} | LEILA Ratings`;
  }, [game]);

  const totalRated = rankings && ratingWeek !== null
    ? (rankings.byWeek[String(ratingWeek)] || []).filter((row) => row.rank !== null).length
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

  const awaySideRows = teamSideRows({
    advanced: advancedTeams.away,
    advancedRows,
    slug: game.awaySlug,
  });
  const homeSideRows = teamSideRows({
    advanced: advancedTeams.home,
    advancedRows,
    slug: game.homeSlug,
  });
  const headlineRows = headlineComparisonRows({
    awayRating: ratings.away,
    homeRating: ratings.home,
    awayStats: teamStats.away,
    homeStats: teamStats.home,
    awayAdvanced: advancedTeams.away,
    homeAdvanced: advancedTeams.home,
    advancedRows,
    awaySlug: game.awaySlug,
    homeSlug: game.homeSlug,
    totalRated,
    totalStatted,
  });

  return (
    <>
      <a className="skip-link" href="#matchupContent">Skip to matchup</a>
      <SiteHeader tagline="College Football Matchup Analysis" />
      <SiteNav />

      <main id="matchupContent" className="container matchup-v2-main">
        <section className="matchup-v2-gamebar" aria-label="Game information">
          <div className="matchup-v2-gamebar__meta">
            <strong>{season} · {weekName}</strong>
            <span>{gameTime(game)}{game.venue ? ` · ${game.venue}` : ""}</span>
          </div>

          <div className="matchup-v2-gamebar__matchup">
            <img src={logoUrl(game.awayTeamId, 64)} alt="" />
            <strong>{game.awayTeam}</strong>
            <span>{separator}</span>
            <strong>{game.homeTeam}</strong>
            <img src={logoUrl(game.homeTeamId, 64)} alt="" />
          </div>

          <div className="matchup-v2-gamebar__snapshot">
            {ratingWeek === null ? "No pregame snapshot" : `Pregame through Week ${ratingWeek}`}
          </div>
        </section>

        <div className="matchup-v2-grid matchup-v2-grid--scouting">
          <TeamSideCard
            area="away"
            team={game.awayTeam}
            teamId={game.awayTeamId}
            slug={game.awaySlug}
            record={ratings.away?.record || "—"}
            rank={ratings.away?.rank}
            rows={awaySideRows}
          />

          <div className="matchup-v2-center">
            <HeadlineComparison
              left={{ team: game.awayTeam, teamId: game.awayTeamId }}
              right={{ team: game.homeTeam, teamId: game.homeTeamId }}
              rows={headlineRows}
            />
          </div>

          <TeamSideCard
            area="home"
            team={game.homeTeam}
            teamId={game.homeTeamId}
            slug={game.homeSlug}
            record={ratings.home?.record || "—"}
            rank={ratings.home?.rank}
            rows={homeSideRows}
          />
        </div>
      </main>

      <SiteFooter note="Matchup pages use the most recent LEILA Ratings snapshot strictly before the selected game week. Rank colors are based on national rank among teams with available data. Defensive EPA and success values are allowed values, so lower is better." />
    </>
  );
}

function TeamSideCard({
  area,
  team,
  teamId,
  slug,
  record,
  rank,
  rows,
}: {
  area: "away" | "home";
  team: string;
  teamId: number;
  slug: string;
  record: string;
  rank: number | null | undefined;
  rows: SideRow[];
}) {
  return (
    <aside className={`matchup-v2-side matchup-v2-side--${area}`} aria-label={`${team} detailed team stats`}>
      <div className="matchup-v2-side__head">
        <span>
          <strong>{team}</strong>
          <small>{record} · {rank ? `#${rank} LEILA Ratings` : "Unranked"}</small>
        </span>
        <img src={logoUrl(teamId, 96)} alt="" decoding="async" />
      </div>

      <TeamStatSection title="Offense" rows={rows} side="offense" />
      <TeamStatSection title="Defense" rows={rows} side="defense" />

      <Link href={`/team/${encodeURIComponent(slug)}`} className="matchup-v2-side__link" prefetch={false}>
        Full profile →
      </Link>
    </aside>
  );
}

function TeamStatSection({
  title,
  rows,
  side,
}: {
  title: "Offense" | "Defense";
  rows: SideRow[];
  side: "offense" | "defense";
}) {
  return (
    <section className="matchup-v2-team-section" aria-label={title}>
      <div className="matchup-v2-team-section__title">{title}</div>
      {rows.map((row) => (
        <div className="matchup-v2-team-section__row" key={`${side}-${row.label}`}>
          <span>{row.label}</span>
          <StatCell {...row[side]} compact />
        </div>
      ))}
    </section>
  );
}

function HeadlineComparison({
  left,
  right,
  rows,
}: {
  left: { team: string; teamId: number };
  right: { team: string; teamId: number };
  rows: HeadlineRow[];
}) {
  return (
    <section className="matchup-v2-comparison matchup-v2-comparison--headline" aria-label={`${left.team} versus ${right.team} headline comparison`}>
      <div className="matchup-v2-comparison__head matchup-v2-comparison__head--teams">
        <ComparisonTeam team={left.team} teamId={left.teamId} label="Team" />
        <span className="matchup-v2-comparison__vs">vs</span>
        <ComparisonTeam team={right.team} teamId={right.teamId} label="Team" defense />
      </div>

      <div className="matchup-v2-table-head" aria-hidden="true">
        <span>{left.team}</span>
        <span>Headline metric</span>
        <span>{right.team}</span>
      </div>

      {rows.map((row) => (
        <div className="matchup-v2-table-row matchup-v2-table-row--headline" key={row.label}>
          <StatCell {...row.left} />
          <div className="matchup-v2-table-row__metric">{row.label}</div>
          <StatCell {...row.right} />
        </div>
      ))}
    </section>
  );
}

function ComparisonTeam({ team, teamId, label, defense = false }: { team: string; teamId: number; label: string; defense?: boolean }) {
  return (
    <div className={`matchup-v2-comparison-team${defense ? " matchup-v2-comparison-team--defense" : ""}`}>
      <img src={logoUrl(teamId, 64)} alt="" decoding="async" />
      <span>
        <strong>{team}</strong>
        <small>{label}</small>
      </span>
    </div>
  );
}

function StatCell({
  value,
  rank,
  totalTeams,
  compact = false,
}: StatDatum & { compact?: boolean }) {
  const band = rankBand(rank, totalTeams);
  return (
    <span className={`matchup-v2-stat${compact ? " matchup-v2-stat--compact" : ""}`}>
      <strong>{value}</strong>
      <em className={band ? `matchup-v2-rank matchup-v2-rank--${band}` : "matchup-v2-rank"}>{rankText(rank)}</em>
    </span>
  );
}

function advancedDatum(
  row: AdvancedRow | undefined,
  rows: AdvancedRow[],
  slug: string,
  key: keyof AdvancedRow,
  lowerBetter: boolean,
  formatter: (value: number | null) => string,
): StatDatum {
  const info = advancedRankInfo(rows, slug, key, lowerBetter);
  return {
    value: formatter(advancedNumber(row, key)),
    rank: info.rank,
    totalTeams: info.total,
  };
}

function teamSideRows({
  advanced,
  advancedRows,
  slug,
}: {
  advanced: AdvancedRow | undefined;
  advancedRows: AdvancedRow[];
  slug: string;
}): SideRow[] {
  const makeRow = (
    label: string,
    offenseKey: keyof AdvancedRow,
    defenseKey: keyof AdvancedRow,
    formatter: (value: number | null) => string = (value) => signed(value, 3),
  ): SideRow => ({
    label,
    offense: advancedDatum(advanced, advancedRows, slug, offenseKey, false, formatter),
    defense: advancedDatum(advanced, advancedRows, slug, defenseKey, true, formatter),
  });

  return [
    makeRow("EPA / Pass", "passEpaAdj", "passEpaAdjAllowed"),
    makeRow("EPA / Rush", "rushEpaAdj", "rushEpaAdjAllowed"),
    makeRow("SR / Pass", "passSuccessAdj", "passSuccessAdjAllowed", pctEdge),
    makeRow("SR / Rush", "rushSuccessAdj", "rushSuccessAdjAllowed", pctEdge),
  ];
}

function headlineComparisonRows({
  awayRating,
  homeRating,
  awayStats,
  homeStats,
  awayAdvanced,
  homeAdvanced,
  advancedRows,
  awaySlug,
  homeSlug,
  totalRated,
  totalStatted,
}: {
  awayRating: RankingsRow | undefined;
  homeRating: RankingsRow | undefined;
  awayStats: TeamStatsRow | undefined;
  homeStats: TeamStatsRow | undefined;
  awayAdvanced: AdvancedRow | undefined;
  homeAdvanced: AdvancedRow | undefined;
  advancedRows: AdvancedRow[];
  awaySlug: string;
  homeSlug: string;
  totalRated: number;
  totalStatted: number;
}): HeadlineRow[] {
  const awayEpaOff = advancedDatum(awayAdvanced, advancedRows, awaySlug, "epaAdj", false, (value) => signed(value, 3));
  const homeEpaOff = advancedDatum(homeAdvanced, advancedRows, homeSlug, "epaAdj", false, (value) => signed(value, 3));
  const awayEpaDef = advancedDatum(awayAdvanced, advancedRows, awaySlug, "epaAdjAllowed", true, (value) => signed(value, 3));
  const homeEpaDef = advancedDatum(homeAdvanced, advancedRows, homeSlug, "epaAdjAllowed", true, (value) => signed(value, 3));

  return [
    {
      label: "Overall Rating",
      left: { value: signed(awayRating?.adjEM, 1), rank: awayRating?.rank, totalTeams: totalRated },
      right: { value: signed(homeRating?.adjEM, 1), rank: homeRating?.rank, totalTeams: totalRated },
    },
    {
      label: "Offense Rating",
      left: { value: signed(awayRating?.adjO, 2), rank: awayRating?.adjORank, totalTeams: totalRated },
      right: { value: signed(homeRating?.adjO, 2), rank: homeRating?.adjORank, totalTeams: totalRated },
    },
    {
      label: "Defense Rating",
      left: { value: signed(awayRating?.adjD, 2), rank: awayRating?.adjDRank, totalTeams: totalRated },
      right: { value: signed(homeRating?.adjD, 2), rank: homeRating?.adjDRank, totalTeams: totalRated },
    },
    { label: "EPA / Play · Offense", left: awayEpaOff, right: homeEpaOff },
    { label: "EPA / Play · Defense", left: awayEpaDef, right: homeEpaDef },
    {
      label: "Success Rate · Offense",
      left: { value: pct(awayStats?.successRate), rank: awayStats?.successRateRank, totalTeams: totalStatted },
      right: { value: pct(homeStats?.successRate), rank: homeStats?.successRateRank, totalTeams: totalStatted },
    },
    {
      label: "Success Rate · Defense",
      left: { value: pct(awayStats?.successRateAllowed), rank: awayStats?.successRateAllowedRank, totalTeams: totalStatted },
      right: { value: pct(homeStats?.successRateAllowed), rank: homeStats?.successRateAllowedRank, totalTeams: totalStatted },
    },
  ];
}
