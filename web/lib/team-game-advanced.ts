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
// - EFFICIENCY and GAME_SHAPE use PRIME's PBP/drive analytics and historical
//   single-game percentile coloring.
// Never fill an official box-score row with a similarly named PRIME metric.
const BOX_SCORE: [string, Spec[]][] = [
  ["Overall", [
    { label: "Plays", key: "box_total_plays", fmt: count, neutral: true, tip: "Official offensive plays from CFBD's team box score (rush attempts plus pass attempts). Not colored -- it's a game fact, not a PRIME rating." },
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
      tip: "Official 3rd-down conversions over 3rd-down attempts from CFBD's team box score. This is the official rate, not PRIME's own play-level 3rd-down success metric.",
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

// PRIME displays CFBD's PPA (Predicted Points Added) under the "EPA" label,
// a branding decision -- the field/key names below stay "ppa_*" (the
// export's honest internal name; see docs/cfbd_advanced_stats_migration.md
// and canonical/cfbd_advanced.py) so provenance is never ambiguous, but the
// user-facing `label` text says "EPA" per that decision. Do not claim PRIME
// independently fits an expected-points model -- every tooltip here says
// plainly that the source is CFBD's own PPA.
const EPA_PLAY_TIP = "PRIME's EPA display uses CFBD's PPA (Predicted Points Added) as its underlying play-value model -- CFBD's own play-level model output, not a model PRIME independently fits. Positive means the offense gained expected points on average; negative means it lost them. Higher is better. Sourced from CFBD's /stats/game/advanced, not an official box-score stat.";
const SUCCESS_RATE_TIP = "Share of plays that gained a positive share of the expected points needed to keep a drive on schedule (roughly 50% of yards to go on 1st down, 70% on 2nd, 100% on 3rd/4th). Higher is better. Sourced from CFBD's /stats/game/advanced.";
const PRIME_EPA_BY_DOWN_TIP = "PRIME's own aggregation of CFBD's per-play PPA (displayed as EPA -- see above), split by the exact down number. CFBD's own advanced endpoints only split by standard-down/passing-down category, not by down number, so this one slice genuinely requires PRIME's play-by-play pipeline.";

const EFFICIENCY: [string, Spec[]][] = [
  ["Overall", [
    { label: "EPA / Play", key: "ppa_per_play", baselineKey: "epa_per_play", fmt: (v) => signed(v, 3), tip: EPA_PLAY_TIP },
    { label: "Total EPA", key: "total_ppa", baselineKey: "total_epa", fmt: (v) => signed(v, 1), tip: "Sum of CFBD's PPA (displayed as EPA) across every offensive play in the game. Higher is better. CFBD-sourced." },
    { label: "Success Rate", key: "success_rate", fmt: pct, tip: SUCCESS_RATE_TIP },
  ]],
  ["Passing", [
    { label: "Passing EPA", key: "passing_total_ppa", baselineKey: "passing_epa", fmt: (v) => signed(v, 1), tip: "Sum of CFBD's PPA (displayed as EPA) on CFBD's own passing-play population for this game. Higher is better. CFBD-sourced; this population may differ slightly from PRIME's own dropback definition (which also includes sacks)." },
    { label: "EPA / Pass Play", key: "passing_ppa_per_play", baselineKey: "epa_per_dropback", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to CFBD's passing-play population." },
    { label: "Success Rate", key: "pass_success_rate", fmt: pct, indent: 1, tip: SUCCESS_RATE_TIP + " Limited to CFBD's passing-play population." },
  ]],
  ["Rushing", [
    { label: "Rushing EPA", key: "rushing_total_ppa", baselineKey: "rushing_epa", fmt: (v) => signed(v, 1), tip: "Sum of CFBD's PPA (displayed as EPA) on rush attempts. Higher is better. CFBD-sourced." },
    { label: "EPA / Rush", key: "rushing_ppa_per_play", baselineKey: "epa_per_rush", fmt: (v) => signed(v, 2), indent: 1, tip: EPA_PLAY_TIP + " Limited to rush attempts." },
    { label: "Success Rate", key: "rush_success_rate", fmt: pct, indent: 1, tip: SUCCESS_RATE_TIP + " Limited to rush attempts." },
  ]],
  ["Rushing Efficiency", [
    { label: "Stuff Rate", key: "stuff_rate", fmt: pct, neutral: true, indent: 1, tip: "Share of rush attempts stopped at or behind the line of scrimmage. Lower is better. CFBD-sourced; new field, not yet conditionally colored (no historical baseline built)." },
    { label: "Power Success", key: "power_success", fmt: pct, neutral: true, indent: 1, tip: "Conversion rate on power-run situations (short-yardage, goal-to-go). Higher is better. CFBD-sourced; new field, not yet conditionally colored." },
    { label: "Line Yards / Carry", key: "line_yards_per_play", fmt: (v) => plain(v, 2), neutral: true, indent: 1, tip: "Yards attributed to the offensive line, per carry (CFBD's lineYardsAverage -- a weighted share of the first several yards of each run, not the game total). Higher is better. CFBD-sourced; new field, not yet conditionally colored." },
    { label: "2nd-Level Yards / Carry", key: "second_level_yards_per_play", fmt: (v) => plain(v, 2), neutral: true, indent: 1, tip: "Yards gained 5-10 yards past the line of scrimmage, per carry (CFBD's secondLevelYardsAverage, not the game total). Higher is better. CFBD-sourced; new field, not yet conditionally colored." },
    { label: "Open-Field Yards / Carry", key: "open_field_yards_per_play", fmt: (v) => plain(v, 2), neutral: true, indent: 1, tip: "Yards gained beyond 10 yards past the line of scrimmage, per carry (CFBD's openFieldYardsAverage, not the game total). Higher is better. CFBD-sourced; new field, not yet conditionally colored." },
  ]],
  ["By Down (PRIME)", [
    { label: "1st Down EPA / Play", key: "down1_ppa_per_play", baselineKey: "down1_epa", fmt: (v) => signed(v, 2), tip: PRIME_EPA_BY_DOWN_TIP + " 1st-down plays (pass and rush combined)." },
    { label: "Pass EPA / Play", key: "down1_ppa_per_play_pass", baselineKey: "down1_epa_pass", fmt: (v) => signed(v, 2), indent: 1, tip: PRIME_EPA_BY_DOWN_TIP + " 1st-down dropbacks." },
    { label: "Rush EPA / Play", key: "down1_ppa_per_play_rush", baselineKey: "down1_epa_rush", fmt: (v) => signed(v, 2), indent: 1, tip: PRIME_EPA_BY_DOWN_TIP + " 1st-down rush attempts." },
    { label: "2nd Down EPA / Play", key: "down2_ppa_per_play", baselineKey: "down2_epa", fmt: (v) => signed(v, 2), tip: PRIME_EPA_BY_DOWN_TIP + " 2nd-down plays (pass and rush combined)." },
    { label: "Pass EPA / Play", key: "down2_ppa_per_play_pass", baselineKey: "down2_epa_pass", fmt: (v) => signed(v, 2), indent: 1, tip: PRIME_EPA_BY_DOWN_TIP + " 2nd-down dropbacks." },
    { label: "Rush EPA / Play", key: "down2_ppa_per_play_rush", baselineKey: "down2_epa_rush", fmt: (v) => signed(v, 2), indent: 1, tip: PRIME_EPA_BY_DOWN_TIP + " 2nd-down rush attempts." },
    { label: "3rd Down EPA / Play", key: "down3_ppa_per_play", baselineKey: "down3_epa", fmt: (v) => signed(v, 2), tip: PRIME_EPA_BY_DOWN_TIP + " 3rd-down plays (pass and rush combined)." },
    { label: "Pass EPA / Play", key: "down3_ppa_per_play_pass", baselineKey: "down3_epa_pass", fmt: (v) => signed(v, 2), indent: 1, tip: PRIME_EPA_BY_DOWN_TIP + " 3rd-down dropbacks." },
    { label: "Rush EPA / Play", key: "down3_ppa_per_play_rush", baselineKey: "down3_epa_rush", fmt: (v) => signed(v, 2), indent: 1, tip: PRIME_EPA_BY_DOWN_TIP + " 3rd-down rush attempts." },
  ]],
];

const GAME_SHAPE: [string, Spec[]][] = [
  ["Drives", [
    { label: "Offensive Drives", key: "offensive_drives", fmt: count, neutral: true, tip: "This offense's drive count for the game. CFBD-sourced (/stats/game/advanced), not PRIME's own drive-validation pipeline." },
    { label: "Yards / Drive", key: "yards_per_drive", fmt: (v) => plain(v, 1), tip: "Official total offensive yards divided by CFBD's own drive count. Higher is better. Both halves of this ratio are CFBD-sourced." },
    { label: "Avg Starting Field Position", key: "avg_start_yards_to_goal", fmt: fieldPosition, neutral: true, tip: "Average distance to the end zone where this offense's drives began. CFBD-sourced (/game/box/advanced); shown as a yard line, not conditionally colored." },
    { label: "Scoring Opportunities", key: "scoring_opportunities", fmt: count, neutral: true, tip: "CFBD's own count of drives that reached scoring range for this offense. CFBD-sourced (/game/box/advanced). The denominator for Points / Opportunity." },
    { label: "Points / Opportunity", key: "points_per_opportunity", fmt: (v) => plain(v, 2), indent: 1, tip: "Points scored per scoring opportunity. Higher is better -- a finishing-drives measure. CFBD-sourced." },
    { label: "Drive Share", key: "drive_share", fmt: pct, neutral: true, tip: "This team's share of the game's total drives (both teams combined), from CFBD's own drive counts for each side. Descriptive; not conditionally colored." },
  ]],
  ["Series Control (PRIME)", [
    { label: "Series Conversion", key: "series_conversion_rate", fmt: pct, tip: "Share of 1st-down series (a set of downs, not an individual play) that earned a new first down or a touchdown. Higher is better. Genuinely sequence-level; no CFBD game-level equivalent, so this stays PRIME's own play-by-play pipeline." },
    { label: "Recovery Rate", key: "recovery_rate", fmt: pct, indent: 1, tip: "Share of series that fell behind schedule (e.g. a negative or short-gain play) but still converted. Higher is better. PRIME-derived (sequence-level, no CFBD equivalent)." },
    { label: "3rd & Long Exposure", key: "third_long_exposure", fmt: pct, indent: 1, tip: "Share of series that reached a 3rd (or 4th) down needing 7 or more yards. Lower is better -- it means the offense stayed ahead of schedule. PRIME-derived (sequence-level, no CFBD equivalent)." },
  ]],
  ["Explosiveness", [
    { label: "Explosive Play Rate", key: "explosive_play_rate", fmt: pct, tip: "Share of offensive plays gaining 15+ yards through the air or 10+ on the ground. Higher is better. PRIME-derived -- this is a frequency, a different concept from CFBD's own \"explosiveness\" below (an average magnitude), so it is not replaced by it." },
    { label: "Explosive Pass Rate", key: "explosive_pass_rate", fmt: pct, indent: 1, tip: "Explosive Play Rate limited to dropbacks. Higher is better. PRIME-derived." },
    { label: "Explosive Rush Rate", key: "explosive_rush_rate", fmt: pct, indent: 1, tip: "Explosive Play Rate limited to rush attempts. Higher is better. PRIME-derived." },
    { label: "CFBD Explosiveness", key: "cfbd_explosiveness", fmt: (v) => plain(v, 2), neutral: true, tip: "CFBD's own explosiveness metric: average Predicted Points Added on this offense's successful plays only. This is a magnitude (how big are the good plays), not a rate -- do not compare directly to Explosive Play Rate above. CFBD-sourced; new field, not yet conditionally colored." },
    { label: "EPA / Play w/o Explosives", key: "ppa_per_play_without_explosives", baselineKey: "epa_without_explosives", fmt: (v) => signed(v, 2), tip: EPA_PLAY_TIP + " Explosive plays removed, to show how the offense performed on its ordinary snaps. Uses PRIME's own explosive-play definition, so this stays PRIME-derived even though the underlying per-play value is CFBD's PPA." },
    { label: "Explosive Dependency", key: "explosive_dependency", fmt: pct, neutral: true, tip: "Share of this offense's positive EPA that came from explosive plays alone. Descriptive, not conditionally colored -- a high number isn't necessarily bad, it just means the offense leaned on big plays rather than sustained drives. PRIME-derived." },
  ]],
  ["Possession Quality (PRIME)", [
    { label: "Clean Drive Rate", key: "clean_drive_rate", fmt: pct, tip: "Share of drives with no turnover, sack, TFL, or backward-progress accepted penalty. Higher is better. PRIME-derived (sequence-level, no CFBD equivalent)." },
    { label: "Drive Killer Rate", key: "drive_killer_rate", fmt: pct, tip: "Share of drives where a negative event (turnover, sack, TFL, failed 4th down, etc.) ended the drive rather than being overcome. Lower is better. PRIME-derived (sequence-level, no CFBD equivalent)." },
    { label: "Failure Rate", key: "failure_rate", fmt: pct, indent: 1, tip: "Share of offensive plays with negative EPA. Lower is better. PRIME-derived." },
    { label: "Avg Failure Damage", key: "avg_failure_damage", fmt: (v) => plain(v, 2), indent: 1, tip: "Average EPA lost on plays that had negative EPA. Lower (more negative) is worse; closer to zero is better. PRIME-derived." },
    { label: "Failure Burden", key: "failure_burden", fmt: (v) => plain(v, 3), indent: 1, tip: "Total negative EPA from failed plays spread across every eligible play this offense ran. Lower (more negative) is worse; closer to zero is better. PRIME-derived." },
    { label: "Failure Pressure", key: "failure_pressure", fmt: (v) => plain(v, 3), indent: 1, tip: "Failure Burden inflicted on the opponent's offense by this team's defense. Higher is better -- more pressure created. PRIME-derived." },
  ]],
  ["Disruption", [
    { label: "Havoc Allowed", key: "havoc_allowed", fmt: pct, tip: "Share of this offense's plays that resulted in a TFL, sack, or turnover against it. Lower is better. CFBD-sourced (/game/box/advanced); 2025+ coverage only (this endpoint has not yet been backfilled for older seasons)." },
    { label: "Sacks Taken", key: "sacks_taken", fmt: count, neutral: true, indent: 1, tip: "Sacks this team's offense allowed, from PRIME's play-by-play classifier. Descriptive; not conditionally colored. No CFBD game-level sack count exists, so this stays PRIME-derived; current-season coverage only." },
    { label: "TFLs Taken", key: "tfls_taken", fmt: count, neutral: true, indent: 1, tip: "Tackles for loss this team's offense allowed, from PRIME's play-by-play classifier. Descriptive; not conditionally colored." },
  ]],
  ["Turnover Impact (PRIME)", [
    { label: "Turnover EPA Lost", key: "turnover_epa_lost", fmt: (v) => plain(v, 1), tip: "Total CFBD PPA (displayed as EPA) this offense's turnovers cost it, from PRIME's play-by-play model. Stored as a negative number; closer to zero (e.g. -3 vs -15) is better. PRIME-derived (a modeled value, not a raw CFBD field)." },
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
    column("Efficiency", EFFICIENCY),
    column("Game Shape", GAME_SHAPE),
  ];
}
