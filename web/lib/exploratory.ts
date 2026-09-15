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
};

type ExpSection = { title: string; columns: ExpColumn[] };

export const SERIES_OFFENSE: ExpColumn[] = [
  {
    key: "seriesConversionRate",
    label: "Series Conversion %",
    num: "seriesConversions",
    den: "seriesOpportunities",
    tooltip: "A series is one fresh set of downs. This measures how often the offense earns another first down or scores a touchdown before that series ends.",
    profileNote: "A series is one fresh set of downs. This asks whether the offense earns another first down or TD before it ends. Calculation: converted series ÷ eligible series.",
    profileFormula: "Converted series ÷ eligible series",
    denLabel: "Series",
  },
  {
    key: "recoveryRate",
    label: "Recovery %",
    num: "recoveredSeries",
    den: "recoveryOpportunities",
    tooltip: "Only looks at series after an unsuccessful 1st- or 2nd-down play. A recovery means the offense still earns another first down or touchdown in that same series.",
    profileNote: "Only looks at series after a failed 1st- or 2nd-down play. It measures whether the offense still recovers for a first down or TD. Calculation: recovered series ÷ early-down failure chances.",
    profileFormula: "Recovered series ÷ early-down failure chances",
    denLabel: "Chances",
  },
  {
    key: "longDownAvoidanceRate",
    label: "Avoid 3rd & Long %",
    num: "longDownAvoidanceSeries",
    den: "eligibleSeries",
    tooltip: "How often an offensive series never reaches 3rd-and-7 or longer. Higher means the offense stays ahead of the chains more often.",
    profileNote: "Measures how often a series stays out of 3rd-and-7 or longer. Calculation: series avoiding 3rd & 7+ ÷ eligible series.",
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
    profileNote: "Measures how often the defense ends a fresh opponent series before another first down or TD. Calculation: stopped opponent series ÷ opponent series.",
    profileFormula: "Stopped opponent series ÷ opponent series",
    denLabel: "Series",
  },
  {
    key: "closeoutRate",
    label: "Closeout %",
    num: "closeouts",
    den: "closeoutOpportunities",
    tooltip: "Only looks after the defense wins an early down. A closeout means the opponent never recovers for another first down or touchdown in that series.",
    profileNote: "Only looks after the defense wins 1st or 2nd down. A closeout means the offense never recovers for another first down or TD. Calculation: closeouts ÷ early-down win chances.",
    profileFormula: "Closeouts ÷ early-down win chances",
    denLabel: "Chances",
  },
  {
    key: "longDownCreationRate",
    label: "Force 3rd & Long %",
    num: "longDownsCreated",
    den: "longDownCreationOpportunities",
    tooltip: "How often an opponent series reaches 3rd-and-7 or longer. Higher means the defense creates more obvious passing situations.",
    profileNote: "Measures how often the defense gets an opponent series to 3rd-and-7 or longer. Calculation: opponent series reaching 3rd & 7+ ÷ opponent series.",
    profileFormula: "Opponent series reaching 3rd & 7+ ÷ opponent series",
    denLabel: "Series",
  },
];

const POSSESSIONS_OFFENSE: ExpColumn[] = [
  {
    key: "cleanDriveRate", label: "Clean Drive %",
    num: "cleanDrives", den: "eligibleDrives",
    tooltip: "A clean drive has no turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down.",
    profileNote: "A clean drive has no turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down. Calculation: clean drives ÷ eligible drives.",
    profileFormula: "Clean drives ÷ eligible drives",
    denLabel: "Drives",
  },
  {
    key: "driveKillerRate", label: "Drive Killer %",
    num: "drivesKilled", den: "drivesWithKillerEvent",
    tooltip: "A mistake-drive contains a turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down. It is killed when the offense never earns another first down or TD after the final mistake.",
    profileNote: "A mistake-drive has a turnover, sack, TFL, costly accepted penalty, or failed 4th down. It is killed if the offense never gets another first down or TD after the final mistake. Calculation: killed mistake-drives ÷ mistake-drives.",
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
    profileNote: "Measures how often opponents complete a drive without a turnover, sack, TFL, costly penalty, or failed 4th down. Calculation: opponent clean drives ÷ opponent drives.",
    profileFormula: "Opponent clean drives ÷ opponent drives",
    denLabel: "Drives",
    lowerBetter: true,
  },
  {
    key: "driveKillerRateForced", label: "Drive Killer Forced %",
    num: "drivesKilledForced", den: "drivesWithKillerEventForced",
    tooltip: "Among opponent drives containing a tracked mistake, how often the offense never earns another first down or touchdown after the final mistake. This measures finishing the drive, not creating the mistake.",
    profileNote: "Starts only after an opponent has a mistake-drive. It measures how often the defense keeps that drive dead, not how often it creates the mistake. Calculation: killed opponent mistake-drives ÷ opponent mistake-drives.",
    profileFormula: "Killed opponent mistake-drives ÷ opponent mistake-drives",
    denLabel: "Mistake-drives",
  },
];

const STYLE_RISK: ExpColumn[] = [
  {
    key: "explosiveDependency", label: "Explosive Dependency %",
    num: "explosivePositiveEpa", den: "positiveEpa",
    tooltip: "Share of the offense's positive EPA that comes from explosive plays. Explosives are rushes of 10+ yards or passes of 20+ yards. This describes style, not quality.",
    profileNote: "Shows how much of the offense's positive EPA comes from big plays: rushes of 10+ yards or passes of 20+ yards. It describes style, not quality. Calculation: explosive positive EPA ÷ all positive EPA.",
    profileFormula: "Explosive positive EPA ÷ all positive EPA",
    denLabel: "Positive EPA",
    noHeatmap: true,
  },
  {
    key: "nonExplosiveEpaPerPlay", label: "Non-Explosive EPA/play",
    num: "nonExplosiveEpa", den: "nonExplosivePlays",
    tooltip: "EPA per play after explosive plays are removed. Higher means the offense creates more value without relying on big gains.",
    profileNote: "Measures offensive efficiency after explosive plays are removed. Calculation: non-explosive EPA ÷ non-explosive plays.",
    profileFormula: "Non-explosive EPA ÷ non-explosive plays",
    denLabel: "Plays",
    fmt: "signed3",
  },
  {
    key: "failureRate", label: "Failure Rate",
    num: "negativeEpaPlays", den: "epaEligiblePlays",
    tooltip: "Share of EPA-eligible offensive plays with negative EPA. Lower means fewer plays reduce expected scoring value.",
    profileNote: "Measures how often an offensive play has negative EPA and reduces expected scoring value. Calculation: negative-EPA plays ÷ EPA-eligible plays.",
    profileFormula: "Negative-EPA plays ÷ EPA-eligible plays",
    denLabel: "Plays",
    lowerBetter: true,
  },
  {
    key: "averageFailureDamage", label: "Avg Failure Damage",
    num: "negativeEpaMagnitudeSum", den: "negativeEpaPlays",
    tooltip: "Average EPA lost on each negative-EPA play. Lower means the offense's bad plays are less damaging when they happen.",
    profileNote: "Measures how costly the offense's bad plays are when they happen. Calculation: total negative EPA lost ÷ negative-EPA plays.",
    profileFormula: "Total negative EPA lost ÷ negative-EPA plays",
    denLabel: "Bad plays",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "failureBurden", label: "Failure Burden",
    num: "negativeEpaMagnitudeSum", den: "epaEligiblePlays",
    tooltip: "Total negative-play EPA damage spread across every EPA-eligible offensive play. It combines how often bad plays happen with how damaging they are.",
    profileNote: "Combines how often bad plays happen with how damaging they are by spreading total negative-play EPA across every eligible play. Calculation: total negative EPA lost ÷ all EPA-eligible plays.",
    profileFormula: "Total negative EPA lost ÷ all EPA-eligible plays",
    denLabel: "Plays",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "failurePressure", label: "Failure Pressure",
    num: "opponentNegativeEpaMagnitudeSum", den: "opponentEpaEligiblePlays",
    tooltip: "The defensive mirror of Failure Burden: opponent negative-play EPA damage spread across opponent EPA-eligible plays.",
    profileNote: "The defensive version of Failure Burden. It measures how much negative-play EPA damage opponents absorb per eligible play. Calculation: opponent negative EPA lost ÷ opponent eligible plays.",
    profileFormula: "Opponent negative EPA lost ÷ opponent eligible plays",
    denLabel: "Opp. plays",
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
      out[col.key] = n > 0 ? (acc.wk[col.num] ?? 0) / n : null;
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
