"use client";
/* eslint-disable @next/next/no-img-element */

import { use, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { TipTrigger } from "@/components/Tooltip";
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

function plain(value: number | null | undefined, digits = 1): string {
  if (na(value)) return "—";
  return value.toFixed(digits);
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

function derivedAdvancedRankInfo(
  rows: AdvancedRow[],
  slug: string,
  getter: (row: AdvancedRow) => number | null,
  lowerBetter = false,
): RankInfo {
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: getter(row) }))
    .filter((row): row is { slug: string; value: number } => row.value !== null && Number.isFinite(row.value))
    .sort((a, b) => lowerBetter ? a.value - b.value : b.value - a.value);
  const index = ranked.findIndex((row) => row.slug === slug);
  return { rank: index >= 0 ? index + 1 : null, total: ranked.length };
}

type SideRow = {
  group?: string;
  label: ReactNode;
  value: string;
  rank?: number | null;
  totalTeams: number;
};

type MiniStat = {
  label: string;
  value: string;
  rank: number | null;
  totalTeams: number;
};

type ComparisonRow =
  | {
      kind: "single";
      label: ReactNode;
      leftValue: string;
      leftRank: number | null;
      leftTotal: number;
      rightValue: string;
      rightRank: number | null;
      rightTotal: number;
    }
  | {
      kind: "split";
      label: ReactNode;
      left: MiniStat[];
      right: MiniStat[];
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
    if (game) document.title = `${game.awayTeam} vs ${game.homeTeam} | GRID`;
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
    rating: ratings.away,
    stats: teamStats.away,
    advanced: advancedTeams.away,
    advancedRows,
    slug: game.awaySlug,
    totalRated,
    totalStatted,
  });
  const homeSideRows = teamSideRows({
    rating: ratings.home,
    stats: teamStats.home,
    advanced: advancedTeams.home,
    advancedRows,
    slug: game.homeSlug,
    totalRated,
    totalStatted,
  });
  const awayRows = comparisonRows({
    offense: advancedTeams.away,
    defense: advancedTeams.home,
    offenseStats: teamStats.away,
    defenseStats: teamStats.home,
    advancedRows,
    offenseSlug: game.awaySlug,
    defenseSlug: game.homeSlug,
    totalStatted,
  });
  const homeRows = comparisonRows({
    offense: advancedTeams.home,
    defense: advancedTeams.away,
    offenseStats: teamStats.home,
    defenseStats: teamStats.away,
    advancedRows,
    offenseSlug: game.homeSlug,
    defenseSlug: game.awaySlug,
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

        <div className="matchup-v2-grid">
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
            <ComparisonTable
              offense={{ team: game.awayTeam, teamId: game.awayTeamId }}
              defense={{ team: game.homeTeam, teamId: game.homeTeamId }}
              rows={awayRows}
            />

            <ComparisonTable
              offense={{ team: game.homeTeam, teamId: game.homeTeamId }}
              defense={{ team: game.awayTeam, teamId: game.awayTeamId }}
              rows={homeRows}
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

      <SiteFooter note="Matchup pages use the most recent GRID snapshot strictly before the selected game week. Rank colors are based on each metric's national rank among teams with available data. Defensive EPA and success values are allowed values, so lower is better." />
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
    <aside className={`matchup-v2-side matchup-v2-side--${area}`} aria-label={`${team} team snapshot`}>
      <div className="matchup-v2-side__head">
        <span>
          <strong>{team}</strong>
          <small>{record} · {rank ? `#${rank} GRID` : "Unranked"}</small>
        </span>
        <img src={logoUrl(teamId, 96)} alt="" decoding="async" />
      </div>
      {rows.map((row, index) => {
        const showGroup = Boolean(row.group && (index === 0 || row.group !== rows[index - 1]?.group));
        return (
          <div key={index} className="matchup-v2-side__row-wrap">
            {showGroup ? <div className="matchup-v2-side__group-title">{row.group}</div> : null}
            <div className="matchup-v2-side-row">
              <span className="matchup-v2-side-row__label">{row.label}</span>
              <StatCell value={row.value} rank={row.rank} totalTeams={row.totalTeams} />
            </div>
          </div>
        );
      })}
      <Link href={`/team/${encodeURIComponent(slug)}`} className="matchup-v2-side__link" prefetch={false}>
        Full profile →
      </Link>
    </aside>
  );
}

function ComparisonTable({
  offense,
  defense,
  rows,
}: {
  offense: { team: string; teamId: number };
  defense: { team: string; teamId: number };
  rows: ComparisonRow[];
}) {
  return (
    <section className="matchup-v2-comparison" aria-label={`${offense.team} offense versus ${defense.team} defense`}>
      <div className="matchup-v2-comparison__head">
        <ComparisonTeam team={offense.team} teamId={offense.teamId} label="Offense" />
        <span className="matchup-v2-comparison__vs">vs</span>
        <ComparisonTeam team={defense.team} teamId={defense.teamId} label="Defense" defense />
      </div>

      <div className="matchup-v2-table-head" aria-hidden="true">
        <span>Offense</span>
        <span>Matchup metric</span>
        <span>Defense</span>
      </div>

      {rows.map((row, index) => <ComparisonMetricRow row={row} key={index} />)}
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

function ComparisonMetricRow({ row }: { row: ComparisonRow }) {
  return (
    <div className={`matchup-v2-table-row${row.kind === "split" ? " matchup-v2-table-row--split" : ""}`}>
      {row.kind === "single" ? (
        <StatCell value={row.leftValue} rank={row.leftRank} totalTeams={row.leftTotal} />
      ) : (
        <SplitStatCell stats={row.left} />
      )}
      <div className="matchup-v2-table-row__metric">{row.label}</div>
      {row.kind === "single" ? (
        <StatCell value={row.rightValue} rank={row.rightRank} totalTeams={row.rightTotal} />
      ) : (
        <SplitStatCell stats={row.right} />
      )}
    </div>
  );
}

function StatCell({ value, rank, totalTeams }: { value: string; rank?: number | null; totalTeams: number }) {
  const band = rankBand(rank, totalTeams);
  return (
    <span className="matchup-v2-stat">
      <strong>{value}</strong>
      {rank !== undefined ? (
        <em className={band ? `matchup-v2-rank matchup-v2-rank--${band}` : "matchup-v2-rank"}>{rankText(rank)}</em>
      ) : null}
    </span>
  );
}

function SplitStatCell({ stats }: { stats: MiniStat[] }) {
  return (
    <span className="matchup-v2-split-stat">
      {stats.map((stat) => {
        const band = rankBand(stat.rank, stat.totalTeams);
        return (
          <span className="matchup-v2-split-stat__item" key={stat.label}>
            <small>{stat.label}</small>
            <strong>{stat.value}</strong>
            <em className={band ? `matchup-v2-rank matchup-v2-rank--${band}` : "matchup-v2-rank"}>{rankText(stat.rank)}</em>
          </span>
        );
      })}
    </span>
  );
}

function teamSideRows({
  rating,
  stats,
  advanced,
  advancedRows,
  slug,
  totalRated,
  totalStatted,
}: {
  rating: RankingsRow | undefined;
  stats: TeamStatsRow | undefined;
  advanced: AdvancedRow | undefined;
  advancedRows: AdvancedRow[];
  slug: string;
  totalRated: number;
  totalStatted: number;
}): SideRow[] {
  const epaOffRank = advancedRankInfo(advancedRows, slug, "epaAdj");
  const epaDefRank = advancedRankInfo(advancedRows, slug, "epaAdjAllowed", true);
  const netEpa = advancedNumber(advanced, "epaAdj") !== null && advancedNumber(advanced, "epaAdjAllowed") !== null
    ? (advancedNumber(advanced, "epaAdj") as number) - (advancedNumber(advanced, "epaAdjAllowed") as number)
    : null;
  const netEpaRank = derivedAdvancedRankInfo(
    advancedRows,
    slug,
    (row) => {
      const offense = advancedNumber(row, "epaAdj");
      const defense = advancedNumber(row, "epaAdjAllowed");
      return offense === null || defense === null ? null : offense - defense;
    },
  );

  return [
    { group: "Adjusted EPA", label: "Net Adj EPA / Play", value: signed(netEpa, 3), rank: netEpaRank.rank, totalTeams: netEpaRank.total },
    { group: "Adjusted EPA", label: "Offense", value: signed(advancedNumber(advanced, "epaAdj"), 3), rank: epaOffRank.rank, totalTeams: epaOffRank.total },
    { group: "Adjusted EPA", label: "Defense", value: signed(advancedNumber(advanced, "epaAdjAllowed"), 3), rank: epaDefRank.rank, totalTeams: epaDefRank.total },

    { group: "Offense Success", label: "Overall", value: pct(stats?.successRate), rank: stats?.successRateRank, totalTeams: totalStatted },
    { group: "Offense Success", label: "Pass", value: pct(stats?.passSuccessRate), rank: stats?.passSuccessRateRank, totalTeams: totalStatted },
    { group: "Offense Success", label: "Rush", value: pct(stats?.rushSuccessRate), rank: stats?.rushSuccessRateRank, totalTeams: totalStatted },

    { group: "Defense Success", label: "Overall", value: pct(stats?.successRateAllowed), rank: stats?.successRateAllowedRank, totalTeams: totalStatted },
    { group: "Defense Success", label: "Pass", value: pct(stats?.passSuccessRateAllowed), rank: stats?.passSuccessRateAllowedRank, totalTeams: totalStatted },
    { group: "Defense Success", label: "Rush", value: pct(stats?.rushSuccessRateAllowed), rank: stats?.rushSuccessRateAllowedRank, totalTeams: totalStatted },

    { group: "Profile", label: "Yards / Play", value: plain(stats?.yardsPerPlay, 2), rank: stats?.yardsPerPlayRank, totalTeams: totalStatted },
    { group: "Profile", label: "YPP Allowed", value: plain(stats?.yardsPerPlayAllowed, 2), rank: stats?.yardsPerPlayAllowedRank, totalTeams: totalStatted },
    { group: "Profile", label: "Explosive %", value: pct(stats?.explosivePlayRate), rank: stats?.explosivePlayRateRank, totalTeams: totalStatted },
    { group: "Profile", label: "Explosive Allowed", value: pct(stats?.explosivePlayRateAllowed), rank: stats?.explosivePlayRateAllowedRank, totalTeams: totalStatted },

    { group: "Scoring & Havoc", label: "Finishing", value: plain(stats?.finishingRate, 1), rank: stats?.finishingRateRank, totalTeams: totalStatted },
    { group: "Scoring & Havoc", label: "Finishing Allowed", value: plain(stats?.finishingRateAllowed, 1), rank: stats?.finishingRateAllowedRank, totalTeams: totalStatted },
    { group: "Scoring & Havoc", label: "Havoc Allowed", value: pct(stats?.havocRateAllowed), rank: stats?.havocRateAllowedRank, totalTeams: totalStatted },
    { group: "Scoring & Havoc", label: "Havoc Forced", value: pct(stats?.havocRateForced), rank: stats?.havocRateForcedRank, totalTeams: totalStatted },

    { group: "Context", label: "GRID Rating", value: signed(rating?.adjEM, 1), rank: rating?.rank, totalTeams: totalRated },
    { group: "Context", label: "SOS", value: signed(rating?.sos, 1), rank: rating?.sosRank, totalTeams: totalRated },
    { group: "Context", label: "Field Position", value: signed(stats?.fieldPositionEdge, 1), rank: stats?.fieldPositionEdgeRank, totalTeams: totalStatted },
  ];
}

function comparisonRows({
  offense,
  defense,
  offenseStats,
  defenseStats,
  advancedRows,
  offenseSlug,
  defenseSlug,
  totalStatted,
}: {
  offense: AdvancedRow | undefined;
  defense: AdvancedRow | undefined;
  offenseStats: TeamStatsRow | undefined;
  defenseStats: TeamStatsRow | undefined;
  advancedRows: AdvancedRow[];
  offenseSlug: string;
  defenseSlug: string;
  totalStatted: number;
}): ComparisonRow[] {
  const advRow = (
    label: ReactNode,
    offenseKey: keyof AdvancedRow,
    defenseKey: keyof AdvancedRow,
    formatter: (value: number | null) => string = (value) => signed(value, 3),
  ): ComparisonRow => {
    const leftRank = advancedRankInfo(advancedRows, offenseSlug, offenseKey);
    const rightRank = advancedRankInfo(advancedRows, defenseSlug, defenseKey, true);
    return {
      kind: "single",
      label,
      leftValue: formatter(advancedNumber(offense, offenseKey)),
      leftRank: leftRank.rank,
      leftTotal: leftRank.total,
      rightValue: formatter(advancedNumber(defense, defenseKey)),
      rightRank: rightRank.rank,
      rightTotal: rightRank.total,
    };
  };

  const splitRow = (
    label: ReactNode,
    metrics: Array<{ label: string; offenseKey: keyof AdvancedRow; defenseKey: keyof AdvancedRow }>,
    formatter: (value: number | null) => string = (value) => signed(value, 3),
  ): ComparisonRow => ({
    kind: "split",
    label,
    left: metrics.map((metric) => {
      const info = advancedRankInfo(advancedRows, offenseSlug, metric.offenseKey);
      return {
        label: metric.label,
        value: formatter(advancedNumber(offense, metric.offenseKey)),
        rank: info.rank,
        totalTeams: info.total,
      };
    }),
    right: metrics.map((metric) => {
      const info = advancedRankInfo(advancedRows, defenseSlug, metric.defenseKey, true);
      return {
        label: metric.label,
        value: formatter(advancedNumber(defense, metric.defenseKey)),
        rank: info.rank,
        totalTeams: info.total,
      };
    }),
  });

  return [
    advRow(<>EPA / Play<TipTrigger text="Opponent-adjusted EPA per play. Higher is better on offense; lower EPA allowed is better on defense." /></>, "epaAdj", "epaAdjAllowed"),
    advRow("EPA / Pass", "passEpaAdj", "passEpaAdjAllowed"),
    advRow("EPA / Rush", "rushEpaAdj", "rushEpaAdjAllowed"),
    advRow(<>Success Edge<TipTrigger text="Opponent-adjusted success-rate edge. Higher is better on offense; lower allowed is better on defense." /></>, "successAdj", "successAdjAllowed", pctEdge),
    advRow("Pass Success Edge", "passSuccessAdj", "passSuccessAdjAllowed", pctEdge),
    advRow("Rush Success Edge", "rushSuccessAdj", "rushSuccessAdjAllowed", pctEdge),
    {
      kind: "single",
      label: "Yards / Play",
      leftValue: plain(offenseStats?.yardsPerPlay, 2),
      leftRank: offenseStats?.yardsPerPlayRank ?? null,
      leftTotal: totalStatted,
      rightValue: plain(defenseStats?.yardsPerPlayAllowed, 2),
      rightRank: defenseStats?.yardsPerPlayAllowedRank ?? null,
      rightTotal: totalStatted,
    },
    {
      kind: "single",
      label: "Explosiveness Adj.",
      leftValue: signed(offenseStats?.adjustedExplosivenessOffense, 2),
      leftRank: offenseStats?.adjustedExplosivenessOffenseRank ?? null,
      leftTotal: totalStatted,
      rightValue: signed(defenseStats?.adjustedExplosivenessDefense, 2),
      rightRank: defenseStats?.adjustedExplosivenessDefenseRank ?? null,
      rightTotal: totalStatted,
    },
    {
      kind: "single",
      label: "Finishing Adj.",
      leftValue: signed(offenseStats?.adjustedFinishingOffense, 2),
      leftRank: offenseStats?.adjustedFinishingOffenseRank ?? null,
      leftTotal: totalStatted,
      rightValue: signed(defenseStats?.adjustedFinishingDefense, 2),
      rightRank: defenseStats?.adjustedFinishingDefenseRank ?? null,
      rightTotal: totalStatted,
    },
    {
      kind: "single",
      label: "Havoc Adj.",
      leftValue: signed(offenseStats?.adjustedHavocOffense, 3),
      leftRank: offenseStats?.adjustedHavocOffenseRank ?? null,
      leftTotal: totalStatted,
      rightValue: signed(defenseStats?.adjustedHavocDefense, 3),
      rightRank: defenseStats?.adjustedHavocDefenseRank ?? null,
      rightTotal: totalStatted,
    },
    splitRow("Pass EPA by Down", [
      { label: "1D", offenseKey: "passEpaDown1Adj", defenseKey: "passEpaDown1AdjAllowed" },
      { label: "2D", offenseKey: "passEpaDown2Adj", defenseKey: "passEpaDown2AdjAllowed" },
      { label: "3D", offenseKey: "passEpaDown3Adj", defenseKey: "passEpaDown3AdjAllowed" },
    ]),
    splitRow("Pass Success by Down", [
      { label: "1D", offenseKey: "passSuccessDown1Adj", defenseKey: "passSuccessDown1AdjAllowed" },
      { label: "2D", offenseKey: "passSuccessDown2Adj", defenseKey: "passSuccessDown2AdjAllowed" },
      { label: "3D", offenseKey: "passSuccessDown3Adj", defenseKey: "passSuccessDown3AdjAllowed" },
    ], pctEdge),
    splitRow("Rush EPA by Down", [
      { label: "1D", offenseKey: "rushEpaDown1Adj", defenseKey: "rushEpaDown1AdjAllowed" },
      { label: "2D", offenseKey: "rushEpaDown2Adj", defenseKey: "rushEpaDown2AdjAllowed" },
      { label: "3D", offenseKey: "rushEpaDown3Adj", defenseKey: "rushEpaDown3AdjAllowed" },
    ]),
    splitRow("Rush Success by Down", [
      { label: "1D", offenseKey: "rushSuccessDown1Adj", defenseKey: "rushSuccessDown1AdjAllowed" },
      { label: "2D", offenseKey: "rushSuccessDown2Adj", defenseKey: "rushSuccessDown2AdjAllowed" },
      { label: "3D", offenseKey: "rushSuccessDown3Adj", defenseKey: "rushSuccessDown3AdjAllowed" },
    ], pctEdge),
  ];
}
