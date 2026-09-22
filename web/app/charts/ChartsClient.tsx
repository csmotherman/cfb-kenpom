"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteFooter from "@/components/SiteFooter";
import {
  getAdvancedSeason,
  getExploratorySeason,
  getMeta,
  getRankingsSeason,
  getTeamStatsSeason,
  getTeamStatsWeeklySeason,
} from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import { aggregateExploratory, SECTIONS } from "@/lib/exploratory";
import type {
  AdvancedSeason,
  ExploratorySeason,
  RankingsSeason,
  TeamStatsSeason,
  TeamStatsWeeklySeason,
} from "@/lib/types";
import styles from "./charts.module.css";

type MetricFormat = "number" | "number3" | "percent" | "rank" | "integer";
type Metric = {
  key: string;
  label: string;
  group: string;
  format: MetricFormat;
};
type TeamPoint = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  values: Record<string, number | null>;
};
type HoveredPoint = TeamPoint & { x: number; y: number };
type Aspect = "4:3" | "16:9" | "1:1";

const META_KEYS = new Set(["teamId"]);
const ADVANCED_DUPES = new Set(["adjEM", "adjO", "adjD", "rank", "adjORank", "adjDRank"]);
const KNOWN_LABELS: Record<string, string> = {
  "ratings.rank": "Power Rating Rank",
  "ratings.adjEM": "Net Rating",
  "ratings.adjO": "Off Rating",
  "ratings.adjD": "Def Rating",
  "ratings.adjORank": "Off Rating Rank",
  "ratings.adjDRank": "Def Rating Rank",
  "ratings.sos": "Strength of Schedule",
  "ratings.sosRank": "SOS Rank",
  "ratings.sor": "Strength of Record",
  "ratings.sorRank": "SOR Rank",
  "ratings.rankChange": "Power Rank Change",
  "advanced.asm": "Adjusted Score Matrix",
  "advanced.cff": "CFF",
  "advanced.cfpChancePct": "CFP Chance",
  "advanced.fieldPos": "Adjusted Field Position",
  "advanced.off": "Advanced Offense",
  "advanced.def": "Advanced Defense",
  "advanced.offExp": "Adjusted Offensive Explosiveness",
  "advanced.defExp": "Adjusted Defensive Explosiveness",
  "advanced.offFin": "Adjusted Offensive Finishing",
  "advanced.defFin": "Adjusted Defensive Finishing",
  "advanced.offHavoc": "Adjusted Havoc Avoided",
  "advanced.defHavoc": "Adjusted Havoc Forced",
  "advanced.epaAdj": "Adjusted EPA / Play",
  "advanced.epaAdjAllowed": "Adjusted EPA / Play Allowed",
  "advanced.passEpaAdj": "Adjusted Pass EPA",
  "advanced.passEpaAdjAllowed": "Adjusted Pass EPA Allowed",
  "advanced.rushEpaAdj": "Adjusted Rush EPA",
  "advanced.rushEpaAdjAllowed": "Adjusted Rush EPA Allowed",
  "advanced.successAdj": "Adjusted Success Rate",
  "advanced.successAdjAllowed": "Adjusted Success Rate Allowed",
};

const EXPLORATORY_METRICS: Map<string, Pick<Metric, "label" | "group" | "format">> = new Map(
  SECTIONS.flatMap((section) =>
    section.columns.map((column) => [
      `exploratory.${column.key}`,
      {
        label: column.label,
        group: `Exploratory · ${section.title}`,
        format: (column.fmt ?? "pct1") === "pct1" ? "percent" : "number",
      } satisfies Pick<Metric, "label" | "group" | "format">,
    ] as const)
  )
);

const PRESETS = [
  {
    name: "Battle Tested",
    x: "ratings.sosRank",
    y: "ratings.adjEM",
    title: "Who's Strong — and Who's Been Tested?",
    subtitle: "Power rating meets the difficulty of the schedule already played.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Beating Up Cupcakes", "Battle Tested", "Bad & Untested", "Schedule From Hell"],
  },
  {
    name: "Complete Teams",
    x: "ratings.adjD",
    y: "ratings.adjO",
    title: "The Most Complete Teams in College Football",
    subtitle: "The teams that can win with both their offense and their defense.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Offense Carries", "Complete Team", "Nothing Working", "Defense Carries"],
  },
  {
    name: "Offensive Identity",
    x: "advanced.successAdj",
    y: "advanced.offExp",
    title: "How Offenses Actually Win",
    subtitle: "Who stays on schedule, who creates explosives — and who does both.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Living On Big Plays", "Pick Your Poison", "Stalled Out", "Death By 1,000 Cuts"],
  },
  {
    name: "Every-Down Value",
    x: "advanced.successAdj",
    y: "advanced.epaAdj",
    title: "Which Offenses Create Value Every Down",
    subtitle: "Success rate shows consistency; EPA shows how much each play is worth.",
    xReverse: false,
    yReverse: false,
    quadrants: ["High-Leverage Plays", "Offensive Machine", "Going Nowhere", "Move The Chains"],
  },
  {
    name: "Cashing In",
    x: "advanced.successAdj",
    y: "advanced.offFin",
    title: "Who Turns Good Drives Into Points",
    subtitle: "Moving the chains only matters if scoring opportunities become points.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Finishes, Doesn't Sustain", "Complete Drives", "No Threat", "Empty Calories"],
  },
  {
    name: "Big Plays to Points",
    x: "advanced.offExp",
    y: "advanced.offFin",
    title: "Who Turns Explosives Into Touchdowns",
    subtitle: "Chunk plays create opportunities; the best offenses finish them.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Methodical Closers", "Touchdown Waiting To Happen", "Little Threat", "All Flash, No Finish"],
  },
  {
    name: "Air or Ground",
    x: "advanced.passEpaAdj",
    y: "advanced.rushEpaAdj",
    title: "How the Best Offenses Hurt You",
    subtitle: "Passing strength on one axis, rushing strength on the other.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Ground & Pound", "Pick Your Poison", "Offensive Crisis", "Air Raid Territory"],
  },
  {
    name: "Tempo Check",
    x: "stats.pace",
    y: "ratings.adjO",
    title: "Does Playing Fast Actually Make You Better?",
    subtitle: "Tempo is style; offensive rating tells us whether that style works.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Slow but Sharp", "Fast and Dangerous", "Slow and Stuck", "Fast but Wasteful"],
  },
  {
    name: "Passing Lean",
    x: "stats.passRate",
    y: "ratings.adjO",
    title: "Do the Best Offenses Need to Throw?",
    subtitle: "Passing tendency compared with the quality of the offense it produces.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Efficient Balance", "Elite Through the Air", "Conservative & Limited", "Throwing Without Results"],
  },
  {
    name: "Resume Reality",
    x: "ratings.sor",
    y: "ratings.adjEM",
    title: "Who's Proven — and Who's Just Powerful?",
    subtitle: "Resume strength meets the quality PRIME sees on a neutral field.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Better Than Their Resume", "Proven Contender", "Neither", "Resume Merchants"],
  },
  {
    name: "Schedule Opportunity",
    x: "ratings.sosRank",
    y: "ratings.sorRank",
    title: "Who Has Done the Most With Their Schedule?",
    subtitle: "A difficult schedule creates opportunity; Strength of Record shows who actually capitalized.",
    xReverse: true,
    yReverse: true,
    quadrants: ["Made the Most of an Easier Slate", "Earned It the Hard Way", "Missed the Opportunity", "Brutal Schedule"],
  },
  {
    name: "Hidden Field Edge",
    x: "advanced.fieldPos",
    y: "ratings.adjEM",
    title: "Who Quietly Wins the Field Position Battle?",
    subtitle: "Field position can make an already-good team even harder to beat.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Winning The Hard Way", "Complete Advantage", "Needs Help", "Field Position Carrying"],
  },
  {
    name: "Defensive Identity",
    x: "advanced.successAdjAllowed",
    y: "advanced.defExp",
    title: "How Defenses Take Away Offense",
    subtitle: "Who wins down to down, who erases explosives — and who does both.",
    xReverse: true,
    yReverse: false,
    quadrants: ["No Big Plays, Still Leaky", "Shut-Down Unit", "Target Practice", "Wins Down to Down"],
  },
  {
    name: "Chaos Creators",
    x: "advanced.defHavoc",
    y: "ratings.adjD",
    title: "Which Defenses Wreck Games?",
    subtitle: "Havoc measures disruption; defensive rating shows whether the whole unit holds up.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Sound & Steady", "Nightmare Fuel", "Easy Living", "Chaos or Bust"],
  },
  {
    name: "Big-Play Prevention",
    x: "stats.explosivePlayRateAllowed",
    y: "ratings.adjD",
    title: "Who Takes Away the Big Play?",
    subtitle: "The best defenses make opponents earn every yard instead of giving away explosives.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Strong but Leaky", "Complete Defenses", "Target Practice", "Limits Explosives, Needs More"],
  },
  {
    name: "Down-to-Down Defense",
    x: "stats.successRateAllowed",
    y: "ratings.adjD",
    title: "Who Gets Stops Down After Down?",
    subtitle: "Success Rate allowed reveals which defenses consistently keep opponents off schedule.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Other Strengths Carrying", "Complete Defenses", "Leaky Defenses", "Sound, Needs More"],
  },
  {
    name: "Stops Without Turnovers",
    x: "exploratory.takeawayRate",
    y: "exploratory.seriesStopRate",
    title: "Can They Get Stops Without Turnovers?",
    subtitle: "Series stops show repeatable defense; takeaways show the extra chaos layered on top.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Sound Without Turnovers", "Complete Disruption", "Can't Get Stops", "Turnover Reliant"],
  },
  {
    name: "Closing the Door",
    x: "advanced.defHavoc",
    y: "advanced.defFin",
    title: "Which Defenses Actually End Drives?",
    subtitle: "Creating chaos matters most when scoring chances still die.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Red-Zone Toughness", "Drive Killers", "Passive & Soft", "Disruptive but Leaky"],
  },
  {
    name: "Stay Ahead",
    x: "exploratory.longDownAvoidanceRate",
    y: "exploratory.seriesConversionRate",
    title: "Which Offenses Stay Ahead of the Chains?",
    subtitle: "Avoiding long downs should turn into more sustained series.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Converts The Hard Way", "Stays Ahead & Sustains", "Series Problems", "Ahead Of Chains, Not Finishing"],
  },
  {
    name: "Drive Survival",
    x: "exploratory.recoveryRate",
    y: "exploratory.seriesConversionRate",
    title: "Which Offenses Recover When a Drive Goes Sideways?",
    subtitle: "The best units survive bad plays without losing the series.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Stays On Schedule", "Hard To Kill", "Three & Out Territory", "Gets Off The Mat"],
  },
  {
    name: "Clean Football",
    x: "exploratory.cleanDriveRate",
    y: "exploratory.driveKillerRate",
    title: "Who Gets Out of Their Own Way?",
    subtitle: "Clean drives reveal the teams avoiding self-inflicted damage.",
    xReverse: false,
    yReverse: true,
    quadrants: ["Messy but Survives", "Clean Football", "Self Destruct Button", "One Mistake Away"],
  },
  {
    name: "Boom or Bust",
    x: "exploratory.explosiveDependency",
    y: "exploratory.failureBurden",
    title: "Who's Living on Big Plays?",
    subtitle: "Explosive dependence shows which offenses may be fragile underneath the highlights.",
    xReverse: false,
    yReverse: true,
    quadrants: ["Steady & Efficient", "Explosive Without The Damage", "Grinding Through Mistakes", "Boom or Bust"],
  },
  {
    name: "Series Control",
    x: "exploratory.longDownCreationRate",
    y: "exploratory.seriesStopRate",
    title: "Which Defenses Control the Series?",
    subtitle: "Create bad downs, then prove you can actually finish the stop.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Gets Off The Field", "Drive Killers", "Can't Get A Stop", "Creates Long Downs, Can't Finish"],
  },
  {
    name: "Pressure to Possessions",
    x: "exploratory.takeawayRate",
    y: "exploratory.failurePressure",
    title: "Which Defenses Turn Pressure Into Possessions?",
    subtitle: "Creating failed plays is useful; takeaways are the payoff.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Pressure Without Payoff", "Creates Chaos", "No Resistance", "Turnover Hunters"],
  },
  {
    name: "Ball Security",
    x: "exploratory.turnoverRate",
    y: "exploratory.cleanDriveRate",
    title: "Which Offenses Protect the Football?",
    subtitle: "Ball security and clean drives expose self-inflicted offensive damage.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Clean Until Disaster", "Takes Care Of Business", "Giveaway Machine", "Ugly but Safe"],
  },
  {
    name: "Hard to Kill",
    x: "exploratory.recoveryRate",
    y: "exploratory.driveKillerRate",
    title: "Which Offenses Are Hardest to Kill?",
    subtitle: "Recovery rate shows who can absorb a mistake before the drive collapses.",
    xReverse: false,
    yReverse: true,
    quadrants: ["Rarely Needs Saving", "Hard To Kill", "One Mistake = Punt", "Escapes Trouble, Eventually Dies"],
  },
  {
    name: "Flag Battle",
    x: "exploratory.penaltyRate",
    y: "exploratory.penaltiesDrawnRate",
    title: "Who Wins the Flag Battle?",
    subtitle: "The best combination is simple: commit fewer and make opponents commit more.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Flag Fest", "Disciplined Agitators", "Sloppy Football", "Clean & Quiet"],
  },
  {
    name: "Built to Last",
    x: "exploratory.explosiveDependency",
    y: "ratings.adjO",
    title: "Which Offenses Are Built to Last?",
    subtitle: "Elite offense with less dependence on explosive plays is harder to derail when the big plays disappear.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Elite but Volatile", "Built to Last", "Boom or Bust", "Limited but Stable"],
  },
  {
    name: "Big-Play Impact",
    x: "stats.adjustedExplosivenessOffense",
    y: "ratings.adjO",
    title: "Does Explosiveness Actually Drive Elite Offense?",
    subtitle: "Adjusted big-play ability compared with the overall quality of the offense.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Efficient Without Explosives", "Pick Your Poison", "No Juice", "Boom or Bust"],
  },
  {
    name: "Explosiveness Reality Check",
    x: "stats.explosivePlayRate",
    y: "stats.adjustedExplosivenessOffense",
    title: "Whose Explosiveness Survives Adjustment?",
    subtitle: "Raw big-play rate can be schedule driven; adjustment shows whose explosiveness still holds up.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Better Than the Raw Numbers", "Actually Explosive", "Not Explosive", "Raw Numbers Flatter Them"],
  },
  {
    name: "Efficiency Reality Check",
    x: "stats.successRate",
    y: "advanced.successAdj",
    title: "Whose Efficiency Survives Adjustment?",
    subtitle: "Raw Success Rate can flatter an easy schedule; adjustment shows what remains.",
    xReverse: false,
    yReverse: false,
    quadrants: ["Better Than the Raw Numbers", "Legit Efficiency", "Struggling", "Schedule Boosted"],
  },
  {
    name: "Explosive Defense Reality Check",
    x: "stats.explosivePlayRateAllowed",
    y: "stats.adjustedExplosivenessDefense",
    title: "Who Really Suppresses Explosive Plays?",
    subtitle: "Raw explosive rate allowed is schedule dependent; adjustment separates opponent quality from real prevention.",
    xReverse: true,
    yReverse: false,
    quadrants: ["Looks Worse Than Reality", "Legit Big-Play Defense", "Actually Vulnerable", "Raw Numbers Flatter Them"],
  },
];

const PRESET_SECTIONS = [
  {
    title: "Power & Résumé",
    description: "Who's actually good, who's earned it, and who's been tested.",
    presets: ["Battle Tested", "Complete Teams", "Resume Reality", "Schedule Opportunity", "Hidden Field Edge"],
  },
  {
    title: "Offense Stories",
    description: "How teams create, sustain, and finish offense.",
    presets: ["Offensive Identity", "Every-Down Value", "Cashing In", "Big Plays to Points", "Air or Ground", "Built to Last", "Big-Play Impact", "Tempo Check", "Passing Lean"],
  },
  {
    title: "Defense Stories",
    description: "How teams prevent efficiency, create chaos, and finish stops.",
    presets: ["Defensive Identity", "Chaos Creators", "Big-Play Prevention", "Down-to-Down Defense", "Stops Without Turnovers", "Closing the Door"],
  },
  {
    title: "Drive DNA",
    description: "Why possessions survive, stall, or self-destruct.",
    presets: ["Stay Ahead", "Drive Survival", "Clean Football", "Boom or Bust", "Series Control", "Pressure to Possessions", "Ball Security", "Hard to Kill", "Flag Battle"],
  },
  {
    title: "Reality Checks",
    description: "Where raw impressions change after opponent adjustment.",
    presets: ["Explosiveness Reality Check", "Efficiency Reality Check", "Explosive Defense Reality Check"],
  },
] as const;

const PRESET_BY_NAME = new Map(PRESETS.map((preset) => [preset.name, preset]));

function humanize(key: string) {
  if (KNOWN_LABELS[key]) return KNOWN_LABELS[key];
  const raw = key.split(".").pop() ?? key;
  return raw
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/EPA/gi, "EPA")
    .replace(/Ypp/gi, "YPP")
    .replace(/Adj\b/gi, "Adjusted")
    .replace(/Pct\b/gi, "%")
    .replace(/Sor\b/gi, "SOR")
    .replace(/Sos\b/gi, "SOS")
    .replace(/Cfp\b/gi, "CFP")
    .replace(/\bOff\b/gi, "Offense")
    .replace(/\bDef\b/gi, "Defense")
    .replace(/\bEpa\b/gi, "EPA")
    .replace(/\bRush\b/gi, "Rush")
    .replace(/\bPass\b/gi, "Pass")
    .replace(/^./, (letter) => letter.toUpperCase());
}

function metricFormat(key: string): MetricFormat {
  const lower = key.toLowerCase();
  if (
    lower === "advanced.offexp" ||
    lower === "advanced.defexp" ||
    lower === "stats.adjustedexplosivenessoffense" ||
    lower === "stats.adjustedexplosivenessdefense"
  ) return "number3";
  if (lower.endsWith("rank") || lower.includes("rank.")) return "rank";
  if (lower.endsWith("rankchange")) return "integer";
  if (
    lower.includes("success") ||
    lower.includes("explosiveplayrate") ||
    lower.includes("havocrate") ||
    lower.includes("passrate") ||
    lower.includes("cfpchancepct")
  ) {
    return "percent";
  }
  return "number";
}

function metricGroup(prefix: string) {
  if (prefix === "ratings") return "Ratings & Résumé";
  if (prefix === "stats") return "Team Stats";
  if (prefix === "exploratory") return "Exploratory";
  return "Advanced";
}

function formatValue(value: number, metric: Metric | undefined, compact = false) {
  if (!Number.isFinite(value)) return "—";
  if (metric?.format === "percent") return `${(value * 100).toFixed(compact ? 0 : 1)}%`;
  if (metric?.format === "number3") return value.toFixed(3);
  if (metric?.format === "rank" || metric?.format === "integer") return Math.round(value).toString();
  const abs = Math.abs(value);
  if (compact && abs >= 100) return Math.round(value).toString();
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function median(values: number[]) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function extent(values: number[]) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1] as const;
  if (min === max) {
    const pad = Math.abs(min) > 1 ? Math.abs(min) * 0.08 : 1;
    return [min - pad, max + pad] as const;
  }
  const pad = (max - min) * 0.075;
  return [min - pad, max + pad] as const;
}

function closestRows<T>(season: { weeks: number[]; byWeek: Record<string, T[]> } | null, week: number): T[] {
  if (!season?.weeks?.length) return [];
  const eligible = season.weeks.filter((item) => item <= week);
  const resolved = eligible.length ? eligible[eligible.length - 1] : season.weeks[0];
  return season.byWeek[String(resolved)] ?? [];
}

function collectNumeric(
  target: Record<string, number | null>,
  prefix: string,
  row: Record<string, unknown> | undefined,
  exclude: Set<string> = META_KEYS
) {
  if (!row) return;
  for (const [key, value] of Object.entries(row)) {
    if (exclude.has(key)) continue;
    if (typeof value === "number" || value === null) target[`${prefix}.${key}`] = value as number | null;
  }
}

function buildMetricCatalog(points: TeamPoint[]) {
  const keys = new Set<string>();
  for (const point of points) Object.keys(point.values).forEach((key) => keys.add(key));

  return [...keys]
    .filter((key) => points.some((point) => Number.isFinite(point.values[key])))
    .map((key): Metric => {
      const exploratory = EXPLORATORY_METRICS.get(key);
      if (exploratory) return { key, ...exploratory };
      const prefix = key.split(".")[0];
      return { key, label: humanize(key), group: metricGroup(prefix), format: metricFormat(key) };
    })
    .sort((a, b) => a.group.localeCompare(b.group) || a.label.localeCompare(b.label));
}

function blobToDataUrl(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve(String(reader.result));
    reader.readAsDataURL(blob);
  });
}

export default function ChartsClient() {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState("");
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
  const [weeklyStats, setWeeklyStats] = useState<TeamStatsWeeklySeason | null>(null);
  const [seasonStats, setSeasonStats] = useState<TeamStatsSeason | null>(null);
  const [advanced, setAdvanced] = useState<AdvancedSeason | null>(null);
  const [exploratory, setExploratory] = useState<ExploratorySeason | null>(null);
  const [advancedStatus, setAdvancedStatus] = useState<"loading" | "ready" | "locked" | "missing">("loading");
  const [exploratoryStatus, setExploratoryStatus] = useState<"loading" | "ready" | "locked" | "missing">("loading");
  const [loadedYear, setLoadedYear] = useState("");
  const [week, setWeek] = useState(0);
  const [xMetric, setXMetric] = useState("ratings.sosRank");
  const [yMetric, setYMetric] = useState("ratings.adjEM");
  const [conference, setConference] = useState("ALL");
  const [xReverse, setXReverse] = useState(true);
  const [yReverse, setYReverse] = useState(false);
  const [showGuides, setShowGuides] = useState(true);
  const [showQuadrants, setShowQuadrants] = useState(true);
  const [logoSize, setLogoSize] = useState(34);
  const [aspect, setAspect] = useState<Aspect>("4:3");
  const [title, setTitle] = useState("Who's Strong — and Who's Been Tested?");
  const [subtitle, setSubtitle] = useState("Power rating meets the difficulty of the schedule already played.");
  const [quadTL, setQuadTL] = useState("Beating Up Cupcakes");
  const [quadTR, setQuadTR] = useState("Battle Tested");
  const [quadBL, setQuadBL] = useState("Bad & Untested");
  const [quadBR, setQuadBR] = useState("Schedule From Hell");
  const [hovered, setHovered] = useState<HoveredPoint | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportMessage, setExportMessage] = useState("");

  useEffect(() => {
    let active = true;
    getMeta()
      .then((meta) => {
        if (!active) return;
        const available = [...new Set([...(meta.rankingsYears ?? []), ...(meta.advancedYears ?? [])])].sort((a, b) => b - a);
        setYears(available);
        if (available.length) setYear(String(available[0]));
      })
      .catch(() => {
        if (active) setExportMessage("Could not load season metadata.");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!year) return;
    let active = true;

    Promise.allSettled([
      getRankingsSeason(year),
      getTeamStatsWeeklySeason(year),
      getTeamStatsSeason(year),
      getAdvancedSeason(year),
      getExploratorySeason(year),
    ]).then(([rankResult, weeklyResult, seasonResult, advancedResult, exploratoryResult]) => {
      if (!active) return;
      if (rankResult.status === "fulfilled") {
        setRankings(rankResult.value);
        const latest = rankResult.value.weeks.at(-1) ?? 0;
        setWeek(latest);
      } else {
        setRankings(null);
      }
      setWeeklyStats(weeklyResult.status === "fulfilled" ? weeklyResult.value : null);
      setSeasonStats(seasonResult.status === "fulfilled" ? seasonResult.value : null);
      if (advancedResult.status === "fulfilled") {
        setAdvanced(advancedResult.value);
        setAdvancedStatus("ready");
      } else {
        setAdvanced(null);
        const message = advancedResult.reason instanceof Error ? advancedResult.reason.message.toLowerCase() : "";
        setAdvancedStatus(message.includes("subscription") || message.includes("sign in") ? "locked" : "missing");
      }
      if (exploratoryResult.status === "fulfilled") {
        setExploratory(exploratoryResult.value);
        setExploratoryStatus("ready");
      } else {
        setExploratory(null);
        const message = exploratoryResult.reason instanceof Error ? exploratoryResult.reason.message.toLowerCase() : "";
        setExploratoryStatus(message.includes("subscription") || message.includes("sign in") ? "locked" : "missing");
      }
      setLoadedYear(year);
    });

    return () => {
      active = false;
    };
  }, [year]);

  const availableWeeks = rankings?.weeks ?? [];

  const points = useMemo(() => {
    if (!rankings || !week) return [] as TeamPoint[];

    const ratingRows = closestRows(rankings, week);
    const statsRows = weeklyStats ? closestRows(weeklyStats, week) : seasonStats?.teams ?? [];
    const advancedRows = closestRows(advanced, week);
    const exploratoryStart = exploratory?.weeks?.[0] ?? week;
    const exploratoryRows = exploratory
      ? aggregateExploratory(exploratory.byWeek, exploratory.weeks, exploratoryStart, week)
      : [];

    const statsById = new Map(statsRows.map((row) => [row.teamId, row]));
    const advancedById = new Map(advancedRows.map((row) => [row.teamId, row]));
    const exploratoryById = new Map(exploratoryRows.map((row) => [row.teamId, row]));

    return ratingRows.map((rating) => {
      const values: Record<string, number | null> = {};
      collectNumeric(values, "ratings", rating as unknown as Record<string, unknown>);
      collectNumeric(values, "stats", statsById.get(rating.teamId) as unknown as Record<string, unknown> | undefined);
      collectNumeric(
        values,
        "advanced",
        advancedById.get(rating.teamId) as unknown as Record<string, unknown> | undefined,
        new Set([...META_KEYS, ...ADVANCED_DUPES])
      );

      const exploratoryRow = exploratoryById.get(rating.teamId);
      if (exploratoryRow) {
        for (const section of SECTIONS) {
          for (const column of section.columns) {
            const value = exploratoryRow[column.key];
            values[`exploratory.${column.key}`] =
              typeof value === "number" && Number.isFinite(value) ? value : null;
          }
        }
      }

      return {
        team: rating.team,
        slug: rating.slug,
        teamId: rating.teamId,
        conf: rating.conf,
        values,
      };
    });
  }, [rankings, weeklyStats, seasonStats, advanced, exploratory, week]);

  const metrics = useMemo(() => buildMetricCatalog(points), [points]);
  const metricMap = useMemo(() => new Map(metrics.map((metric) => [metric.key, metric])), [metrics]);
  const metricGroups = useMemo(() => {
    const groups = new Map<string, Metric[]>();
    for (const metric of metrics) {
      const list = groups.get(metric.group) ?? [];
      list.push(metric);
      groups.set(metric.group, list);
    }
    return [...groups.entries()];
  }, [metrics]);

  const resolvedXMetric = metricMap.has(xMetric) ? xMetric : metrics[0]?.key ?? xMetric;
  const resolvedYMetric = metricMap.has(yMetric)
    ? yMetric
    : metrics[Math.min(1, Math.max(0, metrics.length - 1))]?.key ?? yMetric;
  const loading = !year || loadedYear !== year;

  const conferences = useMemo(
    () => [...new Set(points.map((point) => point.conf).filter(Boolean))].sort((a, b) => a.localeCompare(b)),
    [points]
  );

  const plotted = useMemo(() => {
    return points
      .filter((point) => conference === "ALL" || point.conf === conference)
      .map((point) => ({ ...point, x: point.values[resolvedXMetric], y: point.values[resolvedYMetric] }))
      .filter((point): point is TeamPoint & { x: number; y: number } => Number.isFinite(point.x) && Number.isFinite(point.y));
  }, [points, conference, resolvedXMetric, resolvedYMetric]);

  const xValues = plotted.map((point) => point.x);
  const yValues = plotted.map((point) => point.y);
  const [xMin, xMax] = extent(xValues);
  const [yMin, yMax] = extent(yValues);
  const xMedian = median(xValues);
  const yMedian = median(yValues);

  const dimensions = aspect === "16:9" ? { width: 1600, height: 900 } : aspect === "1:1" ? { width: 1080, height: 1080 } : { width: 1200, height: 900 };
  const margin = { left: 122, right: 58, top: 148, bottom: 104 };
  const plotWidth = dimensions.width - margin.left - margin.right;
  const plotHeight = dimensions.height - margin.top - margin.bottom;

  const scaleX = (value: number) => {
    const ratio = (value - xMin) / (xMax - xMin || 1);
    const normalized = xReverse ? 1 - ratio : ratio;
    return margin.left + normalized * plotWidth;
  };
  const scaleY = (value: number) => {
    const ratio = (value - yMin) / (yMax - yMin || 1);
    const normalized = yReverse ? ratio : 1 - ratio;
    return margin.top + normalized * plotHeight;
  };

  const xTicks = Array.from({ length: 6 }, (_, index) => xMin + ((xMax - xMin) * index) / 5);
  const yTicks = Array.from({ length: 6 }, (_, index) => yMin + ((yMax - yMin) * index) / 5);
  const selectedX = metricMap.get(resolvedXMetric);
  const selectedY = metricMap.get(resolvedYMetric);

  const conferenceLabel = (() => {
    const labels: Record<string, string> = {
      B1G: "Big Ten",
      BIG10: "Big Ten",
      "Big Ten": "Big Ten",
      SEC: "SEC",
      ACC: "ACC",
      B12: "Big 12",
      BIG12: "Big 12",
      "Big 12": "Big 12",
      AAC: "American",
      AMERICAN: "American",
      CUSA: "Conference USA",
      MAC: "MAC",
      MWC: "Mountain West",
      "Mountain West": "Mountain West",
      SBC: "Sun Belt",
      "Sun Belt": "Sun Belt",
      PAC: "Pac-12",
      PAC12: "Pac-12",
      "Pac-12": "Pac-12",
      IND: "Independent",
      Independent: "Independent",
    };
    return labels[conference] ?? conference;
  })();

  const activeFilterLabels = [
    conference !== "ALL" ? `${conferenceLabel} only` : null,
  ].filter((label): label is string => Boolean(label));

  const baseSubtitle = subtitle.trim();
  const resolvedSubtitle = [
    baseSubtitle || null,
    `Through Week ${week}`,
    ...activeFilterLabels,
  ].filter((label): label is string => Boolean(label)).join(" · ");

  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    if (!metricMap.has(preset.x) || !metricMap.has(preset.y)) return;
    setXMetric(preset.x);
    setYMetric(preset.y);
    setTitle(preset.title);
    setSubtitle(preset.subtitle);
    setXReverse(preset.xReverse);
    setYReverse(preset.yReverse);
    setQuadTL(preset.quadrants[0]);
    setQuadTR(preset.quadrants[1]);
    setQuadBL(preset.quadrants[2]);
    setQuadBR(preset.quadrants[3]);
    setShowGuides(true);
    setShowQuadrants(true);
  };

  const cloneSvgWithEmbeddedLogos = async () => {
    if (!svgRef.current) throw new Error("Chart is not ready.");
    const original = svgRef.current;
    const clone = original.cloneNode(true) as SVGSVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(dimensions.width));
    clone.setAttribute("height", String(dimensions.height));

    // A serialized SVG does not inherit the page stylesheet or loaded web fonts.
    // Inline the rendered styles so clipboard/SVG exports match the chart instead
    // of falling back to browser-default serif text.
    const originalNodes = Array.from(original.querySelectorAll("*"));
    const cloneNodes = Array.from(clone.querySelectorAll("*"));
    const exportStyleProperties = [
      "fill",
      "stroke",
      "stroke-width",
      "stroke-dasharray",
      "opacity",
      "font-family",
      "font-size",
      "font-style",
      "font-weight",
      "letter-spacing",
      "text-transform",
    ];

    originalNodes.forEach((sourceNode, index) => {
      const targetNode = cloneNodes[index] as SVGElement | undefined;
      if (!targetNode) return;
      const computed = window.getComputedStyle(sourceNode);
      for (const property of exportStyleProperties) {
        const value = computed.getPropertyValue(property);
        if (value) targetNode.style.setProperty(property, value);
      }
    });

    // Keep export typography deterministic even when browser image rendering
    // cannot access the site's webfont files.
    clone.querySelectorAll("text").forEach((textNode) => {
      textNode.style.fontFamily = "Arial, Helvetica, sans-serif";
    });

    const images = Array.from(clone.querySelectorAll("image"));
    await Promise.all(
      images.map(async (image) => {
        const teamId = image.getAttribute("data-team-id");
        const href = image.getAttribute("href");
        if (!href || href.startsWith("data:")) return;

        const exportUrl = teamId ? `/api/team-logo/${encodeURIComponent(teamId)}` : href;
        const response = await fetch(exportUrl, { cache: "force-cache" });
        if (!response.ok) throw new Error(`Logo export failed: ${response.status}`);
        image.setAttribute("href", await blobToDataUrl(await response.blob()));
      })
    );

    return clone;
  };

  const renderChartPng = async () => {
    const clone = await cloneSvgWithEmbeddedLogos();
    const serialized = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
    const svgUrl = URL.createObjectURL(svgBlob);

    try {
      const image = new Image();
      const loaded = new Promise<void>((resolve, reject) => {
        image.onload = () => resolve();
        image.onerror = () => reject(new Error("Could not render chart image."));
      });
      image.src = svgUrl;
      await loaded;

      const canvas = document.createElement("canvas");
      canvas.width = dimensions.width;
      canvas.height = dimensions.height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas is unavailable.");

      context.drawImage(image, 0, 0, dimensions.width, dimensions.height);

      return await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(
          (result) => (result ? resolve(result) : reject(new Error("Could not create chart image."))),
          "image/png",
          1
        );
      });
    } finally {
      URL.revokeObjectURL(svgUrl);
    }
  };

  const downloadSvg = async () => {
    setExporting(true);
    setExportMessage("");
    try {
      const clone = await cloneSvgWithEmbeddedLogos();
      const serialized = new XMLSerializer().serializeToString(clone);
      const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `prime-${year}-week-${week}-chart.svg`;
      link.click();
      URL.revokeObjectURL(url);
      setExportMessage("SVG exported with embedded team logos.");
    } catch (error) {
      setExportMessage(error instanceof Error ? error.message : "SVG export failed.");
    } finally {
      setExporting(false);
    }
  };

  const copyImage = async () => {
    setExporting(true);
    setExportMessage("");
    try {
      if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
        throw new Error("Image copying is not supported by this browser.");
      }

      const blob = await renderChartPng();
      await navigator.clipboard.write([
        new ClipboardItem({
          "image/png": blob,
        }),
      ]);

      setExportMessage("Chart copied to clipboard.");
    } catch (error) {
      setExportMessage(error instanceof Error ? error.message : "Could not copy chart image.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <SiteHeader tagline="Chart Studio" />
      <main className={styles.page}>
        <section className={styles.mobileUnavailable} aria-labelledby="chartsDesktopOnlyTitle">
          <span className={styles.eyebrow}>PRIME Chart Studio</span>
          <h1 id="chartsDesktopOnlyTitle">Desktop only</h1>
          <p>The chart builder is designed for a larger screen. Open <strong>primecfb.com/charts</strong> on a desktop or laptop to build and export charts.</p>
        </section>

        <section className={styles.intro}>
          <div>
            <span className={styles.eyebrow}>Hidden tool · /charts</span>
            <h1>PRIME Chart Studio</h1>
            <p>Build shareable college football charts from the data already powering PRIME. Every team is plotted with its logo.</p>
          </div>
          <div className={styles.accessState}>
            <span className={!loading && advancedStatus === "ready" && exploratoryStatus === "ready" ? styles.readyDot : styles.mutedDot} />
            <div>
              <strong>
                {loading || advancedStatus === "loading" || exploratoryStatus === "loading"
                  ? "Loading premium metrics…"
                  : advancedStatus === "ready" && exploratoryStatus === "ready"
                    ? "Advanced + Exploratory connected"
                    : "Public data mode"}
              </strong>
              <small>
                {advancedStatus === "ready" && exploratoryStatus === "ready"
                  ? "Advanced and research-stage exploratory metrics are available in the selectors."
                  : advancedStatus === "locked" || exploratoryStatus === "locked"
                    ? "Sign in with Advanced access to unlock premium and exploratory metrics."
                    : "Ratings and public team stats remain available."}
              </small>
            </div>
          </div>
        </section>

        <section className={styles.workspace}>
          <aside className={styles.controls}>
            <div className={styles.controlSection}>
              <h2>Data</h2>
              <div className={styles.twoCol}>
                <label>
                  Season
                  <select value={year} onChange={(event) => setYear(event.target.value)}>
                    {years.map((item) => <option key={item} value={item}>{item}</option>)}
                  </select>
                </label>
                <label>
                  Week
                  <select value={week} onChange={(event) => setWeek(Number(event.target.value))}>
                    {availableWeeks.map((item) => <option key={item} value={item}>Week {item}</option>)}
                  </select>
                </label>
              </div>

              <label>
                Conference
                <select value={conference} onChange={(event) => setConference(event.target.value)}>
                  <option value="ALL">All FBS</option>
                  {conferences.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            </div>

            <div className={styles.controlSection}>
              <div className={styles.sectionHead}>
                <h2>Axes</h2>
                <button
                  type="button"
                  className={styles.textButton}
                  onClick={() => {
                    setXMetric(resolvedYMetric);
                    setYMetric(resolvedXMetric);
                    setXReverse(yReverse);
                    setYReverse(xReverse);
                  }}
                >
                  Swap
                </button>
              </div>

              <label>
                X axis
                <select value={resolvedXMetric} onChange={(event) => setXMetric(event.target.value)}>
                  {metricGroups.map(([group, groupMetrics]) => (
                    <optgroup key={group} label={group}>
                      {groupMetrics.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}
                    </optgroup>
                  ))}
                </select>
              </label>
              <label className={styles.checkRow}>
                <input type="checkbox" checked={xReverse} onChange={(event) => setXReverse(event.target.checked)} />
                Reverse X direction
              </label>

              <label>
                Y axis
                <select value={resolvedYMetric} onChange={(event) => setYMetric(event.target.value)}>
                  {metricGroups.map(([group, groupMetrics]) => (
                    <optgroup key={group} label={group}>
                      {groupMetrics.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}
                    </optgroup>
                  ))}
                </select>
              </label>
              <label className={styles.checkRow}>
                <input type="checkbox" checked={yReverse} onChange={(event) => setYReverse(event.target.checked)} />
                Reverse Y direction
              </label>
            </div>

            <div className={styles.controlSection}>
              <h2>Presets</h2>
              <p className={styles.presetIntro}>Choose the question you want the chart to answer.</p>
              <div className={styles.presetSections}>
                {PRESET_SECTIONS.map((section) => (
                  <section className={styles.presetSection} key={section.title}>
                    <div className={styles.presetSectionHead}>
                      <h3>{section.title}</h3>
                      <p>{section.description}</p>
                    </div>
                    <div className={styles.presetGrid}>
                      {section.presets.map((presetName) => {
                        const preset = PRESET_BY_NAME.get(presetName);
                        if (!preset) return null;
                        return (
                          <button
                            type="button"
                            key={preset.name}
                            disabled={!metricMap.has(preset.x) || !metricMap.has(preset.y)}
                            onClick={() => applyPreset(preset)}
                          >
                            {preset.name}
                          </button>
                        );
                      })}
                    </div>
                  </section>
                ))}
              </div>
            </div>

            <div className={styles.controlSection}>
              <h2>Presentation</h2>
              <label>
                Title
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label>
                Subtitle
                <input value={subtitle} onChange={(event) => setSubtitle(event.target.value)} placeholder={`Through Week ${week}`} />
              </label>
              <div className={styles.twoCol}>
                <label>
                  Aspect
                  <select value={aspect} onChange={(event) => setAspect(event.target.value as Aspect)}>
                    <option value="4:3">4:3</option>
                    <option value="16:9">16:9</option>
                    <option value="1:1">1:1</option>
                  </select>
                </label>
                <label>
                  Logo size
                  <input
                    className={styles.range}
                    type="range"
                    min="20"
                    max="52"
                    step="2"
                    value={logoSize}
                    onChange={(event) => setLogoSize(Number(event.target.value))}
                  />
                </label>
              </div>
              <label className={styles.checkRow}>
                <input type="checkbox" checked={showGuides} onChange={(event) => setShowGuides(event.target.checked)} />
                Median guide lines
              </label>
              <label className={styles.checkRow}>
                <input type="checkbox" checked={showQuadrants} onChange={(event) => setShowQuadrants(event.target.checked)} />
                Quadrant labels
              </label>

              {showQuadrants ? (
                <div className={styles.quadrantInputs}>
                  <input aria-label="Top left quadrant" value={quadTL} onChange={(event) => setQuadTL(event.target.value)} placeholder="Top left" />
                  <input aria-label="Top right quadrant" value={quadTR} onChange={(event) => setQuadTR(event.target.value)} placeholder="Top right" />
                  <input aria-label="Bottom left quadrant" value={quadBL} onChange={(event) => setQuadBL(event.target.value)} placeholder="Bottom left" />
                  <input aria-label="Bottom right quadrant" value={quadBR} onChange={(event) => setQuadBR(event.target.value)} placeholder="Bottom right" />
                </div>
              ) : null}
            </div>

            <div className={styles.exportSection}>
              <button type="button" className={styles.primaryButton} onClick={copyImage} disabled={exporting || !plotted.length}>
                {exporting ? "Preparing…" : "Copy Image"}
              </button>
              <button type="button" className={styles.secondaryButton} onClick={downloadSvg} disabled={exporting || !plotted.length}>
                Download SVG
              </button>
              {exportMessage ? <small>{exportMessage}</small> : null}
            </div>
          </aside>

          <div className={styles.previewColumn}>
            <div className={styles.previewMeta}>
              <span>{loading ? "Loading data…" : `${plotted.length} teams plotted`}</span>
              <span>{selectedX?.label ?? xMetric} × {selectedY?.label ?? yMetric}</span>
            </div>

            <div className={styles.canvasWrap}>
              {hovered ? (
                <div className={styles.hoverCard}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={logoUrl(hovered.teamId, 64)} alt="" />
                  <div>
                    <strong>{hovered.team}</strong>
                    <span>{selectedX?.label}: {formatValue(hovered.x, selectedX)}</span>
                    <span>{selectedY?.label}: {formatValue(hovered.y, selectedY)}</span>
                  </div>
                </div>
              ) : null}

              <svg
                ref={svgRef}
                className={styles.chart}
                viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
                role="img"
                aria-label={`${title}, ${selectedX?.label ?? "X"} versus ${selectedY?.label ?? "Y"}`}
                onMouseLeave={() => setHovered(null)}
              >
                <rect width={dimensions.width} height={dimensions.height} fill="#fbfaf6" />

                <text x={margin.left} y={56} className={styles.svgTitle}>{title || "PRIME Chart"}</text>
                <rect x={margin.left} y={76} width={Math.min(plotWidth * 0.62, 670)} height={6} rx={3} fill="#c99a35" />
                <text x={margin.left} y={112} className={styles.svgSubtitle}>{resolvedSubtitle}</text>

                <g transform={`translate(${dimensions.width - margin.right} 42)`}>
                  <text x={0} y={0} textAnchor="end" className={styles.svgBrand}>PRIME</text>
                  <text x={0} y={25} textAnchor="end" className={styles.svgBrandSub}>COLLEGE FOOTBALL ANALYTICS</text>
                </g>

                {xTicks.map((tick, index) => {
                  const x = scaleX(tick);
                  return (
                    <g key={`x-${index}`}>
                      <line x1={x} x2={x} y1={margin.top} y2={margin.top + plotHeight} stroke="#e3dfd5" strokeWidth={1.4} />
                      <text x={x} y={margin.top + plotHeight + 35} textAnchor="middle" className={styles.svgTick}>
                        {formatValue(tick, selectedX, true)}
                      </text>
                    </g>
                  );
                })}

                {yTicks.map((tick, index) => {
                  const y = scaleY(tick);
                  return (
                    <g key={`y-${index}`}>
                      <line x1={margin.left} x2={margin.left + plotWidth} y1={y} y2={y} stroke="#e3dfd5" strokeWidth={1.4} />
                      <text x={margin.left - 18} y={y + 6} textAnchor="end" className={styles.svgTick}>
                        {formatValue(tick, selectedY, true)}
                      </text>
                    </g>
                  );
                })}

                {showGuides && plotted.length ? (
                  <>
                    <line
                      x1={scaleX(xMedian)}
                      x2={scaleX(xMedian)}
                      y1={margin.top}
                      y2={margin.top + plotHeight}
                      stroke="#7b8fa2"
                      strokeWidth={2.4}
                      strokeDasharray="8 8"
                      opacity={0.72}
                    />
                    <line
                      x1={margin.left}
                      x2={margin.left + plotWidth}
                      y1={scaleY(yMedian)}
                      y2={scaleY(yMedian)}
                      stroke="#7b8fa2"
                      strokeWidth={2.4}
                      strokeDasharray="8 8"
                      opacity={0.72}
                    />
                  </>
                ) : null}

                {showQuadrants ? (
                  <>
                    <text
                      x={margin.left + 16}
                      y={margin.top + 26}
                      textAnchor="start"
                      className={styles.svgQuadrant}
                    >
                      {quadTL}
                    </text>
                    <text
                      x={margin.left + plotWidth - 16}
                      y={margin.top + 26}
                      textAnchor="end"
                      className={styles.svgQuadrant}
                    >
                      {quadTR}
                    </text>
                    <text
                      x={margin.left + 16}
                      y={margin.top + plotHeight - 16}
                      textAnchor="start"
                      className={styles.svgQuadrant}
                    >
                      {quadBL}
                    </text>
                    <text
                      x={margin.left + plotWidth - 16}
                      y={margin.top + plotHeight - 16}
                      textAnchor="end"
                      className={styles.svgQuadrant}
                    >
                      {quadBR}
                    </text>
                  </>
                ) : null}

                {plotted.map((point) => {
                  const x = scaleX(point.x);
                  const y = scaleY(point.y);
                  return (
                    <g
                      key={point.teamId}
                      transform={`translate(${x} ${y})`}
                      className={styles.logoPoint}
                      onMouseEnter={() => setHovered({ ...point, x: point.x, y: point.y })}
                    >
                      <title>{point.team}: {formatValue(point.x, selectedX)} · {formatValue(point.y, selectedY)}</title>
                      <image
                        href={logoUrl(point.teamId, 128)}
                        data-team-id={point.teamId}
                        x={-logoSize / 2}
                        y={-logoSize / 2}
                        width={logoSize}
                        height={logoSize}
                        preserveAspectRatio="xMidYMid meet"
                      />
                    </g>
                  );
                })}

                <text
                  x={margin.left + plotWidth / 2}
                  y={dimensions.height - 35}
                  textAnchor="middle"
                  className={styles.svgAxisTitle}
                >
                  {selectedX?.label ?? xMetric}
                </text>
                <text
                  x={38}
                  y={margin.top + plotHeight / 2}
                  textAnchor="middle"
                  transform={`rotate(-90 38 ${margin.top + plotHeight / 2})`}
                  className={styles.svgAxisTitle}
                >
                  {selectedY?.label ?? yMetric}
                </text>

                <text x={dimensions.width - 58} y={dimensions.height - 24} textAnchor="end" className={styles.svgFooter}>
                  primecfb.com
                </text>
              </svg>

              {!loading && !plotted.length ? (
                <div className={styles.emptyState}>No teams have values for both selected metrics.</div>
              ) : null}
            </div>
          </div>
        </section>
      </main>
      <SiteFooter note="PRIME Chart Studio — internal visualization workspace." />
    </>
  );
}
