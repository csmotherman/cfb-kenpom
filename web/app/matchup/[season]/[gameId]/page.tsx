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

type AccessPayload = { ultimate?: boolean };

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
};

type ComparisonGroup = {
  title: string;
  rows: ComparisonRow[];
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
  const awayFreeRows = freeComparisonRows(teamStats.away, teamStats.home, totalStatted);
  const homeFreeRows = freeComparisonRows(teamStats.home, teamStats.away, totalStatted);
  const awayPremiumGroups = premiumComparisonGroups({
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
  const homePremiumGroups = premiumComparisonGroups({
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
        <section className="matchup-v2-hero">
          <div className="matchup-v2-hero__meta">
            <span className="eyebrow">{season} · {weekName}</span>
            <span>{gameTime(game)}{game.venue ? ` · ${game.venue}` : ""}</span>
          </div>
          <div className="matchup-v2-hero__matchup">
            <HeroTeam game={game} side="away" rating={ratings.away} />
            <span className="matchup-v2-hero__separator">{separator}</span>
            <HeroTeam game={game} side="home" rating={ratings.home} />
          </div>
          <p className="matchup-v2-hero__note">
            {ratingWeek === null
              ? "No pregame GRID snapshot exists before the opening week, so advanced comparison values are not available yet."
              : `Pregame snapshot through Week ${ratingWeek}. Nothing on this page uses results from this game week.`}
          </p>
        </section>

        <section aria-labelledby="matchupBreakdownTitle">
          <div className="matchup-v2-heading">
            <div>
              <span className="eyebrow">Matchup Breakdown</span>
              <h2 id="matchupBreakdownTitle">How the teams line up</h2>
            </div>
            <span>Value · national rank</span>
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
                freeRows={awayFreeRows}
                premiumGroups={awayPremiumGroups}
                accessResolved={accessResolved}
                ultimateAccess={ultimateAccess}
                advancedLoading={advancedLoading}
              />

              <ComparisonTable
                offense={{ team: game.homeTeam, teamId: game.homeTeamId }}
                defense={{ team: game.awayTeam, teamId: game.awayTeamId }}
                freeRows={homeFreeRows}
                premiumGroups={homePremiumGroups}
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
        </section>

        <section className="matchup-v2-footer-note">
          <p>
            Free matchup data stays useful on purpose: overall team quality plus raw efficiency and style indicators. Ultimate adds the opponent-adjusted EPA, success-rate and situational splits that explain where the matchup advantage is actually coming from.
          </p>
          <Link href="/this-week" className="utility-link">Back to the full slate →</Link>
        </section>
      </main>

      <SiteFooter note="Matchup pages use the most recent GRID snapshot strictly before the selected game week. Defensive EPA and success values are allowed values, so lower is better. Ultimate matchup access is currently tied to active or trialing GRID Pro+ access." />
    </>
  );
}

function HeroTeam({ game, side, rating }: { game: ScheduleGame; side: "away" | "home"; rating?: RankingsRow }) {
  const team = side === "away" ? game.awayTeam : game.homeTeam;
  const teamId = side === "away" ? game.awayTeamId : game.homeTeamId;
  const slug = side === "away" ? game.awaySlug : game.homeSlug;
  return (
    <Link
      href={`/team/${encodeURIComponent(slug)}`}
      className={`matchup-v2-hero-team${side === "home" ? " matchup-v2-hero-team--home" : ""}`}
      prefetch={false}
    >
      <img src={logoUrl(teamId, 192)} alt="" decoding="async" />
      <span className="matchup-v2-hero-team__copy">
        <small>{rating?.rank ? `#${rating.rank} GRID` : "GRID"}</small>
        <strong>{team}</strong>
        <em>{rating?.record || "—"}</em>
      </span>
    </Link>
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
      <div className="matchup-v2-side__group-title">Team snapshot</div>
      {rows.map((row, index) => (
        <div className="matchup-v2-side-row" key={index}>
          <span className="matchup-v2-side-row__label">{row.label}</span>
          <StatCell value={row.value} rank={row.rank} totalTeams={row.totalTeams} />
        </div>
      ))}
      <Link href={`/team/${encodeURIComponent(slug)}`} className="matchup-v2-side__link" prefetch={false}>
        View full team profile →
      </Link>
    </aside>
  );
}

function ComparisonTable({
  offense,
  defense,
  freeRows,
  premiumGroups,
  accessResolved,
  ultimateAccess,
  advancedLoading,
}: {
  offense: { team: string; teamId: number };
  defense: { team: string; teamId: number };
  freeRows: ComparisonRow[];
  premiumGroups: ComparisonGroup[];
  accessResolved: boolean;
  ultimateAccess: boolean;
  advancedLoading: boolean;
}) {
  return (
    <section className="matchup-v2-comparison" aria-label={`${offense.team} offense versus ${defense.team} defense`}>
      <div className="matchup-v2-comparison__head">
        <ComparisonTeam team={offense.team} teamId={offense.teamId} label="Offense" />
        <span className="matchup-v2-comparison__vs">vs</span>
        <ComparisonTeam team={defense.team} teamId={defense.teamId} label="Defense" defense />
      </div>

      <div className="matchup-v2-table-head" aria-hidden="true">
        <span>{offense.team} Off</span>
        <span>Metric</span>
        <span>{defense.team} Def</span>
      </div>

      <div className="matchup-v2-section-label">Free baseline</div>
      {freeRows.map((row, index) => <ComparisonMetricRow row={row} key={`free-${index}`} />)}

      {!accessResolved ? (
        <div className="matchup-v2-access-loading">Checking Ultimate access…</div>
      ) : ultimateAccess ? (
        advancedLoading ? (
          <div className="matchup-v2-access-loading">Loading opponent-adjusted matchup splits…</div>
        ) : (
          <PremiumGroups groups={premiumGroups} />
        )
      ) : (
        <LockedPremiumGroups groups={premiumGroups} />
      )}
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

function ComparisonMetricRow({ row, locked = false }: { row: ComparisonRow; locked?: boolean }) {
  return (
    <div className="matchup-v2-table-row">
      <StatCell
        value={locked ? "+0.000" : row.leftValue}
        rank={locked ? 42 : row.leftRank}
        totalTeams={locked ? 134 : row.totalTeams}
      />
      <div className="matchup-v2-table-row__metric">{row.label}</div>
      <StatCell
        value={locked ? "-0.000" : row.rightValue}
        rank={locked ? 42 : row.rightRank}
        totalTeams={locked ? 134 : row.totalTeams}
      />
    </div>
  );
}

function PremiumGroups({ groups }: { groups: ComparisonGroup[] }) {
  return (
    <div className="matchup-v2-ultimate">
      {groups.map((group) => (
        <div key={group.title}>
          <div className="matchup-v2-section-label">
            <span>{group.title}</span>
            <span className="matchup-v2-ultimate__badge">Ultimate</span>
          </div>
          {group.rows.map((row, index) => <ComparisonMetricRow row={row} key={`${group.title}-${index}`} />)}
        </div>
      ))}
    </div>
  );
}

function LockedPremiumGroups({ groups }: { groups: ComparisonGroup[] }) {
  return (
    <div className="matchup-v2-ultimate matchup-v2-ultimate--locked matchup-v2-lock">
      <div className="matchup-v2-lock__rows" aria-hidden="true">
        {groups.map((group) => (
          <div key={group.title}>
            <div className="matchup-v2-section-label">
              <span>{group.title}</span>
              <span className="matchup-v2-ultimate__badge">Ultimate</span>
            </div>
            {group.rows.map((row, index) => <ComparisonMetricRow row={row} locked key={`${group.title}-${index}`} />)}
          </div>
        ))}
      </div>
      <div className="matchup-v2-lock__cta">
        <strong>Unlock the full matchup</strong>
        <p>See opponent-adjusted EPA, success rate, down splits and contextual matchup edges.</p>
        <Link href="/upgrade?feature=matchup&plan=pro_plus">Get Ultimate access</Link>
      </div>
    </div>
  );
}

function StatCell({ value, rank, totalTeams }: { value: string; rank?: number | null; totalTeams: number }) {
  const band = tier(rank, totalTeams);
  return (
    <span className={`matchup-v2-stat${band ? ` matchup-v2-stat--${band}` : ""}`}>
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
    { label: "GRID rating", value: signed(rating?.adjEM, 1), rank: rating?.rank, totalTeams: totalRated },
    { label: "Offense", value: signed(rating?.adjO, 2), rank: rating?.adjORank, totalTeams: totalRated },
    { label: "Defense", value: signed(rating?.adjD, 2), rank: rating?.adjDRank, totalTeams: totalRated },
    { label: "Strength of schedule", value: signed(rating?.sos, 1), rank: rating?.sosRank, totalTeams: totalRated },
    { label: "Strength of record", value: signed(rating?.sor, 1), rank: rating?.sorRank, totalTeams: totalRated },
    { label: "Yards / play", value: plain(stats?.yardsPerPlay, 2), rank: stats?.yardsPerPlayRank, totalTeams: totalStatted },
    { label: "Success rate", value: pct(stats?.successRate), rank: stats?.successRateRank, totalTeams: totalStatted },
  ];
}

function freeComparisonRows(offense: TeamStatsRow | undefined, defense: TeamStatsRow | undefined, totalTeams: number): ComparisonRow[] {
  return [
    {
      label: <>Yards / play<TipTrigger text="Raw pregame yards per play. Defense is yards per play allowed, so lower is better on the defensive side." /></>,
      leftValue: plain(offense?.yardsPerPlay, 2), leftRank: offense?.yardsPerPlayRank,
      rightValue: plain(defense?.yardsPerPlayAllowed, 2), rightRank: defense?.yardsPerPlayAllowedRank,
      totalTeams,
    },
    {
      label: <>Success rate<TipTrigger text="Raw pregame success rate. Defense is opponent success rate allowed, so lower is better on the defensive side." /></>,
      leftValue: pct(offense?.successRate), leftRank: offense?.successRateRank,
      rightValue: pct(defense?.successRateAllowed), rightRank: defense?.successRateAllowedRank,
      totalTeams,
    },
    {
      label: "Pass success",
      leftValue: pct(offense?.passSuccessRate), leftRank: offense?.passSuccessRateRank,
      rightValue: pct(defense?.passSuccessRateAllowed), rightRank: defense?.passSuccessRateAllowedRank,
      totalTeams,
    },
    {
      label: "Rush success",
      leftValue: pct(offense?.rushSuccessRate), leftRank: offense?.rushSuccessRateRank,
      rightValue: pct(defense?.rushSuccessRateAllowed), rightRank: defense?.rushSuccessRateAllowedRank,
      totalTeams,
    },
    {
      label: "Explosive play %",
      leftValue: pct(offense?.explosivePlayRate), leftRank: offense?.explosivePlayRateRank,
      rightValue: pct(defense?.explosivePlayRateAllowed), rightRank: defense?.explosivePlayRateAllowedRank,
      totalTeams,
    },
    {
      label: <>Finishing drives<TipTrigger text="Points generated per resolved scoring opportunity on offense versus points allowed per opponent opportunity on defense." /></>,
      leftValue: plain(offense?.finishingRate, 1), leftRank: offense?.finishingRateRank,
      rightValue: plain(defense?.finishingRateAllowed, 1), rightRank: defense?.finishingRateAllowedRank,
      totalTeams,
    },
    {
      label: <>Havoc<TipTrigger text="Offense shows the rate of plays that surrender a TFL, sack or turnover; defense shows the rate forced." /></>,
      leftValue: pct(offense?.havocRateAllowed), leftRank: offense?.havocRateAllowedRank,
      rightValue: pct(defense?.havocRateForced), rightRank: defense?.havocRateForcedRank,
      totalTeams,
    },
  ];
}

function premiumComparisonGroups({
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
  offense: AdvancedRow | undefined;
  defense: AdvancedRow | undefined;
  offenseStats: TeamStatsRow | undefined;
  defenseStats: TeamStatsRow | undefined;
  advancedRows: AdvancedRow[];
  offenseSlug: string;
  defenseSlug: string;
  totalAdvanced: number;
  totalStatted: number;
}): ComparisonGroup[] {
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
  });

  return [
    {
      title: "Adjusted efficiency",
      rows: [
        advRow(<>EPA / play<TipTrigger text="Opponent-adjusted EPA per play. Higher is better on offense; lower EPA allowed is better on defense." /></>, "epaAdj", "epaAdjAllowed"),
        advRow("EPA / pass", "passEpaAdj", "passEpaAdjAllowed"),
        advRow("EPA / rush", "rushEpaAdj", "rushEpaAdjAllowed"),
        advRow(<>Success edge<TipTrigger text="Opponent-adjusted success-rate edge relative to expectation. Higher is better on offense; lower allowed is better on defense." /></>, "successAdj", "successAdjAllowed"),
        advRow("Pass success edge", "passSuccessAdj", "passSuccessAdjAllowed"),
        advRow("Rush success edge", "rushSuccessAdj", "rushSuccessAdjAllowed"),
      ],
    },
    {
      title: "Passing by down",
      rows: [
        advRow("1st down EPA", "passEpaDown1Adj", "passEpaDown1AdjAllowed"),
        advRow("2nd down EPA", "passEpaDown2Adj", "passEpaDown2AdjAllowed"),
        advRow("3rd down EPA", "passEpaDown3Adj", "passEpaDown3AdjAllowed"),
        advRow("1st down success", "passSuccessDown1Adj", "passSuccessDown1AdjAllowed"),
        advRow("2nd down success", "passSuccessDown2Adj", "passSuccessDown2AdjAllowed"),
        advRow("3rd down success", "passSuccessDown3Adj", "passSuccessDown3AdjAllowed"),
      ],
    },
    {
      title: "Rushing by down",
      rows: [
        advRow("1st down EPA", "rushEpaDown1Adj", "rushEpaDown1AdjAllowed"),
        advRow("2nd down EPA", "rushEpaDown2Adj", "rushEpaDown2AdjAllowed"),
        advRow("3rd down EPA", "rushEpaDown3Adj", "rushEpaDown3AdjAllowed"),
        advRow("1st down success", "rushSuccessDown1Adj", "rushSuccessDown1AdjAllowed"),
        advRow("2nd down success", "rushSuccessDown2Adj", "rushSuccessDown2AdjAllowed"),
        advRow("3rd down success", "rushSuccessDown3Adj", "rushSuccessDown3AdjAllowed"),
      ],
    },
    {
      title: "Matchup profile",
      rows: [
        {
          label: <>Explosiveness adj.<TipTrigger text="Opponent-adjusted explosiveness. The defensive value is framed as suppression relative to expectation, so its stored rank is already direction-normalized." /></>,
          leftValue: signed(offenseStats?.adjustedExplosivenessOffense, 2), leftRank: offenseStats?.adjustedExplosivenessOffenseRank,
          rightValue: signed(defenseStats?.adjustedExplosivenessDefense, 2), rightRank: defenseStats?.adjustedExplosivenessDefenseRank,
          totalTeams: totalStatted,
        },
        {
          label: "Finishing adj.",
          leftValue: signed(offenseStats?.adjustedFinishingOffense, 2), leftRank: offenseStats?.adjustedFinishingOffenseRank,
          rightValue: signed(defenseStats?.adjustedFinishingDefense, 2), rightRank: defenseStats?.adjustedFinishingDefenseRank,
          totalTeams: totalStatted,
        },
        {
          label: "Havoc adj.",
          leftValue: signed(offenseStats?.adjustedHavocOffense, 3), leftRank: offenseStats?.adjustedHavocOffenseRank,
          rightValue: signed(defenseStats?.adjustedHavocDefense, 3), rightRank: defenseStats?.adjustedHavocDefenseRank,
          totalTeams: totalStatted,
        },
      ],
    },
  ];
}
