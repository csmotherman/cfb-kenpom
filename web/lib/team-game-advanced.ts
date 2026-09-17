import type { StatSection, StatValue } from "@/components/GameResultsSheet";
import {
  TEAM_GAME_PERCENTILE_BASELINE,
  type TeamGamePercentileBaselineKey,
  type TeamGamePercentileBaselineMetric,
} from "./team-game-percentile-baseline";
import type { TeamGameAdvancedRow } from "./types";

function num(row: TeamGameAdvancedRow | undefined, key: string): number | null {
  if (!row) return null;
  const v = row[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * Return a representative percentile inside the historical color band for a
 * single-game metric. We intentionally ship only p10/p30/p70/p90 cut points,
 * not the full historical corpus, because the UI only needs the five
 * conditional-formatting bands.
 */
export function historicalGamePercentileBand(key: string, value: number | null): number | undefined {
  if (value === null) return undefined;
  const metric = TEAM_GAME_PERCENTILE_BASELINE.metrics[
    key as TeamGamePercentileBaselineKey
  ] as TeamGamePercentileBaselineMetric | undefined;
  if (!metric) return undefined;

  if (metric.lowerBetter) {
    if (value <= metric.p10) return 95;
    if (value <= metric.p30) return 80;
    if (value >= metric.p90) return 5;
    if (value >= metric.p70) return 20;
    return 50;
  }

  if (value >= metric.p90) return 95;
  if (value >= metric.p70) return 80;
  if (value <= metric.p10) return 5;
  if (value <= metric.p30) return 20;
  return 50;
}

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function signed(v: number | null, digits = 2): string {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}`;
}

function plain(v: number | null, digits = 1): string {
  return v === null ? "—" : v.toFixed(digits);
}

function count(v: number | null): string {
  return v === null ? "—" : String(Math.round(v));
}

function fieldPosition(yardsToGoal: number | null): string {
  if (yardsToGoal === null) return "—";
  return yardsToGoal > 50 ? `Own ${Math.round(100 - yardsToGoal)}` : `Opp ${Math.round(yardsToGoal)}`;
}

type Fmt = (v: number | null) => string;

type Spec = {
  label: string;
  key: string;
  fmt: Fmt;
  neutral?: boolean;
  indent?: 0 | 1;
};

function datum(row: TeamGameAdvancedRow | undefined, spec: Spec): StatValue {
  const v = num(row, spec.key);
  if (spec.neutral) return { value: spec.fmt(v), neutral: true };
  return { value: spec.fmt(v), percentile: historicalGamePercentileBand(spec.key, v) };
}

function buildSection(
  title: string,
  specs: Spec[],
  leftRow: TeamGameAdvancedRow | undefined,
  rightRow: TeamGameAdvancedRow | undefined,
): StatSection {
  return {
    title,
    rows: specs.map((spec) => ({
      label: spec.label,
      indent: spec.indent,
      left: datum(leftRow, spec),
      right: datum(rightRow, spec),
    })),
  };
}

const EFFICIENCY: [string, Spec[]][] = [
  ["Overall", [
    { label: "Plays", key: "offensive_plays", fmt: count, neutral: true },
    { label: "EPA / Play", key: "epa_per_play", fmt: (v) => signed(v, 3) },
    { label: "Success Rate", key: "success_rate", fmt: pct },
    { label: "Yards / Play", key: "yards_per_play", fmt: (v) => plain(v, 1) },
    { label: "Total EPA", key: "total_epa", fmt: (v) => signed(v, 1) },
  ]],
  ["Passing", [
    { label: "Dropbacks", key: "dropbacks", fmt: count, neutral: true },
    { label: "Pass Rate", key: "pass_rate", fmt: pct, neutral: true, indent: 1 },
    { label: "Passing EPA", key: "passing_epa", fmt: (v) => signed(v, 1), indent: 1 },
    { label: "EPA / Dropback", key: "epa_per_dropback", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Success Rate", key: "pass_success_rate", fmt: pct, indent: 1 },
    { label: "Yards / Dropback", key: "yards_per_dropback", fmt: (v) => plain(v, 1), indent: 1 },
  ]],
  ["Rushing", [
    { label: "Rushes", key: "rush_attempts", fmt: count, neutral: true },
    { label: "Rush Rate", key: "rush_rate", fmt: pct, neutral: true, indent: 1 },
    { label: "Rushing EPA", key: "rushing_epa", fmt: (v) => signed(v, 1), indent: 1 },
    { label: "EPA / Rush", key: "epa_per_rush", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Success Rate", key: "rush_success_rate", fmt: pct, indent: 1 },
    { label: "Yards / Rush", key: "yards_per_rush", fmt: (v) => plain(v, 1), indent: 1 },
  ]],
  ["By Down", [
    { label: "1st Down EPA / Play", key: "down1_epa", fmt: (v) => signed(v, 2) },
    { label: "Pass EPA / Play", key: "down1_epa_pass", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Rush EPA / Play", key: "down1_epa_rush", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "2nd Down EPA / Play", key: "down2_epa", fmt: (v) => signed(v, 2) },
    { label: "Pass EPA / Play", key: "down2_epa_pass", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Rush EPA / Play", key: "down2_epa_rush", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "3rd Down EPA / Play", key: "down3_epa", fmt: (v) => signed(v, 2) },
    { label: "Pass EPA / Play", key: "down3_epa_pass", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Rush EPA / Play", key: "down3_epa_rush", fmt: (v) => signed(v, 2), indent: 1 },
  ]],
];

const CONTROL: [string, Spec[]][] = [
  ["Drives", [
    { label: "Drives", key: "offensive_drives", fmt: count, neutral: true },
    { label: "Points / Drive", key: "points_per_drive", fmt: (v) => plain(v, 2) },
    { label: "Yards / Drive", key: "yards_per_drive", fmt: (v) => plain(v, 1) },
    { label: "Plays / Drive", key: "plays_per_drive", fmt: (v) => plain(v, 1) },
    { label: "Avg Starting Field Position", key: "avg_start_yards_to_goal", fmt: fieldPosition, neutral: true },
    { label: "Scoring Opportunities", key: "scoring_opportunities", fmt: count, neutral: true },
    { label: "Points / Opportunity", key: "points_per_opportunity", fmt: (v) => plain(v, 2), indent: 1 },
    { label: "Possession Share", key: "possession_share", fmt: pct, neutral: true },
  ]],
  ["Series Control", [
    { label: "Series Conversion", key: "series_conversion_rate", fmt: pct },
    { label: "Recovery Rate", key: "recovery_rate", fmt: pct, indent: 1 },
    { label: "3rd & Long Exposure", key: "third_long_exposure", fmt: pct, indent: 1 },
  ]],
  ["Situational", [
    { label: "3rd Down Conversion", key: "series_conversion_rate", fmt: pct },
    { label: "4th Down", key: "fourth_down_rate", fmt: pct },
    { label: "Scoring Opp. TD Rate", key: "scoring_opportunity_touchdown_rate", fmt: pct },
  ]],
];

const SHAPE: [string, Spec[]][] = [
  ["Explosiveness", [
    { label: "Explosive Play Rate", key: "explosive_play_rate", fmt: pct },
    { label: "Explosive Pass Rate", key: "explosive_pass_rate", fmt: pct, indent: 1 },
    { label: "Explosive Rush Rate", key: "explosive_rush_rate", fmt: pct, indent: 1 },
    { label: "EPA / Play w/o Explosives", key: "epa_without_explosives", fmt: (v) => signed(v, 2) },
    { label: "Explosive Dependency", key: "explosive_dependency", fmt: pct, neutral: true },
  ]],
  ["Possession Quality", [
    { label: "Clean Drive Rate", key: "clean_drive_rate", fmt: pct },
    { label: "Drive Killer Rate", key: "drive_killer_rate", fmt: pct },
    { label: "Failure Rate", key: "failure_rate", fmt: pct, indent: 1 },
    { label: "Avg Failure Damage", key: "avg_failure_damage", fmt: (v) => plain(v, 2), indent: 1 },
    { label: "Failure Burden", key: "failure_burden", fmt: (v) => plain(v, 3), indent: 1 },
    { label: "Failure Pressure", key: "failure_pressure", fmt: (v) => plain(v, 3), indent: 1 },
  ]],
  ["Disruption", [
    { label: "Havoc Allowed", key: "havoc_allowed", fmt: pct },
    { label: "Sacks Taken", key: "sacks_taken", fmt: count, neutral: true, indent: 1 },
    { label: "TFLs Taken", key: "tfls_taken", fmt: count, neutral: true, indent: 1 },
  ]],
  ["Turnovers", [
    { label: "Turnovers Lost", key: "turnovers_lost", fmt: count, neutral: true },
    { label: "Interceptions", key: "interceptions_thrown", fmt: count, neutral: true, indent: 1 },
    { label: "Fumbles Lost", key: "fumbles_lost", fmt: count, neutral: true, indent: 1 },
    { label: "Turnover Rate", key: "turnover_rate", fmt: pct, indent: 1 },
    { label: "Turnover EPA Lost", key: "turnover_epa_lost", fmt: (v) => plain(v, 1), indent: 1 },
  ]],
  ["Penalties", [
    { label: "Penalties", key: "penalties", fmt: count, neutral: true },
    { label: "Penalty Yards", key: "penalty_yards", fmt: count, neutral: true, indent: 1 },
    { label: "Penalty Rate", key: "penalty_rate", fmt: pct, indent: 1 },
    { label: "Penalty Yards / Drive", key: "penalty_yards_per_drive", fmt: (v) => plain(v, 1), indent: 1 },
  ]],
];

export function buildGameResultsColumns(
  leftRow: TeamGameAdvancedRow | undefined,
  rightRow: TeamGameAdvancedRow | undefined,
): { title: string; sections: StatSection[] }[] {
  const column = (title: string, groups: [string, Spec[]][]) => ({
    title,
    sections: groups.map(([sectionTitle, specs]) => buildSection(sectionTitle, specs, leftRow, rightRow)),
  });
  return [
    column("Efficiency", EFFICIENCY),
    column("Control & Situations", CONTROL),
    column("Game Shape", SHAPE),
  ];
}
