import type { ExploratoryRow, ExploratoryWeekCounts } from "./types";

export type ExpColumn = {
  key: string;
  label: string;
  num: keyof ExploratoryWeekCounts;
  den: keyof ExploratoryWeekCounts;
  tooltip: string;
  profileNote: string;
  profileFormula: string;
  denLabel: string;
  fmt?: "pct1" | "plain2" | "plain3" | "signed3";
  lowerBetter?: boolean;
  noHeatmap?: boolean;
  /** Display num/den as a positive magnitude (multiply by -1) when the raw
   * stored sum is naturally negative-signed, e.g. turnover EPA -- matches
   * Failure Burden/Pressure's existing positive-magnitude convention rather
   * than showing a negative "Lost"/"Created" value. */
  negate?: boolean;
};

type ExpSection = { title: string; columns: ExpColumn[] };

export const SERIES_OFFENSE: ExpColumn[] = [
  {
    key: "seriesConversionRate",
    label: "Series Conversion %",
    num: "seriesConversions",
    den: "seriesOpportunities",
    tooltip: "A series is one fresh set of downs. This measures how often the offense earns another first down or scores a touchdown before that series ends.",
    profileNote: "Percentage of series that end with another first down or a touchdown.",
    profileFormula: "Converted series ÷ eligible series",
    denLabel: "Series",
  },
  {
    key: "recoveryRate",
    label: "Recovery %",
    num: "recoveredSeries",
    den: "recoveryOpportunities",
    tooltip: "Only looks at series after an unsuccessful 1st- or 2nd-down play. A recovery means the offense still earns another first down or touchdown in that same series.",
    profileNote: "Percentage of series that recover for a first down or TD after a failed 1st- or 2nd-down play.",
    profileFormula: "Recovered series ÷ early-down failure chances",
    denLabel: "Chances",
  },
  {
    key: "longDownAvoidanceRate",
    label: "Avoid 3rd & Long %",
    num: "longDownAvoidanceSeries",
    den: "eligibleSeries",
    tooltip: "How often an offensive series never reaches 3rd-and-7 or longer. Higher means the offense stays ahead of the chains more often.",
    profileNote: "Percentage of series that never reach 3rd-and-7 or longer.",
    profileFormula: "Series avoiding 3rd & 7+ ÷ eligible series",
    denLabel: "Series",
  },
];

const SERIES_DEFENSE: ExpColumn[] = [
  {
    key: "seriesStopRate",
    label: "Series Stop %",
    num: "seriesStops",
    den: "seriesStopOpportunities",
    tooltip: "How often the defense ends an opponent's fresh set of downs before the offense gains another first down or scores a touchdown.",
    profileNote: "Percentage of opponent series stopped before another first down or touchdown.",
    profileFormula: "Stopped opponent series ÷ opponent series",
    denLabel: "Series",
  },
  {
    key: "closeoutRate",
    label: "Closeout %",
    num: "closeouts",
    den: "closeoutOpportunities",
    tooltip: "Only looks after the defense wins an early down. A closeout means the opponent never recovers for another first down or touchdown in that series.",
    profileNote: "Percentage of early-down wins the defense finishes without allowing a first down or touchdown.",
    profileFormula: "Closeouts ÷ early-down win chances",
    denLabel: "Chances",
  },
  {
    key: "longDownCreationRate",
    label: "Force 3rd & Long %",
    num: "longDownsCreated",
    den: "longDownCreationOpportunities",
    tooltip: "How often an opponent series reaches 3rd-and-7 or longer. Higher means the defense creates more obvious passing situations.",
    profileNote: "Percentage of opponent series forced into 3rd-and-7 or longer.",
    profileFormula: "Opponent series reaching 3rd & 7+ ÷ opponent series",
    denLabel: "Series",
  },
];

const POSSESSIONS_OFFENSE: ExpColumn[] = [
  {
    key: "cleanDriveRate", label: "Clean Drive %",
    num: "cleanDrives", den: "eligibleDrives",
    tooltip: "A clean drive has no turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down.",
    profileNote: "Percentage of drives with no offensive mistakes (turnovers, sacks, TFLs, costly penalties, or failed 4th downs).",
    profileFormula: "Clean drives ÷ eligible drives",
    denLabel: "Drives",
  },
  {
    key: "driveKillerRate", label: "Drive Killer %",
    num: "drivesKilled", den: "drivesWithKillerEvent",
    tooltip: "A mistake-drive contains a turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down. It is killed when the offense never earns another first down or TD after the final mistake.",
    profileNote: "Percentage of drives with a mistake that never recover for another first down or TD.",
    profileFormula: "Killed mistake-drives ÷ mistake-drives",
    denLabel: "Mistake-drives",
    lowerBetter: true,
  },
];

const POSSESSIONS_DEFENSE: ExpColumn[] = [
  {
    key: "cleanDriveRateAllowed", label: "Clean Drive Allowed %",
    num: "cleanDrivesAllowed", den: "eligibleDrivesFaced",
    tooltip: "How often an opponent completes a drive without a turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down. Lower is better defense.",
    profileNote: "Percentage of opponent drives with no offensive mistakes. Lower means more defensive disruption.",
    profileFormula: "Opponent clean drives ÷ opponent drives",
    denLabel: "Drives",
    lowerBetter: true,
  },
  {
    key: "driveKillerRateForced", label: "Drive Killer Forced %",
    num: "drivesKilledForced", den: "drivesWithKillerEventForced",
    tooltip: "Among opponent drives containing a tracked mistake, how often the offense never earns another first down or touchdown after the final mistake. This measures finishing the drive, not creating the mistake.",
    profileNote: "Percentage of opponent drives with a mistake that never recover for another first down or TD.",
    profileFormula: "Killed opponent mistake-drives ÷ opponent mistake-drives",
    denLabel: "Mistake-drives",
  },
];

const STYLE_RISK: ExpColumn[] = [
  {
    key: "explosiveDependency", label: "Explosive Dependency %",
    num: "explosivePositiveEpa", den: "positiveEpa",
    tooltip: "Share of the offense's positive EPA that comes from explosive plays. Explosives are rushes of 10+ yards or passes of 20+ yards. This describes style, not quality.",
    profileNote: "Percentage of positive offensive EPA coming from explosive plays (10+ yard runs, 20+ yard passes).",
    profileFormula: "Explosive positive EPA ÷ all positive EPA",
    denLabel: "Positive EPA",
    noHeatmap: true,
  },
  {
    key: "nonExplosiveEpaPerPlay", label: "Non-Explosive EPA/play",
    num: "nonExplosiveEpa", den: "nonExplosivePlays",
    tooltip: "EPA per play after explosive plays are removed. Higher means the offense creates more value without relying on big gains.",
    profileNote: "EPA per play after explosive plays are removed.",
    profileFormula: "Non-explosive EPA ÷ non-explosive plays",
    denLabel: "Plays",
    fmt: "signed3",
  },
  {
    key: "failureRate", label: "Failure Rate",
    num: "negativeEpaPlays", den: "epaEligiblePlays",
    tooltip: "Share of EPA-eligible offensive plays with negative EPA. Lower means fewer plays reduce expected scoring value.",
    profileNote: "Percentage of offensive plays with negative EPA.",
    profileFormula: "Negative-EPA plays ÷ EPA-eligible plays",
    denLabel: "Plays",
    lowerBetter: true,
  },
  {
    key: "averageFailureDamage", label: "Avg Failure Damage",
    num: "negativeEpaMagnitudeSum", den: "negativeEpaPlays",
    tooltip: "Average EPA lost on each negative-EPA play. Lower means the offense's bad plays are less damaging when they happen.",
    profileNote: "Average EPA lost when the offense has a negative-EPA play.",
    profileFormula: "Total negative EPA lost ÷ negative-EPA plays",
    denLabel: "Bad plays",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "failureBurden", label: "Failure Burden",
    num: "negativeEpaMagnitudeSum", den: "epaEligiblePlays",
    tooltip: "Total negative-play EPA damage spread across every EPA-eligible offensive play. It combines how often bad plays happen with how damaging they are.",
    profileNote: "Negative-play EPA damage per offensive play, combining how often bad plays happen and how costly they are.",
    profileFormula: "Total negative EPA lost ÷ all EPA-eligible plays",
    denLabel: "Plays",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "failurePressure", label: "Failure Pressure",
    num: "opponentNegativeEpaMagnitudeSum", den: "opponentEpaEligiblePlays",
    tooltip: "The defensive mirror of Failure Burden: opponent negative-play EPA damage spread across opponent EPA-eligible plays.",
    profileNote: "Negative-play EPA damage opponents absorb per play against the defense.",
    profileFormula: "Opponent negative EPA lost ÷ opponent eligible plays",
    denLabel: "Opp. plays",
    fmt: "plain3",
  },
];

const TURNOVERS_OFFENSE: ExpColumn[] = [
  {
    key: "turnoverRate", label: "Turnover Rate",
    num: "turnovers", den: "offensiveDrives",
    tooltip: "Interceptions plus lost fumbles (possession actually lost to the defense) divided by offensive drives. Self-recovered fumbles never count.",
    profileNote: "Percentage of offensive drives that end in a turnover.",
    profileFormula: "Turnovers ÷ offensive drives",
    denLabel: "Drives",
    lowerBetter: true,
  },
  {
    key: "intRate", label: "INT Rate",
    num: "interceptions", den: "passAttempts",
    tooltip: "Interceptions thrown divided by pass attempts (every dropback that wasn't a sack, including intercepted throws).",
    profileNote: "Percentage of pass attempts intercepted.",
    profileFormula: "Interceptions thrown ÷ pass attempts",
    denLabel: "Attempts",
    lowerBetter: true,
  },
  {
    key: "lostFumbleRate", label: "Lost Fumble Rate",
    num: "lostFumbles", den: "offensiveDrives",
    tooltip: "Fumbles recovered by the defense divided by offensive drives. A fumble the offense recovers itself is not counted.",
    profileNote: "Percentage of offensive drives that end in a fumble lost to the defense.",
    profileFormula: "Lost fumbles ÷ offensive drives",
    denLabel: "Drives",
    lowerBetter: true,
  },
  {
    key: "turnoverEpaLostPerGame", label: "Turnover EPA Lost/Game",
    num: "turnoverEpaSum", den: "games", negate: true,
    tooltip: "Total EPA (expected points added) given away on interceptions and lost fumbles, per game. Uses CFBD's canonical play-level EPA model.",
    profileNote: "EPA given away to interceptions and lost fumbles, per game.",
    profileFormula: "Turnover EPA lost ÷ games",
    denLabel: "Games",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "turnoverEpaLostPerDrive", label: "Turnover EPA Lost/Drive",
    num: "turnoverEpaSum", den: "offensiveDrives", negate: true,
    tooltip: "Total EPA given away on interceptions and lost fumbles, spread across every offensive drive.",
    profileNote: "EPA given away to interceptions and lost fumbles, per offensive drive.",
    profileFormula: "Turnover EPA lost ÷ offensive drives",
    denLabel: "Drives",
    fmt: "plain3", lowerBetter: true,
  },
];

const TURNOVERS_DEFENSE: ExpColumn[] = [
  {
    key: "takeawayRate", label: "Takeaway Rate",
    num: "takeaways", den: "opponentDrives",
    tooltip: "Interceptions plus fumbles recovered by this defense, divided by opponent offensive drives.",
    profileNote: "Percentage of opponent drives that end in a takeaway.",
    profileFormula: "Takeaways ÷ opponent drives",
    denLabel: "Opp. drives",
  },
  {
    key: "intRateForced", label: "INT Rate Forced",
    num: "interceptionsForced", den: "opponentPassAttempts",
    tooltip: "Interceptions by this defense divided by opponent pass attempts.",
    profileNote: "Percentage of opponent pass attempts intercepted.",
    profileFormula: "Interceptions forced ÷ opponent pass attempts",
    denLabel: "Opp. attempts",
  },
  {
    key: "fumbleRecoveryRate", label: "Fumble Recovery Rate",
    num: "fumbleRecoveries", den: "opponentDrives",
    tooltip: "Opponent fumbles recovered by this defense, divided by opponent offensive drives.",
    profileNote: "Percentage of opponent drives that end in a fumble this defense recovers.",
    profileFormula: "Fumble recoveries ÷ opponent drives",
    denLabel: "Opp. drives",
  },
  {
    key: "turnoverEpaCreatedPerGame", label: "Turnover EPA Created/Game",
    num: "opponentTurnoverEpaSum", den: "games", negate: true,
    tooltip: "Total EPA taken away from opponents via interceptions and fumbles this defense forced, per game.",
    profileNote: "EPA taken from opponents via forced turnovers, per game.",
    profileFormula: "Opponent turnover EPA lost ÷ games",
    denLabel: "Games",
    fmt: "plain3",
  },
  {
    key: "turnoverEpaCreatedPerDrive", label: "Turnover EPA Created/Drive",
    num: "opponentTurnoverEpaSum", den: "opponentDrives", negate: true,
    tooltip: "Total EPA taken away from opponents via forced turnovers, spread across every opponent offensive drive.",
    profileNote: "EPA taken from opponents via forced turnovers, per opponent drive.",
    profileFormula: "Opponent turnover EPA lost ÷ opponent drives",
    denLabel: "Opp. drives",
    fmt: "plain3",
  },
];

// Points per Scoring Opportunity (and its opponent mirror) is deliberately
// NOT a column here -- a row-level check found it byte-for-byte identical to
// the existing Finishing Drives points-per-opportunity stat (0 mismatches
// across 1,616 2025 rows). Exposing it under a second name on this page
// would just be the same number twice; see Finishing Drives on /advanced
// instead. The underlying scoringOpportunity* fields still get computed and
// exported (useful for other research), just never surfaced as a page column.

export const SECTIONS: ExpSection[] = [
  { title: "Series · Offense", columns: SERIES_OFFENSE },
  { title: "Series · Defense", columns: SERIES_DEFENSE },
  { title: "Possessions · Offense", columns: POSSESSIONS_OFFENSE },
  { title: "Possessions · Defense", columns: POSSESSIONS_DEFENSE },
  { title: "Style / Risk", columns: STYLE_RISK },
  { title: "Turnovers · Offense", columns: TURNOVERS_OFFENSE },
  { title: "Turnovers · Defense", columns: TURNOVERS_DEFENSE },
];

export const ALL_COLUMNS: ExpColumn[] = SECTIONS.flatMap((s) => s.columns);
export const SECTION_START_KEYS = new Set(SECTIONS.map((s) => s.columns[0]?.key).filter(Boolean));

export type Aggregated = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  wk: Partial<ExploratoryWeekCounts>;
  [key: string]: unknown;
};

type FanTier = { label: string; className: string };

export function fanTier(rank: number | null, total: number, smallSample: boolean, neutral = false): FanTier {
  if (smallSample) return { label: "Small Sample", className: "profile-tier--sample" };
  if (!rank || total <= 0) return { label: "No Rank", className: "profile-tier--sample" };
  const percentile = rank / total;
  if (neutral) return { label: percentile <= .33 ? "High Dependency" : percentile > .67 ? "Low Dependency" : "Balanced", className: "profile-tier--sample" };
  if (percentile <= 0.10) return { label: "Elite", className: "profile-tier--elite" };
  if (percentile <= 0.25) return { label: "Strong", className: "profile-tier--strong" };
  if (percentile <= 0.40) return { label: "Good", className: "profile-tier--good" };
  if (percentile <= 0.60) return { label: "Average", className: "profile-tier--average" };
  if (percentile <= 0.80) return { label: "Below Avg", className: "profile-tier--below" };
  return { label: "Needs Work", className: "profile-tier--poor" };
}

/** Research denominator floors. Secondary existing diagnostic columns retain 20. */
export function minimumN(col: ExpColumn): number {
  if (["seriesOpportunities", "seriesStopOpportunities", "eligibleSeries", "longDownCreationOpportunities"].includes(col.den)) return 25;
  if (["recoveryOpportunities", "closeoutOpportunities"].includes(col.den)) return 16;
  if (["failureRate", "averageFailureDamage"].includes(col.key)) return 20;
  return 10;
}

export function aggregateExploratory(byWeek: Record<string, ExploratoryRow[]>, weeks: number[], start: number, end: number): Aggregated[] {
  const byTeam = new Map<string, Aggregated>();
  for (const week of weeks.filter(w => w >= start && w <= end)) {
    for (const row of byWeek[String(week)] || []) {
      let acc = byTeam.get(row.slug);
      if (!acc) {
        acc = { team: row.team, slug: row.slug, teamId: row.teamId, conf: row.conf, wk: {} };
        byTeam.set(row.slug, acc);
      }
      for (const field of Object.keys(row.wk) as (keyof ExploratoryWeekCounts)[]) {
        const value = row.wk[field];
        if (typeof value === "number" && Number.isFinite(value)) acc.wk[field] = (acc.wk[field] ?? 0) + value;
      }
    }
  }
  return [...byTeam.values()].map(acc => {
    const out: Aggregated = { ...acc };
    for (const col of ALL_COLUMNS) {
      const n = acc.wk[col.den] ?? 0;
      out[col.key] = n > 0 ? ((acc.wk[col.num] ?? 0) / n) * (col.negate ? -1 : 1) : null;
      out[`${col.key}_n`] = n;
    }
    return out;
  });
}

export function rankExploratory(teams: Aggregated[]): Aggregated[] {
  const out = teams.map(t => ({ ...t }));
  for (const col of ALL_COLUMNS) {
    const eligible = out.filter(t => typeof t[col.key] === "number" && Number.isFinite(t[col.key]) && Number(t[`${col.key}_n`]) >= minimumN(col));
    for (const team of out) {
      team[`_rank_${col.key}`] = eligible.includes(team) ? 1 + eligible.filter(t => col.lowerBetter ? Number(t[col.key]) < Number(team[col.key]) : Number(t[col.key]) > Number(team[col.key])).length : null;
    }
  }
  return out;
}