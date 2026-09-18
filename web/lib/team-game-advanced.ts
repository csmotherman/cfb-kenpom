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

function firstNum(row: TeamGameAdvancedRow | undefined, keys: string[]): number | null {
  for (const key of keys) {
    const value = num(row, key);
    if (value !== null) return value;
  }
  return null;
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

function ratioLine(
  row: TeamGameAdvancedRow | undefined,
  madeKey: string,
  attemptKey: string,
  rateKey: string,
): string {
  const made = num(row, madeKey);
  const attempts = num(row, attemptKey);
  const rate = num(row, rateKey);
  if (made === null || attempts === null) return "—";
  return String(Math.round(made)) + "/" + String(Math.round(attempts)) +
    (rate === null ? "" : " (" + pct(rate) + ")");
}

function completionLine(row: TeamGameAdvancedRow | undefined): string {
  const completions = num(row, "box_completions");
  const attempts = num(row, "box_pass_attempts");
  if (completions === null || attempts === null) return "—";
  return String(Math.round(completions)) + "/" + String(Math.round(attempts));
}

function penaltyLine(row: TeamGameAdvancedRow | undefined): string {
  const penalties = num(row, "box_penalties");
  const yards = num(row, "box_penalty_yards");
  if (penalties === null || yards === null) return "—";
  return String(Math.round(penalties)) + "-" + String(Math.round(yards));
}

function possessionLine(row: TeamGameAdvancedRow | undefined): string {
  const seconds = num(row, "box_possession_seconds");
  const share = num(row, "box_possession_share");
  if (seconds === null) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  const clock = String(minutes) + ":" + String(remainder).padStart(2, "0");
  return share === null ? clock : clock + " (" + pct(share) + ")";
}

type Fmt = (v: number | null) => string;

type Spec = {
  label: string;
  key: string;
  fallbackKeys?: string[];
  baselineKey?: string;
  fmt: Fmt;
  display?: (row: TeamGameAdvancedRow | undefined) => string;
  neutral?: boolean;
  indent?: 0 | 1;
};

function datum(row: TeamGameAdvancedRow | undefined, spec: Spec): StatValue {
  const v = firstNum(row, [spec.key, ...(spec.fallbackKeys || [])]);
  const value = spec.display ? spec.display(row) : spec.fmt(v);
  if (spec.neutral) return { value, neutral: true };
  return {
    value,
    percentile: historicalGamePercentileBand(spec.baselineKey || spec.key, v),
  };
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

// Completed-game results have a hard source boundary:
// - BOX_SCORE uses CFBD /games/teams and is descriptive/neutral.
// - EFFICIENCY and GAME_SHAPE use LEILA's PBP/drive analytics and historical
//   single-game percentile coloring.
// Never fill an official box-score row with a similarly named LEILA metric.
const BOX_SCORE: [string, Spec[]][] = [
  ["Overall", [
    { label: "Plays", key: "box_total_plays", fmt: count, neutral: true },
    { label: "Total Yards", key: "box_total_yards", fmt: count, neutral: true },
    { label: "Yards / Play", key: "box_yards_per_play", fmt: (v) => plain(v, 1), neutral: true },
    { label: "First Downs", key: "box_first_downs", fmt: count, neutral: true },
  ]],
  ["Passing", [
    { label: "Comp / Att", key: "box_pass_attempts", fmt: count, display: completionLine, neutral: true },
    { label: "Net Pass Yards", key: "box_net_pass_yards", fmt: count, neutral: true, indent: 1 },
    { label: "Yards / Attempt", key: "box_yards_per_pass_attempt", fmt: (v) => plain(v, 1), neutral: true, indent: 1 },
  ]],
  ["Rushing", [
    { label: "Rush Attempts", key: "box_rush_attempts", fmt: count, neutral: true },
    { label: "Rush Yards", key: "box_rush_yards", fmt: count, neutral: true, indent: 1 },
    { label: "Yards / Carry", key: "box_yards_per_rush_attempt", fmt: (v) => plain(v, 1), neutral: true, indent: 1 },
  ]],
  ["Situational", [
    {
      label: "3rd Down",
      key: "box_third_down_rate",
      fmt: pct,
      display: (row) => ratioLine(row, "box_third_down_conversions", "box_third_down_attempts", "box_third_down_rate"),
      neutral: true,
    },
    {
      label: "4th Down",
      key: "box_fourth_down_rate",
      fmt: pct,
      display: (row) => ratioLine(row, "box_fourth_down_conversions", "box_fourth_down_attempts", "box_fourth_down_rate"),
      neutral: true,
    },
    { label: "Penalties", key: "box_penalties", fmt: count, display: penaltyLine, neutral: true },
    { label: "Turnovers", key: "box_turnovers", fmt: count, neutral: true },
    { label: "Interceptions", key: "box_interceptions", fmt: count, neutral: true, indent: 1 },
    { label: "Fumbles Lost", key: "box_fumbles_lost", fmt: count, neutral: true, indent: 1 },
    { label: "Possession", key: "box_possession_seconds", fmt: count, display: possessionLine, neutral: true },
  ]],
];

const EFFICIENCY: [string, Spec[]][] = [
  ["Overall", [
    { label: "EPA / Play", key: "epa_per_play", fmt: (v) => signed(v, 3) },
    { label: "Total EPA", key: "total_epa", fmt: (v) => signed(v, 1) },
    { label: "Success Rate", key: "success_rate", fmt: pct },
  ]],
  ["Passing", [
    { label: "Passing EPA", key: "passing_epa", fmt: (v) => signed(v, 1) },
    { label: "EPA / Dropback", key: "epa_per_dropback", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Success Rate", key: "pass_success_rate", fmt: pct, indent: 1 },
  ]],
  ["Rushing", [
    { label: "Rushing EPA", key: "rushing_epa", fmt: (v) => signed(v, 1) },
    { label: "EPA / Rush", key: "epa_per_rush", fmt: (v) => signed(v, 2), indent: 1 },
    { label: "Success Rate", key: "rush_success_rate", fmt: pct, indent: 1 },
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

const GAME_SHAPE: [string, Spec[]][] = [
  ["Drives", [
    { label: "Validated Offensive Drives", key: "offensive_drives", fmt: count, neutral: true },
    { label: "Yards / Drive", key: "yards_per_drive", fmt: (v) => plain(v, 1) },
    { label: "Avg Starting Field Position", key: "avg_start_yards_to_goal", fmt: fieldPosition, neutral: true },
    { label: "Scoring Opportunities", key: "scoring_opportunities", fmt: count, neutral: true },
    { label: "Points / Opportunity", key: "points_per_opportunity", fmt: (v) => plain(v, 2), indent: 1 },
    { label: "Drive Share", key: "drive_share", fmt: pct, neutral: true },
  ]],
  ["Series Control", [
    { label: "Series Conversion", key: "series_conversion_rate", fmt: pct },
    { label: "Recovery Rate", key: "recovery_rate", fmt: pct, indent: 1 },
    { label: "3rd & Long Exposure", key: "third_long_exposure", fmt: pct, indent: 1 },
  ]],
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
  ["Turnover Impact", [
    { label: "Turnover EPA Lost", key: "turnover_epa_lost", fmt: (v) => plain(v, 1) },
  ]],
];

export function buildGameResultsColumns(
  leftRow: TeamGameAdvancedRow | undefined,
  rightRow: TeamGameAdvancedRow | undefined,
  _seasonRows?: TeamGameAdvancedRow[],
): { title: string; sections: StatSection[] }[] {
  const column = (title: string, groups: [string, Spec[]][]) => ({
    title,
    sections: groups.map(([sectionTitle, specs]) => buildSection(sectionTitle, specs, leftRow, rightRow)),
  });
  const hasOfficialBoxScore =
    leftRow?.box_score_available === true || rightRow?.box_score_available === true;

  return [
    ...(hasOfficialBoxScore ? [column("Official Box Score", BOX_SCORE)] : []),
    column("LEILA Efficiency", EFFICIENCY),
    column("Game Shape", GAME_SHAPE),
  ];
}
