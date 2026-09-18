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
  tip: string;
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
      tip: spec.tip,
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
    { label: "Plays", key: "box_total_plays", fmt: count, neutral: true, tip: "Official offensive plays from CFBD's team box score (rush attempts plus pass attempts). Not colored -- it's a game fact, not a LEILA rating." },
    { label: "Total Yards", key: "box_total_yards", fmt: count, neutral: true, tip: "Official total offensive yards from CFBD's team box score." },
    { label: "Yards / Play", key: "box_yards_per_play", fmt: (v) => plain(v, 1), neutral: true, tip: "Official total yards divided by official plays. Higher is generally better, but this row is descriptive and not conditionally colored." },
    { label: "First Downs", key: "box_first_downs", fmt: count, neutral: true, tip: "Official first downs from CFBD's team box score." },
  ]],
  ["Passing", [
    { label: "Comp / Att", key: "box_pass_attempts", fmt: count, display: completionLine, neutral: true, tip: "Official completions and pass attempts from CFBD's team box score." },
    { label: "Net Pass Yards", key: "box_net_pass_yards", fmt: count, neutral: true, indent: 1, tip: "Official net passing yards (sack yardage already removed) from CFBD's team box score." },
    { label: "Yards / Attempt", key: "box_yards_per_pass_attempt", fmt: (v) => plain(v, 1), neutral: true, indent: 1, tip: "Official net passing yards divided by official pass attempts." },
  ]],
  ["Rushing", [
    { label: "Rush Attempts", key: "box_rush_attempts", fmt: count, neutral: true, tip: "Official rush attempts from CFBD's team box score." },
    { label: "Rush Yards", key: "box_rush_yards", fmt: count, neutral: true, indent: 1, tip: "Official rushing yards from CFBD's team box score." },
    { label: "Yards / Carry", key: "box_yards_per_rush_attempt", fmt: (v) => plain(v, 1), neutral: true, indent: 1, tip: "Official rushing yards divided by official rush attempts." },
  ]],
  ["Situational", [
    {
      label: "3rd Down",
      key: "box_third_down_rate",
      fmt: pct,
      display: (row) => ratioLine(row, "box_third_down_conversions", "box_third_down_attempts", "box_third_down_rate"),
      neutral: true,
      tip: "Official 3rd-down conversions over 3rd-down attempts from CFBD's team box score. This is the official rate, not LEILA's own play-level 3rd-down success metric.",
    },
    {
      label: "4th Down",
      key: "box_fourth_down_rate",
      fmt: pct,
      display: (row) => ratioLine(row, "box_fourth_down_conversions", "box_fourth_down_attempts", "box_fourth_down_rate"),
      neutral: true,
      tip: "Official 4th-down conversions over 4th-down attempts from CFBD's team box score.",
    },
    { label: "Penalties", key: "box_penalties", fmt: count, display: penaltyLine, neutral: true, tip: "Official penalties and penalty yardage from CFBD's team box score. Shown as count-yards." },
    { label: "Turnovers", key: "box_turnovers", fmt: count, neutral: true, tip: "Official turnovers lost (interceptions plus lost fumbles) from CFBD's team box score." },
    { label: "Interceptions", key: "box_interceptions", fmt: count, neutral: true, indent: 1, tip: "Official interceptions thrown, from CFBD's team box score." },
    { label: "Fumbles Lost", key: "box_fumbles_lost", fmt: count, neutral: true, indent: 1, tip: "Official fumbles lost to the opponent, from CFBD's team box score." },
    { label: "Possession", key: "box_possession_seconds", fmt: count, display: possessionLine, neutral: true, tip: "Official time of possession from CFBD's team box score, with each team's share of the game clock in parentheses." },
  ]],
];

const EPA_PLAY_TIP = "Expected Points Added per play, from LEILA's play-by-play model. Positive means the offense gained expected points on average; negative means it lost them. Higher is better. LEILA-derived, not an official box-score stat.";
const SUCCESS_RATE_TIP = "Share of plays that gained a positive share of the expected points needed to keep a drive on schedule (roughly 50% of yards to go on 1st down, 70% on 2nd, 100% on 3rd/4th). Higher is better. LEILA-derived.";

const EFFICIENCY: [string, Spec[]][] = [
  ["Overall", [
    { label: "EPA / Play", key: "epa_per_play", fmt: (v) => signed(v, 3), tip: EPA_PLAY_TIP },
    { label: "Total EPA", key: "total_epa", fmt: (v) => signed(v, 1), tip: "Sum of Expected Points Added across every offensive play in the game. Higher is better. LEILA-derived." },
    { label: "Success Rate", key: "success_rate", fmt: pct, tip: SUCCESS_RATE_TIP },
  ]],
  ["Passing", [
    { label: "Passing EPA", key: "passing_epa", fmt: (v) => signed(v, 1), tip: "Sum of Expected Points Added on dropbacks (pass attempts plus sacks). Higher is better. LEILA-derived." },
    { label: "EPA / Dropback", key: "epa_per_dropback", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to dropbacks." },
    { label: "Success Rate", key: "pass_success_rate", fmt: pct, indent: 1, tip: SUCCESS_RATE_TIP + " Limited to dropbacks." },
  ]],
  ["Rushing", [
    { label: "Rushing EPA", key: "rushing_epa", fmt: (v) => signed(v, 1), tip: "Sum of Expected Points Added on rush attempts. Higher is better. LEILA-derived." },
    { label: "EPA / Rush", key: "epa_per_rush", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to rush attempts." },
    { label: "Success Rate", key: "rush_success_rate", fmt: pct, indent: 1, tip: SUCCESS_RATE_TIP + " Limited to rush attempts." },
  ]],
  ["By Down", [
    { label: "1st Down EPA / Play", key: "down1_epa", fmt: (v) => signed(v, 2), tip: EPA_PLAY_TIP + " Limited to 1st-down plays (pass and rush combined)." },
    { label: "Pass EPA / Play", key: "down1_epa_pass", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to 1st-down dropbacks." },
    { label: "Rush EPA / Play", key: "down1_epa_rush", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to 1st-down rush attempts." },
    { label: "2nd Down EPA / Play", key: "down2_epa", fmt: (v) => signed(v, 2), tip: EPA_PLAY_TIP + " Limited to 2nd-down plays (pass and rush combined)." },
    { label: "Pass EPA / Play", key: "down2_epa_pass", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to 2nd-down dropbacks." },
    { label: "Rush EPA / Play", key: "down2_epa_rush", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to 2nd-down rush attempts." },
    { label: "3rd Down EPA / Play", key: "down3_epa", fmt: (v) => signed(v, 2), tip: EPA_PLAY_TIP + " Limited to 3rd-down plays (pass and rush combined)." },
    { label: "Pass EPA / Play", key: "down3_epa_pass", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to 3rd-down dropbacks." },
    { label: "Rush EPA / Play", key: "down3_epa_rush", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to 3rd-down rush attempts." },
  ]],
];

const GAME_SHAPE: [string, Spec[]][] = [
  ["Drives", [
    { label: "Validated Offensive Drives", key: "offensive_drives", fmt: count, neutral: true, tip: "Offensive possessions LEILA's drive pipeline could fully validate for this game. The denominator behind the other Drives-section rates." },
    { label: "Yards / Drive", key: "yards_per_drive", fmt: (v) => plain(v, 1), tip: "Offensive yards gained per validated drive. Higher is better. LEILA-derived." },
    { label: "Avg Starting Field Position", key: "avg_start_yards_to_goal", fmt: fieldPosition, neutral: true, tip: "Average distance to the end zone where this offense's drives began. Shown as a yard line; not conditionally colored." },
    { label: "Scoring Opportunities", key: "scoring_opportunities", fmt: count, neutral: true, tip: "Drives where LEILA's pipeline marked the offense inside the opponent's 40-yard line. The denominator for Points / Opportunity." },
    { label: "Points / Opportunity", key: "points_per_opportunity", fmt: (v) => plain(v, 2), indent: 1, tip: "Points scored per scoring opportunity (a drive reaching the opponent's 40). Higher is better -- a finishing-drives measure. LEILA-derived." },
    { label: "Drive Share", key: "drive_share", fmt: pct, neutral: true, tip: "This team's share of the game's total validated drives (both teams combined). Descriptive; not conditionally colored." },
  ]],
  ["Series Control", [
    { label: "Series Conversion", key: "series_conversion_rate", fmt: pct, tip: "Share of 1st-down series (a set of downs, not an individual play) that earned a new first down or a touchdown. Higher is better. LEILA-derived." },
    { label: "Recovery Rate", key: "recovery_rate", fmt: pct, indent: 1, tip: "Share of series that fell behind schedule (e.g. a negative or short-gain play) but still converted. Higher is better. LEILA-derived." },
    { label: "3rd & Long Exposure", key: "third_long_exposure", fmt: pct, indent: 1, tip: "Share of series that reached a 3rd (or 4th) down needing 7 or more yards. Lower is better -- it means the offense stayed ahead of schedule. LEILA-derived." },
  ]],
  ["Explosiveness", [
    { label: "Explosive Play Rate", key: "explosive_play_rate", fmt: pct, tip: "Share of offensive plays gaining 15+ yards through the air or 10+ on the ground. Higher is better. LEILA-derived." },
    { label: "Explosive Pass Rate", key: "explosive_pass_rate", fmt: pct, indent: 1, tip: "Explosive Play Rate limited to dropbacks. Higher is better. LEILA-derived." },
    { label: "Explosive Rush Rate", key: "explosive_rush_rate", fmt: pct, indent: 1, tip: "Explosive Play Rate limited to rush attempts. Higher is better. LEILA-derived." },
    { label: "EPA / Play w/o Explosives", key: "epa_without_explosives", fmt: (v) => signed(v, 2), tip: EPA_PLAY_TIP + " Explosive plays removed, to show how the offense performed on its ordinary snaps." },
    { label: "Explosive Dependency", key: "explosive_dependency", fmt: pct, neutral: true, tip: "Share of this offense's positive EPA that came from explosive plays alone. Descriptive, not conditionally colored -- a high number isn't necessarily bad, it just means the offense leaned on big plays rather than sustained drives." },
  ]],
  ["Possession Quality", [
    { label: "Clean Drive Rate", key: "clean_drive_rate", fmt: pct, tip: "Share of drives with no turnover, sack, TFL, or backward-progress accepted penalty. Higher is better. LEILA-derived." },
    { label: "Drive Killer Rate", key: "drive_killer_rate", fmt: pct, tip: "Share of drives where a negative event (turnover, sack, TFL, failed 4th down, etc.) ended the drive rather than being overcome. Lower is better. LEILA-derived." },
    { label: "Failure Rate", key: "failure_rate", fmt: pct, indent: 1, tip: "Share of offensive plays with negative EPA. Lower is better. LEILA-derived." },
    { label: "Avg Failure Damage", key: "avg_failure_damage", fmt: (v) => plain(v, 2), indent: 1, tip: "Average EPA lost on plays that had negative EPA. Lower (more negative) is worse; closer to zero is better. LEILA-derived." },
    { label: "Failure Burden", key: "failure_burden", fmt: (v) => plain(v, 3), indent: 1, tip: "Total negative EPA from failed plays spread across every eligible play this offense ran. Lower (more negative) is worse; closer to zero is better. LEILA-derived." },
    { label: "Failure Pressure", key: "failure_pressure", fmt: (v) => plain(v, 3), indent: 1, tip: "Failure Burden inflicted on the opponent's offense by this team's defense. Higher is better -- more pressure created. LEILA-derived." },
  ]],
  ["Disruption", [
    { label: "Havoc Allowed", key: "havoc_allowed", fmt: pct, tip: "Share of this offense's plays that resulted in a TFL, sack, or turnover against it. Lower is better. LEILA-derived; current-season coverage only." },
    { label: "Sacks Taken", key: "sacks_taken", fmt: count, neutral: true, indent: 1, tip: "Sacks this team's offense allowed, from LEILA's play-by-play classifier. Descriptive; not conditionally colored. Current-season coverage only." },
    { label: "TFLs Taken", key: "tfls_taken", fmt: count, neutral: true, indent: 1, tip: "Tackles for loss this team's offense allowed, from LEILA's play-by-play classifier. Descriptive; not conditionally colored." },
  ]],
  ["Turnover Impact", [
    { label: "Turnover EPA Lost", key: "turnover_epa_lost", fmt: (v) => plain(v, 1), tip: "Total Expected Points this offense's turnovers cost it, from LEILA's play-by-play model. Stored as a negative number; closer to zero (e.g. -3 vs -15) is better. LEILA-derived." },
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
    column("Official Box Score", BOX_SCORE),
    column("LEILA Efficiency", EFFICIENCY),
    column("Game Shape", GAME_SHAPE),
  ];
}
