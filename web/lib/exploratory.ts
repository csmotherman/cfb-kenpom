import type { ExploratoryRow, ExploratoryWeekCounts } from "./types";

export type ExpColumn = {
  key: string;
  label: string;
  num: keyof ExploratoryWeekCounts;
  den: keyof ExploratoryWeekCounts;
  tooltip: string;
  profileNote: string;
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
    tooltip: "Converted series divided by eligible series. A series converts when the offense earns another first down or scores a touchdown before that set of downs ends.",
    profileNote: "Converted series ÷ eligible series",
  },
  {
    key: "recoveryRate",
    label: "Recovery %",
    num: "recoveredSeries",
    den: "recoveryOpportunities",
    tooltip: "Recovered series divided by series with an unsuccessful 1st- or 2nd-down play. A recovery means the offense still earns another first down or touchdown in that same series.",
    profileNote: "Recovered bad-down series ÷ early-down failures",
  },
  {
    key: "longDownAvoidanceRate",
    label: "Avoid 3rd & Long %",
    num: "longDownAvoidanceSeries",
    den: "eligibleSeries",
    tooltip: "Series that never reach 3rd-and-7 or longer divided by eligible series. Higher means the offense stays ahead of the chains more often.",
    profileNote: "Series avoiding 3rd & 7+ ÷ eligible series",
  },
];

const SERIES_DEFENSE: ExpColumn[] = [
  {
    key: "seriesStopRate",
    label: "Series Stop %",
    num: "seriesStops",
    den: "seriesStopOpportunities",
    tooltip: "Opponent series stopped before another first down or touchdown divided by opponent eligible series.",
    profileNote: "Opponent series stopped ÷ opponent series",
  },
  {
    key: "closeoutRate",
    label: "Closeout %",
    num: "closeouts",
    den: "closeoutOpportunities",
    tooltip: "Closeouts divided by opponent series with an unsuccessful early-down play. A closeout means the defense prevents a later first down or touchdown in that series.",
    profileNote: "Early-down wins finished ÷ closeout chances",
  },
  {
    key: "longDownCreationRate",
    label: "Force 3rd & Long %",
    num: "longDownsCreated",
    den: "longDownCreationOpportunities",
    tooltip: "Opponent series that reach 3rd-and-7 or longer divided by opponent eligible series. Higher means more obvious passing situations created.",
    profileNote: "Opponent series reaching 3rd & 7+ ÷ opponent series",
  },
];

const POSSESSIONS_OFFENSE: ExpColumn[] = [
  {
    key: "cleanDriveRate", label: "Clean Drive %",
    num: "cleanDrives", den: "eligibleDrives",
    tooltip: "Clean drives divided by eligible drives. A drive is clean when it has no turnover, sack, TFL, costly accepted offensive penalty, or failed 4th down.",
    profileNote: "Mistake-free drives ÷ eligible drives",
  },
  {
    key: "driveKillerRate", label: "Drive Killer %",
    num: "drivesKilled", den: "drivesWithKillerEvent",
    tooltip: "Killed drives divided by drives containing a tracked mistake. A drive is killed when the offense never earns another first down or touchdown after the final qualifying mistake.",
    profileNote: "Killed mistake-drives ÷ mistake-drives",
    lowerBetter: true,
  },
];

const POSSESSIONS_DEFENSE: ExpColumn[] = [
  {
    key: "cleanDriveRateAllowed", label: "Clean Drive Allowed %",
    num: "cleanDrivesAllowed", den: "eligibleDrivesFaced",
    tooltip: "Opponent clean drives divided by opponent eligible drives. Lower is better because fewer possessions stay completely free of major negative events.",
    profileNote: "Opponent clean drives ÷ opponent drives",
    lowerBetter: true,
  },
  {
    key: "driveKillerRateForced", label: "Drive Killer Forced %",
    num: "drivesKilledForced", den: "drivesWithKillerEventForced",
    tooltip: "Opponent mistake-drives that never recover divided by opponent drives containing a tracked mistake. This measures finishing the drive after a mistake occurs, not creating the mistake itself.",
    profileNote: "Opponent killed mistake-drives ÷ opponent mistake-drives",
  },
];

const STYLE_RISK: ExpColumn[] = [
  {
    key: "explosiveDependency", label: "Explosive Dependency %",
    num: "explosivePositiveEpa", den: "positiveEpa",
    tooltip: "Positive EPA from explosive plays divided by all positive EPA. Explosive plays are rushes of 10+ yards or passes of 20+ yards. This describes style, not quality.",
    profileNote: "Explosive positive EPA ÷ all positive EPA",
    noHeatmap: true,
  },
  {
    key: "nonExplosiveEpaPerPlay", label: "Non-Explosive EPA/play",
    num: "nonExplosiveEpa", den: "nonExplosivePlays",
    tooltip: "EPA from non-explosive plays divided by the number of non-explosive plays. Higher means the offense creates more value without relying on big gains.",
    profileNote: "Non-explosive EPA ÷ non-explosive plays",
    fmt: "signed3",
  },
  {
    key: "failureRate", label: "Failure Rate",
    num: "negativeEpaPlays", den: "epaEligiblePlays",
    tooltip: "Negative-EPA plays divided by all EPA-eligible offensive plays. Lower means fewer plays reduce the offense's expected scoring value.",
    profileNote: "Negative-EPA plays ÷ EPA-eligible plays",
    lowerBetter: true,
  },
  {
    key: "averageFailureDamage", label: "Avg Failure Damage",
    num: "negativeEpaMagnitudeSum", den: "negativeEpaPlays",
    tooltip: "Total negative EPA lost divided by the number of negative-EPA plays. Lower means the offense's bad plays are less damaging when they happen.",
    profileNote: "Negative EPA lost ÷ negative-EPA plays",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "failureBurden", label: "Failure Burden",
    num: "negativeEpaMagnitudeSum", den: "epaEligiblePlays",
    tooltip: "Total negative EPA lost divided by all EPA-eligible plays. It combines how often bad plays happen with how damaging they are.",
    profileNote: "Negative EPA lost ÷ all EPA-eligible plays",
    fmt: "plain3", lowerBetter: true,
  },
  {
    key: "failurePressure", label: "Failure Pressure",
    num: "opponentNegativeEpaMagnitudeSum", den: "opponentEpaEligiblePlays",
    tooltip: "Opponent negative EPA lost divided by opponent EPA-eligible plays. Higher means the defense forces more negative-play damage per snap.",
    profileNote: "Opponent negative EPA lost ÷ opponent eligible plays",
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
