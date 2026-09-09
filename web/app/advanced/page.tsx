"use client";

import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, useAdvancedSeason, useRankingsSeason } from "@/lib/data";
import { columnRange, heatBackground } from "@/lib/heatmap";
import type { AdvancedRow } from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

const FORMATTERS: Record<string, (v: number | null) => string> = {
  signed1: (v) => (na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1)),
  signed2: (v) => (na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2)),
  signed3: (v) => (na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(3)),
  plain1: (v) => (na(v) ? "—" : v.toFixed(1)),
  pct1: (v) => (na(v) ? "—" : (v * 100).toFixed(1) + "%"),
  fieldpos: (v) => {
    if (na(v)) return "—";
    if (v > 50) return `Own ${(100 - v).toFixed(1)}`;
    if (v < 50) return `Opp ${v.toFixed(1)}`;
    return "50";
  },
};

type ColKind = "snapshot" | "rate" | "split";
type Perspective = "offense" | "defense" | "margin" | "both";
type TabKey = "general" | "offense" | "defense" | "epa" | "successRate";

type AdvColumn = {
  key: string;
  label: string;
  fmt: keyof typeof FORMATTERS | "split0";
  primary?: boolean;
  rankable?: boolean;
  lowerBetter?: boolean;
  kind: ColKind;
  num?: string[];
  den?: string[];
  tooltip: string;
  sourceRankKey?: "rank" | "adjORank" | "adjDRank";
};

type AdvSection = { title: string; columns: AdvColumn[] };
type Tab = {
  label: string;
  primaryKey: string;
  columns: AdvColumn[];
  sections: AdvSection[];
  note?: string;
  supportsPerspective?: boolean;
};

type MetricDescriptor = {
  prefix: string;
  label: string;
  tip: string;
  fmt?: "signed2" | "signed3";
};

type MetricSection = { title: string; metrics: MetricDescriptor[] };

const CONFIDENCE_TIP = "Opponent-adjusted, confidence-weighted by games played -- effectively raw (minus league average) at 1 game, ramping to fully adjusted by 5.";

const GENERAL_SECTIONS: AdvSection[] = [
  {
    title: "Rating",
    columns: [
      { key: "adjEM", label: "Adj. Net", fmt: "signed1", primary: true, rankable: true, kind: "snapshot", sourceRankKey: "rank", tooltip: "The exact Adj. Net rating and national rank from the Ratings page at the selected end week. Adj. Net = Adj. Off + Adj. Def." },
    ],
  },
  {
    title: "Schedule",
    columns: [
      { key: "sos", label: "SOS", fmt: "signed1", rankable: true, kind: "rate", num: ["opponentSrsSum"], den: ["opponentSrsCount"], tooltip: "Strength of schedule: average real SRS of opponents played in the selected weeks." },
    ],
  },
  {
    title: "Game Profile",
    columns: [
      { key: "pace", label: "Pace", fmt: "plain1", rankable: true, kind: "rate", num: ["offPlays"], den: ["offGames"], tooltip: "Offensive plays per game with available play-by-play in the selected weeks." },
      { key: "top", label: "Time of Poss", fmt: "pct1", rankable: true, kind: "rate", num: ["possessionSeconds"], den: ["possessionSecondsTotal"], tooltip: "Time of possession: share of game clock this team's offense held the ball in the selected weeks." },
    ],
  },
  {
    title: "Field Position",
    columns: [
      { key: "fieldPos", label: "Adj", fmt: "signed1", rankable: true, kind: "snapshot", tooltip: "Opponent-adjusted starting field-position edge, as of the end week. Research-stage model." },
      { key: "offFieldPosRaw", label: "Off Start", fmt: "fieldpos", rankable: true, lowerBetter: true, kind: "rate", num: ["fieldPosSum"], den: ["fieldPosCount"], tooltip: "Average offensive starting field position, shown as a yard line. Lower is better." },
      { key: "defFieldPosRaw", label: "Opp Start", fmt: "fieldpos", rankable: true, kind: "rate", num: ["fieldPosSumA"], den: ["fieldPosCountA"], tooltip: "Average opponent starting field position, shown as a yard line. Higher (deeper in their own territory) is better." },
    ],
  },
];

const OFFENSE_SECTIONS: AdvSection[] = [
  {
    title: "Overall",
    columns: [
      { key: "adjO", label: "Adj. Off", fmt: "signed2", primary: true, rankable: true, kind: "snapshot", sourceRankKey: "adjORank", tooltip: "The exact Adj. Off rating and national rank from the Ratings page at the selected end week." },
      { key: "offYpp", label: "YPP", fmt: "plain1", rankable: true, kind: "rate", num: ["yppNum"], den: ["yppDen"], tooltip: "Offensive yards per play in the selected weeks (raw, not opponent-adjusted)." },
      { key: "offSuccess", label: "Success", fmt: "pct1", rankable: true, kind: "rate", num: ["successNum"], den: ["successDen"], tooltip: "Offensive success rate in the selected weeks (raw, not opponent-adjusted)." },
    ],
  },
  {
    title: "Style",
    columns: [
      { key: "offPassSuccess", label: "Pass SR", fmt: "pct1", rankable: true, kind: "rate", num: ["passSuccessNum"], den: ["passSuccessDen"], tooltip: "Passing success rate in the selected weeks (raw)." },
      { key: "offRushSuccess", label: "Rush SR", fmt: "pct1", rankable: true, kind: "rate", num: ["rushSuccessNum"], den: ["rushSuccessDen"], tooltip: "Rushing success rate in the selected weeks (raw)." },
      { key: "offPassRate", label: "Pass | Run", fmt: "split0", kind: "rate", num: ["dropbacks"], den: ["dropbacks", "rushAttempts"], tooltip: "Offensive tendency: share of plays that were dropbacks vs. rush attempts in the selected weeks." },
    ],
  },
  {
    title: "Explosiveness",
    columns: [
      { key: "offExp", label: "Adj", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Schedule-adjusted explosiveness edge (offense), as of the end week. Research-stage model." },
      { key: "offExpRaw", label: "Raw %", fmt: "pct1", rankable: true, kind: "rate", num: ["explosiveNum"], den: ["explosiveDen"], tooltip: "Explosive-play rate in the selected weeks (raw)." },
    ],
  },
  {
    title: "Finishing",
    columns: [
      { key: "offFin", label: "Adj", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Schedule-adjusted finishing-drives edge (offense), as of the end week. Research-stage model." },
      { key: "offFinRaw", label: "Pts/Opp", fmt: "plain1", rankable: true, kind: "rate", num: ["finNum"], den: ["finDen"], tooltip: "Points scored per resolved scoring opportunity in the selected weeks (raw)." },
    ],
  },
  {
    title: "Havoc",
    columns: [
      { key: "offHavoc", label: "Avoid Adj", fmt: "signed3", rankable: true, kind: "snapshot", tooltip: "Opponent-adjusted edge in avoiding TFLs, sacks, and turnovers, as of the end week." },
      { key: "offHavocRaw", label: "Allowed %", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["havocAllowedNum"], den: ["havocAllowedDen"], tooltip: "Share of offensive plays that gave up a TFL, sack, or turnover in the selected weeks. Lower is better." },
    ],
  },
];

const DEFENSE_SECTIONS: AdvSection[] = [
  {
    title: "Overall",
    columns: [
      { key: "adjD", label: "Adj. Def", fmt: "signed2", primary: true, rankable: true, kind: "snapshot", sourceRankKey: "adjDRank", tooltip: "The exact Adj. Def rating and national rank from the Ratings page at the selected end week." },
      { key: "defYpp", label: "YPP Allowed", fmt: "plain1", rankable: true, lowerBetter: true, kind: "rate", num: ["yppNumA"], den: ["yppDenA"], tooltip: "Yards per play allowed in the selected weeks (raw). Lower is better." },
      { key: "defSuccess", label: "Success Allowed", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["successNumA"], den: ["successDenA"], tooltip: "Opponent success rate allowed in the selected weeks (raw). Lower is better." },
    ],
  },
  {
    title: "Opponent Style",
    columns: [
      { key: "defPassSuccess", label: "Pass SR Allowed", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["passSuccessNumA"], den: ["passSuccessDenA"], tooltip: "Passing success rate allowed in the selected weeks (raw). Lower is better." },
      { key: "defRushSuccess", label: "Rush SR Allowed", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["rushSuccessNumA"], den: ["rushSuccessDenA"], tooltip: "Rushing success rate allowed in the selected weeks (raw). Lower is better." },
      { key: "defPassRate", label: "Pass | Run", fmt: "split0", kind: "rate", num: ["dropbacksFaced"], den: ["dropbacksFaced", "rushAttemptsFaced"], tooltip: "Opponent tendency against this defense in the selected weeks." },
    ],
  },
  {
    title: "Explosiveness",
    columns: [
      { key: "defExp", label: "Adj", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Schedule-adjusted explosiveness-suppression edge. Higher is better." },
      { key: "defExpRaw", label: "Allowed %", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["explosiveNumA"], den: ["explosiveDenA"], tooltip: "Explosive-play rate allowed in the selected weeks (raw). Lower is better." },
    ],
  },
  {
    title: "Finishing",
    columns: [
      { key: "defFin", label: "Adj", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Schedule-adjusted finishing-drives suppression edge. Higher is better." },
      { key: "defFinRaw", label: "Pts/Opp", fmt: "plain1", rankable: true, lowerBetter: true, kind: "rate", num: ["finNumA"], den: ["finDenA"], tooltip: "Points allowed per opponent scoring opportunity in the selected weeks. Lower is better." },
    ],
  },
  {
    title: "Havoc",
    columns: [
      { key: "defHavoc", label: "Forced Adj", fmt: "signed3", rankable: true, kind: "snapshot", tooltip: "Opponent-adjusted edge in forcing TFLs, sacks, and turnovers, as of the end week." },
      { key: "defHavocRaw", label: "Forced %", fmt: "pct1", rankable: true, kind: "rate", num: ["havocForcedNum"], den: ["havocForcedDen"], tooltip: "Share of opponent plays turned into a TFL, sack, or turnover in the selected weeks." },
    ],
  },
];

const EPA_METRICS: MetricSection[] = [
  {
    title: "Overall",
    metrics: [
      { prefix: "epa", label: "EPA/Play", fmt: "signed2", tip: "GRID's opponent-adjusted EPA per play (CFBD's ppa model, summed over every clean rush/pass snap)." },
    ],
  },
  {
    title: "Passing",
    metrics: [
      { prefix: "passEpa", label: "EPA/Dropback", tip: "GRID's opponent-adjusted passing EPA per dropback (attempts + sacks)." },
      { prefix: "passEpaDown1", label: "1st Down", tip: "GRID's opponent-adjusted passing EPA per dropback on 1st down." },
      { prefix: "passEpaDown2", label: "2nd Down", tip: "GRID's opponent-adjusted passing EPA per dropback on 2nd down." },
      { prefix: "passEpaDown3", label: "3rd Down", tip: "GRID's opponent-adjusted passing EPA per dropback on 3rd down." },
    ],
  },
  {
    title: "Rushing",
    metrics: [
      { prefix: "rushEpa", label: "EPA/Rush", tip: "GRID's opponent-adjusted rushing EPA per carry." },
      { prefix: "rushEpaDown1", label: "1st Down", tip: "GRID's opponent-adjusted rushing EPA per carry on 1st down." },
      { prefix: "rushEpaDown2", label: "2nd Down", tip: "GRID's opponent-adjusted rushing EPA per carry on 2nd down." },
      { prefix: "rushEpaDown3", label: "3rd Down", tip: "GRID's opponent-adjusted rushing EPA per carry on 3rd down." },
    ],
  },
];

const SUCCESS_METRICS: MetricSection[] = [
  {
    title: "Overall",
    metrics: [
      { prefix: "success", label: "Success Rate", fmt: "signed2", tip: "GRID's opponent-adjusted success rate using down-scaled yardage thresholds." },
    ],
  },
  {
    title: "Passing",
    metrics: [
      { prefix: "passSuccess", label: "Pass Success", tip: "GRID's opponent-adjusted passing success rate." },
      { prefix: "passSuccessDown1", label: "1st Down", tip: "GRID's opponent-adjusted passing success rate on 1st down." },
      { prefix: "passSuccessDown2", label: "2nd Down", tip: "GRID's opponent-adjusted passing success rate on 2nd down." },
      { prefix: "passSuccessDown3", label: "3rd Down", tip: "GRID's opponent-adjusted passing success rate on 3rd down." },
    ],
  },
  {
    title: "Rushing",
    metrics: [
      { prefix: "rushSuccess", label: "Rush Success", tip: "GRID's opponent-adjusted rushing success rate." },
      { prefix: "rushSuccessDown1", label: "1st Down", tip: "GRID's opponent-adjusted rushing success rate on 1st down." },
      { prefix: "rushSuccessDown2", label: "2nd Down", tip: "GRID's opponent-adjusted rushing success rate on 2nd down." },
      { prefix: "rushSuccessDown3", label: "3rd Down", tip: "GRID's opponent-adjusted rushing success rate on 3rd down." },
    ],
  },
];

function pairedSections(source: MetricSection[], perspective: Perspective): AdvSection[] {
  return source.map((section, sectionIndex) => ({
    title: section.title,
    columns: section.metrics.flatMap((metric, metricIndex) => {
      const fmt = metric.fmt ?? "signed3";
      const offense: AdvColumn = {
        key: `${metric.prefix}Adj`,
        label: perspective === "both" ? `${metric.label} Off` : metric.label,
        fmt,
        primary: sectionIndex === 0 && metricIndex === 0 && perspective !== "defense",
        rankable: true,
        kind: "snapshot",
        tooltip: `${metric.tip} Offense. Higher is better. ${CONFIDENCE_TIP}`,
      };
      const defense: AdvColumn = {
        key: `${metric.prefix}AdjAllowed`,
        label: perspective === "both" ? `${metric.label} Def` : metric.label,
        fmt,
        primary: sectionIndex === 0 && metricIndex === 0 && perspective === "defense",
        rankable: true,
        lowerBetter: true,
        kind: "snapshot",
        tooltip: `${metric.tip} Defense allowed. Lower is better. ${CONFIDENCE_TIP}`,
      };
      const margin: AdvColumn = {
        key: `${metric.prefix}Margin`,
        label: metric.label,
        fmt,
        primary: sectionIndex === 0 && metricIndex === 0 && perspective === "margin",
        rankable: true,
        kind: "snapshot",
        tooltip: `${metric.tip} Margin = offense adjusted value minus defense adjusted allowed value. Higher is better. ${CONFIDENCE_TIP}`,
      };
      if (perspective === "offense") return [offense];
      if (perspective === "defense") return [defense];
      if (perspective === "margin") return [margin];
      return [offense, defense];
    }),
  }));
}

function staticTab(label: string, primaryKey: string, sections: AdvSection[], note?: string): Tab {
  return { label, primaryKey, sections, columns: sections.flatMap((section) => section.columns), note };
}

const STATIC_TABS: Record<"general" | "offense" | "defense", Tab> = {
  general: staticTab("General", "adjEM", GENERAL_SECTIONS),
  offense: staticTab("Offense", "adjO", OFFENSE_SECTIONS),
  defense: staticTab("Defense", "adjD", DEFENSE_SECTIONS),
};

const TAB_LABELS: Array<{ key: TabKey; label: string }> = [
  { key: "general", label: "General" },
  { key: "offense", label: "Offense" },
  { key: "defense", label: "Defense" },
  { key: "epa", label: "EPA" },
  { key: "successRate", label: "Success Rate" },
];

function specialTab(key: "epa" | "successRate", perspective: Perspective): Tab {
  const isEpa = key === "epa";
  const sections = pairedSections(isEpa ? EPA_METRICS : SUCCESS_METRICS, perspective);
  const primaryKey = isEpa
    ? (perspective === "defense" ? "epaAdjAllowed" : perspective === "margin" ? "epaMargin" : "epaAdj")
    : (perspective === "defense" ? "successAdjAllowed" : perspective === "margin" ? "successMargin" : "successAdj");
  const directionNote = perspective === "offense"
    ? "Offense: higher is better."
    : perspective === "defense"
      ? "Defense: lower is better."
      : perspective === "margin"
        ? "Margin = offense adjusted value minus defense adjusted allowed value. Higher is better."
        : "Offense: higher is better. Defense: lower is better.";
  return {
    label: isEpa ? "EPA" : "Success Rate",
    primaryKey,
    sections,
    columns: sections.flatMap((section) => section.columns),
    supportsPerspective: true,
    note: isEpa
      ? `${CONFIDENCE_TIP} Every number in this tab is an opponent-adjusted edge. ${directionNote}`
      : `${CONFIDENCE_TIP} ${directionNote}`,
  };
}

const EPA_ALL_COLUMNS = pairedSections(EPA_METRICS, "both").flatMap((section) => section.columns);
const SUCCESS_ALL_COLUMNS = pairedSections(SUCCESS_METRICS, "both").flatMap((section) => section.columns);
const MARGIN_METRICS = [...EPA_METRICS, ...SUCCESS_METRICS].flatMap((section) => section.metrics);
const ALL_COLUMNS: AdvColumn[] = [
  ...STATIC_TABS.general.columns,
  ...STATIC_TABS.offense.columns,
  ...STATIC_TABS.defense.columns,
  ...EPA_ALL_COLUMNS,
  ...SUCCESS_ALL_COLUMNS,
];

function sumField(wk: Record<string, number>, fields: string[]): number {
  let total = 0;
  fields.forEach((field) => {
    if (wk[field] !== undefined) total += wk[field];
  });
  return total;
}

function rate(num: number, den: number): number | null {
  return den > 0 ? num / den : null;
}

type Aggregated = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  record: string;
  wins: number;
  [key: string]: unknown;
};

const EMPTY_WEEKS: number[] = [];
const EMPTY_BY_WEEK: Record<string, AdvancedRow[]> = {};

export default function AdvancedPage() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<string>("");
  const [startWeek, setStartWeek] = useState<number | null>(null);
  const [endWeek, setEndWeek] = useState<number | null>(null);
  const [tab, setTab] = useState<TabKey>("general");
  const [perspective, setPerspective] = useState<Perspective>("offense");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filter, setFilter] = useState("");
  const [conference, setConference] = useState("");

  useEffect(() => {
    getMeta().then((meta) => {
      setUpdatedAt(meta.generatedAt ?? null);
      setYears(meta.advancedYears);
      setYear(String(meta.advancedYears[meta.advancedYears.length - 1]));
    }).catch(setLoadError);
  }, []);

  const season = useAdvancedSeason(year || null);
  const ratingsSeason = useRankingsSeason(year || null);
  const loading = !season || !ratingsSeason;
  const weeks = season?.weeks ?? EMPTY_WEEKS;
  const seasonByWeek = season?.byWeek ?? EMPTY_BY_WEEK;

  function weekLabel(w: number): string {
    return season?.weekLabels?.[String(w)] || `Week ${w}`;
  }

  function weekRangeLabel(start: number, end: number): string {
    if (start === end) return weekLabel(start);
    return `${weekLabel(start)}–${weekLabel(end)}`;
  }

  const snapshotBySlug = useMemo(() => {
    if (!season) return {};
    const endRows = season.byWeek[String(endWeek)] || [];
    const snapshot: Record<string, AdvancedRow> = {};
    endRows.forEach((row) => (snapshot[row.slug] = row));
    return snapshot;
  }, [season, endWeek]);

  const ratingsSnapshotBySlug = useMemo(() => {
    if (!ratingsSeason) return {};
    const endRows = ratingsSeason.byWeek[String(endWeek)] || [];
    return Object.fromEntries(endRows.map((row) => [row.slug, row]));
  }, [ratingsSeason, endWeek]);

  const [rangeYear, setRangeYear] = useState(year);
  if (year !== rangeYear && season) {
    setRangeYear(year);
    setStartWeek(season.weeks[0]);
    setEndWeek(season.weeks[season.weeks.length - 1]);
  }

  const teams = useMemo<Aggregated[]>(() => {
    if (startWeek === null || endWeek === null) return [];
    const selectedWeeks = weeks.filter((week) => week >= startWeek && week <= endWeek);
    const byTeam = new Map<string, { team: string; slug: string; teamId: number; conf: string; wk: Record<string, number> }>();

    selectedWeeks.forEach((week) => {
      const rows = seasonByWeek[String(week)] || [];
      rows.forEach((row) => {
        let acc = byTeam.get(row.slug);
        if (!acc) {
          acc = { team: row.team, slug: row.slug, teamId: row.teamId, conf: row.conf, wk: {} };
          byTeam.set(row.slug, acc);
        }
        const wkData = row.wk || {};
        Object.keys(wkData).forEach((key) => {
          acc!.wk[key] = (acc!.wk[key] || 0) + wkData[key];
        });
      });
    });

    return Array.from(byTeam.values()).map((acc) => {
      const snap = snapshotBySlug[acc.slug];
      const wins = acc.wk.wins || 0;
      const losses = acc.wk.losses || 0;
      const out: Aggregated = {
        team: acc.team,
        slug: acc.slug,
        teamId: acc.teamId,
        conf: acc.conf,
        record: `${wins}-${losses}`,
        wins,
      };

      ALL_COLUMNS.forEach((col) => {
        if (col.kind === "snapshot") {
          const value = snap ? (snap as unknown as Record<string, unknown>)[col.key] : null;
          out[col.key] = na(value) ? null : value;
        } else {
          const num = sumField(acc.wk, col.num!);
          const den = sumField(acc.wk, col.den!);
          out[col.key] = rate(num, den);
        }
      });

      // Ratings page is the single source of truth for the three headline
      // ratings. Advanced keeps its own range-based stats, but these snapshots
      // (and their national ranks) must be identical everywhere.
      const ratingSnap = ratingsSnapshotBySlug[acc.slug];
      out.adjEM = ratingSnap?.adjEM ?? null;
      out.adjO = ratingSnap?.adjO ?? null;
      out.adjD = ratingSnap?.adjD ?? null;
      out.rank = ratingSnap?.rank ?? null;
      out.adjORank = ratingSnap?.adjORank ?? null;
      out.adjDRank = ratingSnap?.adjDRank ?? null;

      MARGIN_METRICS.forEach((metric) => {
        const offenseValue = out[`${metric.prefix}Adj`] as number | null;
        const defenseAllowedValue = out[`${metric.prefix}AdjAllowed`] as number | null;
        out[`${metric.prefix}Margin`] = na(offenseValue) || na(defenseAllowedValue)
          ? null
          : offenseValue - defenseAllowedValue;
      });
      return out;
    });
  }, [seasonByWeek, snapshotBySlug, ratingsSnapshotBySlug, weeks, startWeek, endWeek]);

  const tabDef = useMemo<Tab>(() => {
    if (tab === "epa" || tab === "successRate") return specialTab(tab, perspective);
    return STATIC_TABS[tab];
  }, [tab, perspective]);

  const rankedTeams = useMemo(() => {
    const withRanks = teams.map((team) => ({ ...team }));
    tabDef.columns.forEach((col) => {
      if (!col.rankable) return;
      if (col.sourceRankKey) {
        withRanks.forEach((team) => {
          const sourceRank = team[col.sourceRankKey] as number | null | undefined;
          team[`_rank_${col.key}`] = na(sourceRank) ? null : sourceRank;
        });
        return;
      }
      const ranked = withRanks.filter((team) => !na(team[col.key] as number | null));
      ranked.sort((a, b) => {
        const av = a[col.key] as number;
        const bv = b[col.key] as number;
        return col.lowerBetter ? av - bv : bv - av;
      });
      ranked.forEach((team, index) => {
        team[`_rank_${col.key}`] = index + 1;
      });
      withRanks.forEach((team) => {
        if (team[`_rank_${col.key}`] === undefined) team[`_rank_${col.key}`] = null;
      });
    });
    withRanks.forEach((team) => {
      team._rank = team[`_rank_${tabDef.primaryKey}`];
    });
    return withRanks;
  }, [teams, tabDef]);

  const visibleTeams = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    let out = conference ? rankedTeams.filter((team) => team.conf === conference) : rankedTeams;
    if (needle) {
      out = out.filter((team) => team.team.toLowerCase().includes(needle) || team.conf.toLowerCase().includes(needle));
    }
    const key = sortKey || "rank";
    const direction = sortDir === "asc" ? 1 : -1;
    return out.slice().sort((a, b) => {
      const av = key === "rank" ? a._rank : a[key];
      const bv = key === "rank" ? b._rank : b[key];
      if (na(av as number | null)) return na(bv as number | null) ? 0 : 1;
      if (na(bv as number | null)) return -1;
      if (typeof av === "string") return av.localeCompare(bv as string) * direction;
      return ((av as number) - (bv as number)) * direction;
    });
  }, [rankedTeams, filter, conference, sortKey, sortDir]);

  const columnRanges = useMemo(() => {
    const ranges: Record<string, { min: number; max: number }> = {};
    tabDef.columns.forEach((col) => {
      if (!col.rankable) return;
      ranges[col.key] = columnRange(teams.map((team) => team[col.key] as number | null));
    });
    return ranges;
  }, [teams, tabDef]);

  const sectionStartKeys = useMemo(
    () => new Set(tabDef.sections.map((section) => section.columns[0]?.key).filter(Boolean)),
    [tabDef],
  );

  const conferences = useMemo(() => [...new Set(teams.map((team) => team.conf))].filter(Boolean).sort(), [teams]);

  function onHeaderClick(key: string) {
    if ((sortKey || "rank") === key) {
      setSortDir((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      const column = tabDef.columns.find((col) => col.key === key);
      setSortDir(["rank", "team", "conf"].includes(key) || column?.lowerBetter ? "asc" : "desc");
    }
  }

  function selectTab(nextTab: TabKey) {
    setTab(nextTab);
    setSortKey(null);
    setSortDir("asc");
  }

  function selectPerspective(nextPerspective: Perspective) {
    setPerspective(nextPerspective);
    setSortKey(null);
    setSortDir("asc");
  }

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#advancedTable">Skip to advanced analytics</a>
      <div>
        <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
        <SiteNav />

        <section className="ratings-hero container" aria-labelledby="advancedTitle">
          <div className="ratings-hero__copy">
            <span className="eyebrow">CFF Advanced Analytics</span>
            <h1 id="advancedTitle">{year} College Football Analytics</h1>
            <p className="ratings-hero__description">Compare opponent-adjusted efficiency, success rate, explosiveness, field position, and situational performance across FBS teams.</p>
          </div>
          <div className="ratings-hero__meta">
            <span className="ratings-status">{loading ? "Loading season…" : `${year} • ${startWeek !== null && endWeek !== null ? weekRangeLabel(startWeek, endWeek) : ""} • ${teams.length} teams`}</span>
            <a className="utility-link" href="#methodology">Methodology ↗</a>
            {updatedAt ? <time className="data-updated" dateTime={updatedAt}>Data updated {new Date(updatedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })} UTC</time> : null}
          </div>
        </section>

        <div className="control-bar">
          <div className="control-bar__inner">
            <span className="control-label">Season</span>
            <nav className="year-nav" aria-label="Season">
              {[...years].reverse().map((seasonYear) => (
                <button
                  key={seasonYear}
                  type="button"
                  className={String(seasonYear) === year ? "active" : undefined}
                  aria-pressed={String(seasonYear) === year}
                  onClick={() => { setYear(String(seasonYear)); setConference(""); }}
                >
                  {seasonYear}
                </button>
              ))}
            </nav>
            <div className="filter-box">
              <label className="sr-only" htmlFor="filterInput">Search advanced analytics</label>
              <input id="filterInput" type="search" placeholder="Search team…" autoComplete="off" value={filter} onChange={(event) => setFilter(event.target.value)} />
            </div>
            <div className="conference-filter">
              <label className="sr-only" htmlFor="conferenceSelect">Conference</label>
              <select id="conferenceSelect" value={conference} onChange={(event) => setConference(event.target.value)}>
                <option value="">All conferences</option>
                {conferences.map((conf) => <option key={conf} value={conf}>{conf}</option>)}
              </select>
            </div>
            <span className="row-count" aria-live="polite">
              {filter || conference ? `${visibleTeams.length} of ${teams.length} teams` : `${teams.length} teams`}
            </span>
          </div>

          <div className="control-bar__inner control-bar__inner--secondary advanced-range-row">
            <span className="control-label">Weeks</span>
            <div className="week-range">
              <span className="control-label week-range__label">Start</span>
              <select
                aria-label="Start week"
                value={startWeek ?? ""}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setStartWeek(value);
                  if (endWeek !== null && value > endWeek) setEndWeek(value);
                }}
              >
                {weeks.map((week) => <option key={week} value={week}>{weekLabel(week)}</option>)}
              </select>
              <span className="week-range__sep">–</span>
              <span className="control-label week-range__label">End</span>
              <select
                aria-label="End week"
                value={endWeek ?? ""}
                onChange={(event) => {
                  const value = Number(event.target.value);
                  setEndWeek(value);
                  if (startWeek !== null && value < startWeek) setStartWeek(value);
                }}
              >
                {weeks.map((week) => <option key={week} value={week}>{weekLabel(week)}</option>)}
              </select>
            </div>
          </div>

          <div className="container tab-bar advanced-tab-bar">
            <nav className="tab-nav" aria-label="Analytics category">
              {TAB_LABELS.map(({ key, label }) => (
                <button key={key} type="button" className={tab === key ? "active" : undefined} aria-pressed={tab === key} onClick={() => selectTab(key)}>
                  {label}
                </button>
              ))}
            </nav>

            {tabDef.supportsPerspective ? (
              <div className="advanced-perspective" role="group" aria-label={`${tabDef.label} perspective`}>
                <span className="advanced-perspective__label">View</span>
                {(["offense", "defense", "margin"] as Perspective[]).map((view) => (
                  <button
                    key={view}
                    type="button"
                    className={perspective === view ? "active" : undefined}
                    aria-pressed={perspective === view}
                    onClick={() => selectPerspective(view)}
                  >
                    {view === "offense" ? "Offense" : view === "defense" ? "Defense" : "Margin"}
                  </button>
                ))}
              </div>
            ) : null}

            <p className="adv-note">{tabDef.note ?? "Rate stats use exactly the selected week range. Opponent-adjusted model stats are snapshots as of the selected end week."}</p>
          </div>
        </div>

        <main id="advancedTable" className="table-main container">
          <div className="advanced-table-shell">
            <div className="advanced-table-summary" aria-hidden="true">
              <span>{tabDef.label}</span>
              <span>{tabDef.sections.map((section) => section.title).join(" • ")}</span>
            </div>
            <div className="table-scroll" role="region" aria-label="Advanced CFF analytics table" tabIndex={0}>
              <table className="data-table adv-table" data-view={tab} data-perspective={tabDef.supportsPerspective ? perspective : undefined}>
                <caption className="sr-only">Advanced CollegeFootballFocus team analytics</caption>
                <thead>
                  <tr className="adv-section-row">
                    <th scope="colgroup" colSpan={3} className="adv-section-spacer">Team</th>
                    {tabDef.sections.map((section) => (
                      <th key={section.title} scope="colgroup" colSpan={section.columns.length} className="adv-section-heading">
                        {section.title}
                      </th>
                    ))}
                  </tr>
                  <tr className="adv-column-row">
                    <th scope="col" className="num rank-cell sortable" aria-sort={sortKey === "rank" || !sortKey ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                      <button type="button" className="column-sort" onClick={() => onHeaderClick("rank")}>Rk</button>
                      <TipTrigger text={`Rank by ${tabDef.label} primary rating`} />
                      <span className="sort-indicator">{(sortKey === "rank" || !sortKey) ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                    </th>
                    <th scope="col" className="team-cell sortable" aria-sort={sortKey === "team" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                      <button type="button" className="column-sort" onClick={() => onHeaderClick("team")}>Team</button>
                      <span className="sort-indicator">{sortKey === "team" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                    </th>
                    <th scope="col" className="num record-cell sortable" aria-sort={sortKey === "wins" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                      <button type="button" className="column-sort" onClick={() => onHeaderClick("wins")}>W-L</button>
                      <TipTrigger text="Record within the selected week range" />
                      <span className="sort-indicator">{sortKey === "wins" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                    </th>
                    {tabDef.columns.map((col) => (
                      <th
                        key={col.key}
                        scope="col"
                        className={`num metric-cell${col.rankable ? " sortable" : ""}${sectionStartKeys.has(col.key) ? " section-start" : ""}`}
                        data-metric-key={col.key}
                        aria-sort={sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                      >
                        {col.rankable ? <button type="button" className="column-sort" onClick={() => onHeaderClick(col.key)}>{col.label}</button> : <span>{col.label}</span>}
                        <TipTrigger text={col.tooltip} />
                        {col.rankable ? <span className="sort-indicator">{sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : ""}</span> : null}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    Array.from({ length: 14 }).map((_, rowIndex) => (
                      <tr key={rowIndex} className="skeleton-row">
                        {Array.from({ length: 3 + tabDef.columns.length }).map((__, cellIndex) => (
                          <td key={cellIndex}><span className="skeleton-bar" style={{ width: (cellIndex === 1 ? 75 : 45 + ((cellIndex * 11) % 30)) + "%" }} /></td>
                        ))}
                      </tr>
                    ))
                  ) : visibleTeams.length === 0 ? (
                    <tr className="empty-row">
                      <td colSpan={3 + tabDef.columns.length}>No teams match &ldquo;{filter}&rdquo;.</td>
                    </tr>
                  ) : (
                    visibleTeams.map((team) => (
                      <tr key={team.slug}>
                        <td className="num rank-cell">{team._rank ? String(team._rank) : "—"}</td>
                        <td className="team-cell">
                          <div className="team-cell-stack">
                            <TeamLink team={team.team} teamId={team.teamId} slug={team.slug} />
                            <span className="team-conf-label">{team.conf}</span>
                          </div>
                        </td>
                        <td className="num record-cell">{team.record}</td>
                        {tabDef.columns.map((col) => {
                          const value = team[col.key] as number | null;
                          const rank = team[`_rank_${col.key}`] as number | null;
                          return (
                            <td
                              key={col.key}
                              className={`num stat-cell metric-cell${col.primary ? " primary" : ""}${sectionStartKeys.has(col.key) ? " section-start" : ""}`}
                              data-metric-key={col.key}
                              style={col.rankable ? { backgroundColor: heatBackground(value, columnRanges[col.key], col.lowerBetter) } : undefined}
                            >
                              <span className="metric-value">{col.fmt === "split0" ? splitText(value) : FORMATTERS[col.fmt](value)}</span>
                              {col.rankable && rank ? <span className="rank-sub">#{rank}</span> : null}
                            </td>
                          );
                        })}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </main>

        <div id="methodology" tabIndex={-1}>
          <SiteFooter note="Records and metrics include completed FBS-vs-FBS games only. Advanced CFF combines selected-range rate statistics with end-week opponent-adjusted model snapshots." />
        </div>
      </div>
    </>
  );
}

function splitText(v: number | null): string {
  if (na(v)) return "—";
  const pass = Math.round(v * 100);
  return `${pass}% | ${100 - pass}%`;
}