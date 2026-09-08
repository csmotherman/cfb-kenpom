"use client";
/* eslint-disable @next/next/no-img-element */

import { use, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { TipTrigger } from "@/components/Tooltip";
import {
  getAdvancedSeason,
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

function tier(rank: number | null | undefined, totalTeams: number): string | null {
  if (rank === null || rank === undefined || !totalTeams) return null;
  const percentile = rank / totalTeams;
  if (percentile <= 0.15) return "high";
  if (percentile <= 0.4) return "mid-high";
  if (percentile >= 0.85) return "low";
  if (percentile >= 0.6) return "mid-low";
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
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

type AccessPayload = { ultimate?: boolean };
type MatchupView = "overview" | "passing" | "rushing";

async function getMatchupAccess(): Promise<boolean> {
  try {
    const response = await fetch("/api/matchup-access", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) return false;
    const payload = (await response.json()) as AccessPayload;
    return payload.ultimate === true;
  } catch {
    return false;
  }
}

function advancedNumber(row: AdvancedRow | undefined, key: keyof AdvancedRow): number | null {
  if (!row) return null;
  const value = row[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function advancedRank(
  rows: AdvancedRow[],
  slug: string,
  key: keyof AdvancedRow,
  lowerBetter = false,
): number | null {
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: advancedNumber(row, key) }))
    .filter((row): row is { slug: string; value: number } => row.value !== null)
    .sort((a, b) => lowerBetter ? a.value - b.value : b.value - a.value);
  const index = ranked.findIndex((row) => row.slug === slug);
  return index >= 0 ? index + 1 : null;
}

type SideRow = {
  group?: string;
  label: ReactNode;
  value: string;
  rank?: number | null;
  totalTeams: number;
};

type ComparisonRow = {
  label: ReactNode;
  leftValue: string;
  leftRank?: number | null;
  rightValue: string;
  rightRank?: number | null;
  totalTeams: number;
  premium?: boolean;
};

export default function MatchupPage({ params }: { params: Promise<{ season: string; gameId: string }> }) {
  const { season: seasonParam, gameId } = use(params);
  const season = Number.parseInt(seasonParam, 10);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
  const [teamStatsWeekly, setTeamStatsWeekly] = useState<TeamStatsWeeklySeason | null>(null);
  const [advanced, setAdvanced] = useState<AdvancedSeason | null | undefined>(undefined);
  const [ultimateAccess, setUltimateAccess] = useState(false);
  const [accessResolved, setAccessResolved] = useState(false);
  const [view, setView] = useState<MatchupView>("overview");

  useEffect(() => {
    let cancelled = false;
    if (!Number.isFinite(season)) {
      Promise.resolve().then(() => {
        if (!cancelled) {
          setSchedule(null);
          setAccessResolved(true);
          setAdvanced(null);
        }
      });
      return () => {
        cancelled = true;
      };
    }

    Promise.all([
      getScheduleSeason(season),
      getRankingsSeason(season),
      getTeamStatsWeeklySeason(season),
      getMatchupAccess(),
    ])
      .then(async ([scheduleData, rankingData, teamStatsData, hasUltimate]) => {
        if (cancelled) return;
        setSchedule(scheduleData);
        setRankings(rankingData);
        setTeamStatsWeekly(teamStatsData);
        setUltimateAccess(hasUltimate);
        setAccessResolved(true);

        if (!hasUltimate) {
          setAdvanced(null);
          return;
        }

        try {
          const advancedData = await getAdvancedSeason(season);
          if (!cancelled) setAdvanced(advancedData);
        } catch {
          if (!cancelled) setAdvanced(null);
        }
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
  const totalAdvanced = advancedRows.length;

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
  const awaySideRows = teamSideRows(ratings.away, teamStats.away, totalRated, totalStatted);
  const homeSideRows = teamSideRows(ratings.home, teamStats.home, totalRated, totalStatted);
  const awayRows = comparisonRows({
    view,
    offense: advancedTeams.away,
    defense: advancedTeams.home,
    offenseStats: teamStats.away,
    defenseStats: teamStats.home,
    advancedRows,
    offenseSlug: game.awaySlug,
    defenseSlug: game.homeSlug,
    totalAdvanced,
    totalStatted,
  });
  const homeRows = comparisonRows({
    view,
    offense: advancedTeams.home,
    defense: advancedTeams.away,
    offenseStats: teamStats.home,
    defenseStats: teamStats.away,
    advancedRows,
    offenseSlug: game.homeSlug,
    defenseSlug: game.awaySlug,
    totalAdvanced,
    totalStatted,
  });
  const advancedLoading = ultimateAccess && advanced === undefined;

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

          <div className="matchup-v2-views" role="group" aria-label="Matchup stat view">
            {(["overview", "passing", "rushing"] as MatchupView[]).map((option) => (
              <button
                type="button"
                key={option}
                className={view === option ? "active" : undefined}
                aria-pressed={view === option}
                onClick={() => setView(option)}
              >
                {option === "overview" ? "Overview" : option === "passing" ? "Passing" : "Rushing"}
              </button>
            ))}
          </div>
        </section>

        <div className="matchup-v2-snapshot-note">
          <span>{ratingWeek === null ? "No pregame GRID snapshot available" : `Pregame through Week ${ratingWeek}`}</span>
          <span>Value · national rank</span>
          {!ultimateAccess && accessResolved ? <span>Ultimate rows are blurred</span> : null}
        </div>

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
              view={view}
              accessResolved={accessResolved}
              ultimateAccess={ultimateAccess}
              advancedLoading={advancedLoading}
            />

            <ComparisonTable
              offense={{ team: game.homeTeam, teamId: game.homeTeamId }}
              defense={{ team: game.awayTeam, teamId: game.awayTeamId }}
              rows={homeRows}
              view={view}
              accessResolved={accessResolved}
              ultimateAccess={ultimateAccess}
              advancedLoading={advancedLoading}
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

        <section className="matchup-v2-footer-note">
          <p>Free users keep the core matchup profile. Ultimate unlocks opponent-adjusted EPA, success-rate edges and down-specific passing/rushing splits.</p>
          <Link href="/this-week" className="utility-link">Full slate →</Link>
        </section>
      </main>

      <SiteFooter note="Matchup pages use the most recent GRID snapshot strictly before the selected game week. Defensive EPA and success values are allowed values, so lower is better. Ultimate matchup access is currently tied to active or trialing GRID Pro+ access." />
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
  view,
  accessResolved,
  ultimateAccess,
  advancedLoading,
}: {
  offense: { team: string; teamId: number };
  defense: { team: string; teamId: number };
  rows: ComparisonRow[];
  view: MatchupView;
  accessResolved: boolean;
  ultimateAccess: boolean;
  advancedLoading: boolean;
}) {
  const hasPremium = rows.some((row) => row.premium);
  const locked = accessResolved && !ultimateAccess;
  return (
    <section className="matchup-v2-comparison" aria-label={`${offense.team} offense versus ${defense.team} defense`}>
      <div className="matchup-v2-comparison__head">
        <ComparisonTeam team={offense.team} teamId={offense.teamId} label="Offense" />
        <span className="matchup-v2-comparison__vs">vs</span>
        <ComparisonTeam team={defense.team} teamId={defense.teamId} label="Defense" defense />
      </div>

      <div className="matchup-v2-table-head" aria-hidden="true">
        <span>Offense</span>
        <span>{view === "overview" ? "Matchup metric" : view === "passing" ? "Passing metric" : "Rushing metric"}</span>
        <span>Defense</span>
      </div>

      {rows.map((row, index) => {
        const premiumWaiting = Boolean(row.premium && ultimateAccess && advancedLoading);
        return (
          <ComparisonMetricRow
            row={row}
            locked={Boolean(row.premium && locked)}
            loading={premiumWaiting}
            key={`${view}-${index}`}
          />
        );
      })}

      {!accessResolved ? <div className="matchup-v2-access-status">Checking Ultimate access…</div> : null}
      {hasPremium && locked ? (
        <div className="matchup-v2-unlock-strip">
          <span><b>Ultimate</b> adjusted values blurred</span>
          <Link href="/upgrade?feature=matchup&plan=pro_plus">Unlock →</Link>
        </div>
      ) : null}
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

function ComparisonMetricRow({ row, locked = false, loading = false }: { row: ComparisonRow; locked?: boolean; loading?: boolean }) {
  const conceal = locked || loading;
  return (
    <div className={`matchup-v2-table-row${locked ? " matchup-v2-table-row--locked" : ""}`}>
      <StatCell
        value={conceal ? "+0.000" : row.leftValue}
        rank={conceal ? 42 : row.leftRank}
        totalTeams={conceal ? 134 : row.totalTeams}
        locked={conceal}
      />
      <div className="matchup-v2-table-row__metric">
        {row.label}
        {row.premium ? <span className="matchup-v2-row-badge">U</span> : null}
      </div>
      <StatCell
        value={conceal ? "-0.000" : row.rightValue}
        rank={conceal ? 42 : row.rightRank}
        totalTeams={conceal ? 134 : row.totalTeams}
        locked={conceal}
      />
    </div>
  );
}

function StatCell({ value, rank, totalTeams, locked = false }: { value: string; rank?: number | null; totalTeams: number; locked?: boolean }) {
  const band = locked ? null : tier(rank, totalTeams);
  return (
    <span className={`matchup-v2-stat${band ? ` matchup-v2-stat--${band}` : ""}${locked ? " matchup-v2-stat--locked" : ""}`} aria-hidden={locked || undefined}>
      <strong>{value}</strong>
      {rank !== undefined ? <em>{rankText(rank)}</em> : null}
    </span>
  );
}

function teamSideRows(
  rating: RankingsRow | undefined,
  stats: TeamStatsRow | undefined,
  totalRated: number,
  totalStatted: number,
): SideRow[] {
  return [
    { group: "Ratings", label: "GRID rating", value: signed(rating?.adjEM, 1), rank: rating?.rank, totalTeams: totalRated },
    { group: "Ratings", label: "Offense", value: signed(rating?.adjO, 2), rank: rating?.adjORank, totalTeams: totalRated },
    { group: "Ratings", label: "Defense", value: signed(rating?.adjD, 2), rank: rating?.adjDRank, totalTeams: totalRated },
    { group: "Schedule", label: "SOS", value: signed(rating?.sos, 1), rank: rating?.sosRank, totalTeams: totalRated },
    { group: "Schedule", label: "SOR", value: signed(rating?.sor, 1), rank: rating?.sorRank, totalTeams: totalRated },
    { group: "Profile", label: "Yards / play", value: plain(stats?.yardsPerPlay, 2), rank: stats?.yardsPerPlayRank, totalTeams: totalStatted },
    { group: "Profile", label: "Success rate", value: pct(stats?.successRate), rank: stats?.successRateRank, totalTeams: totalStatted },
    { group: "Profile", label: "Field position", value: signed(stats?.fieldPositionEdge, 1), rank: stats?.fieldPositionEdgeRank, totalTeams: totalStatted },
  ];
}

function comparisonRows({
  view,
  offense,
  defense,
  offenseStats,
  defenseStats,
  advancedRows,
  offenseSlug,
  defenseSlug,
  totalAdvanced,
  totalStatted,
}: {
  view: MatchupView;
  offense: AdvancedRow | undefined;
  defense: AdvancedRow | undefined;
  offenseStats: TeamStatsRow | undefined;
  defenseStats: TeamStatsRow | undefined;
  advancedRows: AdvancedRow[];
  offenseSlug: string;
  defenseSlug: string;
  totalAdvanced: number;
  totalStatted: number;
}): ComparisonRow[] {
  const advRow = (
    label: ReactNode,
    offenseKey: keyof AdvancedRow,
    defenseKey: keyof AdvancedRow,
    digits = 3,
  ): ComparisonRow => ({
    label,
    leftValue: signed(advancedNumber(offense, offenseKey), digits),
    leftRank: advancedRank(advancedRows, offenseSlug, offenseKey),
    rightValue: signed(advancedNumber(defense, defenseKey), digits),
    rightRank: advancedRank(advancedRows, defenseSlug, defenseKey, true),
    totalTeams: totalAdvanced,
    premium: true,
  });

  if (view === "passing") {
    return [
      {
        label: "Pass success",
        leftValue: pct(offenseStats?.passSuccessRate), leftRank: offenseStats?.passSuccessRateRank,
        rightValue: pct(defenseStats?.passSuccessRateAllowed), rightRank: defenseStats?.passSuccessRateAllowedRank,
        totalTeams: totalStatted,
      },
      advRow("EPA / pass", "passEpaAdj", "passEpaAdjAllowed"),
      advRow("Pass success edge", "passSuccessAdj", "passSuccessAdjAllowed"),
      advRow("1st down EPA", "passEpaDown1Adj", "passEpaDown1AdjAllowed"),
      advRow("2nd down EPA", "passEpaDown2Adj", "passEpaDown2AdjAllowed"),
      advRow("3rd down EPA", "passEpaDown3Adj", "passEpaDown3AdjAllowed"),
      advRow("1st down success", "passSuccessDown1Adj", "passSuccessDown1AdjAllowed"),
      advRow("2nd down success", "passSuccessDown2Adj", "passSuccessDown2AdjAllowed"),
      advRow("3rd down success", "passSuccessDown3Adj", "passSuccessDown3AdjAllowed"),
    ];
  }

  if (view === "rushing") {
    return [
      {
        label: "Rush success",
        leftValue: pct(offenseStats?.rushSuccessRate), leftRank: offenseStats?.rushSuccessRateRank,
        rightValue: pct(defenseStats?.rushSuccessRateAllowed), rightRank: defenseStats?.rushSuccessRateAllowedRank,
        totalTeams: totalStatted,
      },
      advRow("EPA / rush", "rushEpaAdj", "rushEpaAdjAllowed"),
      advRow("Rush success edge", "rushSuccessAdj", "rushSuccessAdjAllowed"),
      advRow("1st down EPA", "rushEpaDown1Adj", "rushEpaDown1AdjAllowed"),
      advRow("2nd down EPA", "rushEpaDown2Adj", "rushEpaDown2AdjAllowed"),
      advRow("3rd down EPA", "rushEpaDown3Adj", "rushEpaDown3AdjAllowed"),
      advRow("1st down success", "rushSuccessDown1Adj", "rushSuccessDown1AdjAllowed"),
      advRow("2nd down success", "rushSuccessDown2Adj", "rushSuccessDown2AdjAllowed"),
      advRow("3rd down success", "rushSuccessDown3Adj", "rushSuccessDown3AdjAllowed"),
    ];
  }

  return [
    {
      label: <>Yards / play<TipTrigger text="Raw pregame yards per play. Defense is yards per play allowed, so lower is better on the defensive side." /></>,
      leftValue: plain(offenseStats?.yardsPerPlay, 2), leftRank: offenseStats?.yardsPerPlayRank,
      rightValue: plain(defenseStats?.yardsPerPlayAllowed, 2), rightRank: defenseStats?.yardsPerPlayAllowedRank,
      totalTeams: totalStatted,
    },
    {
      label: <>Success rate<TipTrigger text="Raw pregame success rate. Defense is opponent success rate allowed, so lower is better on the defensive side." /></>,
      leftValue: pct(offenseStats?.successRate), leftRank: offenseStats?.successRateRank,
      rightValue: pct(defenseStats?.successRateAllowed), rightRank: defenseStats?.successRateAllowedRank,
      totalTeams: totalStatted,
    },
    {
      label: "Explosive play %",
      leftValue: pct(offenseStats?.explosivePlayRate), leftRank: offenseStats?.explosivePlayRateRank,
      rightValue: pct(defenseStats?.explosivePlayRateAllowed), rightRank: defenseStats?.explosivePlayRateAllowedRank,
      totalTeams: totalStatted,
    },
    {
      label: "Finishing drives",
      leftValue: plain(offenseStats?.finishingRate, 1), leftRank: offenseStats?.finishingRateRank,
      rightValue: plain(defenseStats?.finishingRateAllowed, 1), rightRank: defenseStats?.finishingRateAllowedRank,
      totalTeams: totalStatted,
    },
    {
      label: <>Havoc<TipTrigger text="Offense shows the rate of plays that surrender a TFL, sack or turnover; defense shows the rate forced." /></>,
      leftValue: pct(offenseStats?.havocRateAllowed), leftRank: offenseStats?.havocRateAllowedRank,
      rightValue: pct(defenseStats?.havocRateForced), rightRank: defenseStats?.havocRateForcedRank,
      totalTeams: totalStatted,
    },
    advRow(<>EPA / play<TipTrigger text="Opponent-adjusted EPA per play. Higher is better on offense; lower EPA allowed is better on defense." /></>, "epaAdj", "epaAdjAllowed"),
    advRow(<>Success edge<TipTrigger text="Opponent-adjusted success-rate edge. Higher is better on offense; lower allowed is better on defense." /></>, "successAdj", "successAdjAllowed"),
    {
      label: "Explosiveness adj.",
      leftValue: signed(offenseStats?.adjustedExplosivenessOffense, 2), leftRank: offenseStats?.adjustedExplosivenessOffenseRank,
      rightValue: signed(defenseStats?.adjustedExplosivenessDefense, 2), rightRank: defenseStats?.adjustedExplosivenessDefenseRank,
      totalTeams: totalStatted,
      premium: true,
    },
  ];
}
