"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, prefetchAllAdvanced, useAdvancedSeason } from "@/lib/data";
import type { AdvancedRow } from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

const FORMATTERS: Record<string, (v: number | null) => string> = {
  signed1: (v) => (na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1)),
  signed2: (v) => (na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(2)),
  plain1: (v) => (na(v) ? "—" : v.toFixed(1)),
  pct1: (v) => (na(v) ? "—" : (v * 100).toFixed(1) + "%"),
};

type ColKind = "snapshot" | "rate" | "split" | "constant-null";

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
};

type Tab = { label: string; primaryKey: string; columns: AdvColumn[] };

const TABS: Record<string, Tab> = {
  general: {
    label: "General",
    primaryKey: "cff",
    columns: [
      { key: "cff", label: "CFF", fmt: "signed1", primary: true, rankable: true, kind: "snapshot", tooltip: "Real Simple Rating System (SRS) score, schedule-adjusted, as of the end week (a model fit can't be split into a sub-range)" },
      { key: "sos", label: "SOS", fmt: "signed1", rankable: true, kind: "rate", num: ["opponentSrsSum"], den: ["opponentSrsCount"], tooltip: "Strength of schedule: average real SRS of opponents played in the selected weeks" },
      { key: "fieldPos", label: "Field Pos", fmt: "signed1", rankable: true, kind: "snapshot", tooltip: "Real opponent-adjusted starting field position edge, as of the end week. Research-only model, independently validated this session" },
      { key: "pace", label: "Pace", fmt: "plain1", rankable: true, kind: "rate", num: ["offPlays"], den: ["games"], tooltip: "Real offensive plays per game in the selected weeks" },
      { key: "top", label: "TOP", fmt: "pct1", rankable: true, kind: "rate", num: ["possessionSeconds"], den: ["possessionSecondsTotal"], tooltip: "Time of possession — real share of game clock this team's offense held the ball, summed from actual drive lengths, in the selected weeks" },
      { key: "st", label: "ST", fmt: "signed1", kind: "constant-null", tooltip: "No special-teams data exists anywhere in this project yet — intentionally left blank rather than invented" },
    ],
  },
  offense: {
    label: "Offense",
    primaryKey: "off",
    columns: [
      { key: "off", label: "Off", fmt: "signed1", primary: true, rankable: true, kind: "snapshot", tooltip: "Real schedule-adjusted yards-per-possession edge (offense), as of the end week. Research-only model, independently validated" },
      { key: "offSuccess", label: "Success", fmt: "pct1", rankable: true, kind: "rate", num: ["successNum"], den: ["successDen"], tooltip: "Real offensive success rate in the selected weeks (raw, not opponent-adjusted)" },
      { key: "offPassSuccess", label: "Pass", fmt: "pct1", rankable: true, kind: "rate", num: ["passSuccessNum"], den: ["passSuccessDen"], tooltip: "Real passing success rate in the selected weeks (raw)" },
      { key: "offRushSuccess", label: "Run", fmt: "pct1", rankable: true, kind: "rate", num: ["rushSuccessNum"], den: ["rushSuccessDen"], tooltip: "Real rushing success rate in the selected weeks (raw)" },
      { key: "offPassRate", label: "Pass | Run Split", fmt: "split0", kind: "rate", num: ["dropbacks"], den: ["dropbacks", "rushAttempts"], tooltip: "Real offensive tendency — share of real plays that were dropbacks vs. rush attempts in the selected weeks" },
      { key: "offExp", label: "Exp", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Real schedule-adjusted explosiveness edge (offense), as of the end week. Research-only model, independently validated" },
      { key: "offFin", label: "Fin", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Real schedule-adjusted finishing-drives edge (offense), as of the end week. Research-only model, independently validated" },
    ],
  },
  defense: {
    label: "Defense",
    primaryKey: "def",
    columns: [
      { key: "def", label: "Def", fmt: "signed1", primary: true, rankable: true, kind: "snapshot", tooltip: "Real schedule-adjusted yards-per-possession edge (defense). Higher is better — a positive value means the defense beat expectation. Research-only model, independently validated" },
      { key: "defSuccess", label: "Success", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["successNumA"], den: ["successDenA"], tooltip: "Real success rate allowed in the selected weeks (raw, not opponent-adjusted)" },
      { key: "defPassSuccess", label: "Pass", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["passSuccessNumA"], den: ["passSuccessDenA"], tooltip: "Real passing success rate allowed in the selected weeks (raw)" },
      { key: "defRushSuccess", label: "Run", fmt: "pct1", rankable: true, lowerBetter: true, kind: "rate", num: ["rushSuccessNumA"], den: ["rushSuccessDenA"], tooltip: "Real rushing success rate allowed in the selected weeks (raw)" },
      { key: "defPassRate", label: "Pass | Run Split", fmt: "split0", kind: "rate", num: ["dropbacksFaced"], den: ["dropbacksFaced", "rushAttemptsFaced"], tooltip: "Real opponent tendency against this defense in the selected weeks" },
      { key: "defExp", label: "Exp", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Real schedule-adjusted explosiveness-allowed edge. Higher is better. Research-only model, independently validated" },
      { key: "defFin", label: "Fin", fmt: "signed2", rankable: true, kind: "snapshot", tooltip: "Real schedule-adjusted finishing-drives-allowed edge. Higher is better. Research-only model, independently validated" },
    ],
  },
};

function sumField(wk: Record<string, number>, fields: string[]): number {
  let total = 0;
  fields.forEach((f) => {
    if (wk[f] !== undefined) total += wk[f];
  });
  return total;
}

function rate(num: number, den: number): number | null {
  return den > 0 ? num / den : null;
}

type Aggregated = {
  team: string; slug: string; teamId: number; conf: string;
  record: string; wins: number;
  [key: string]: unknown;
};

// Stable empty fallbacks -- `season?.weeks ?? []` would otherwise create a
// new array/object every render while unloaded, defeating memoization below.
const EMPTY_WEEKS: number[] = [];
const EMPTY_BY_WEEK: Record<string, AdvancedRow[]> = {};

export default function AdvancedPage() {
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<string>("");
  const [startWeek, setStartWeek] = useState<number | null>(null);
  const [endWeek, setEndWeek] = useState<number | null>(null);
  const [tab, setTab] = useState<keyof typeof TABS>("general");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filter, setFilter] = useState("");
  const [mobileMetric, setMobileMetric] = useState<string>("cff");

  useEffect(() => {
    getMeta().then((meta) => {
      setYears(meta.advancedYears);
      setYear(String(meta.advancedYears[meta.advancedYears.length - 1]));
      // Each season is a ~1MB JSON file -- load them all in the background up
      // front so switching seasons later reads from cache instantly.
      prefetchAllAdvanced(meta.advancedYears);
    });
  }, []);

  // Reads the cache reactively: renders instantly whenever this season was
  // already prefetched or previously viewed, with no fetch or flicker.
  const season = useAdvancedSeason(year || null);
  const loading = !season;
  const weeks = season?.weeks ?? EMPTY_WEEKS;
  const seasonByWeek = season?.byWeek ?? EMPTY_BY_WEEK;

  // Postseason site-weeks are named by CFBD's own playoff round (e.g. "CFP
  // Semifinal") instead of just numbered -- see lib/types.ts's WeekLabels.
  function weekLabel(w: number): string {
    return season?.weekLabels?.[String(w)] || `Week ${w}`;
  }
  function weekRangeLabel(start: number, end: number): string {
    if (start === end) return weekLabel(start);
    return `${weekLabel(start)}–${weekLabel(end)}`;
  }

  const snapshotBySlug = useMemo(() => {
    if (!season) return {};
    const endRows = season.byWeek[String(season.weeks[season.weeks.length - 1])] || [];
    const snap: Record<string, AdvancedRow> = {};
    endRows.forEach((r) => (snap[r.slug] = r));
    return snap;
  }, [season]);

  // Switching years always resets to the full week range, matching the
  // original site. Adjusted during render rather than in an effect (React's
  // documented pattern for this) so it applies the instant `season` is
  // available -- no extra render, no flicker.
  const [rangeYear, setRangeYear] = useState(year);
  if (year !== rangeYear && season) {
    setRangeYear(year);
    setStartWeek(season.weeks[0]);
    setEndWeek(season.weeks[season.weeks.length - 1]);
  }

  const teams = useMemo<Aggregated[]>(() => {
    if (startWeek === null || endWeek === null) return [];
    const selectedWeeks = weeks.filter((w) => w >= startWeek && w <= endWeek);
    const byTeam = new Map<string, { team: string; slug: string; teamId: number; conf: string; wk: Record<string, number> }>();

    selectedWeeks.forEach((wk) => {
      const rows = seasonByWeek[String(wk)] || [];
      rows.forEach((r) => {
        let acc = byTeam.get(r.slug);
        if (!acc) {
          acc = { team: r.team, slug: r.slug, teamId: r.teamId, conf: r.conf, wk: {} };
          byTeam.set(r.slug, acc);
        }
        const wkData = r.wk || {};
        Object.keys(wkData).forEach((k) => {
          acc!.wk[k] = (acc!.wk[k] || 0) + wkData[k];
        });
      });
    });

    const allCols = ([] as AdvColumn[]).concat(TABS.general.columns, TABS.offense.columns, TABS.defense.columns);

    return Array.from(byTeam.values()).map((acc) => {
      const snap = snapshotBySlug[acc.slug];
      const wins = acc.wk.wins || 0;
      const losses = acc.wk.losses || 0;
      const out: Aggregated = {
        team: acc.team, slug: acc.slug, teamId: acc.teamId, conf: acc.conf,
        record: `${wins}-${losses}`, wins,
      };
      allCols.forEach((col) => {
        if (col.kind === "snapshot") {
          const v = snap ? (snap as unknown as Record<string, unknown>)[col.key] : null;
          out[col.key] = na(v) ? null : v;
        } else if (col.kind === "rate") {
          const num = sumField(acc.wk, col.num!);
          const den = sumField(acc.wk, col.den!);
          out[col.key] = rate(num, den);
        } else {
          out[col.key] = null;
        }
      });
      return out;
    });
  }, [seasonByWeek, snapshotBySlug, weeks, startWeek, endWeek]);

  const rankedTeams = useMemo(() => {
    const tabDef = TABS[tab];
    const withRanks = teams.map((t) => ({ ...t }));
    tabDef.columns.forEach((col) => {
      if (!col.rankable) return;
      const ranked = withRanks.filter((t) => !na(t[col.key] as number | null));
      ranked.sort((a, b) => {
        const av = a[col.key] as number;
        const bv = b[col.key] as number;
        return col.lowerBetter ? av - bv : bv - av;
      });
      ranked.forEach((t, i) => {
        t[`_rank_${col.key}`] = i + 1;
      });
      withRanks.forEach((t) => {
        if (t[`_rank_${col.key}`] === undefined) t[`_rank_${col.key}`] = null;
      });
    });
    const primaryCol = tabDef.columns.find((c) => c.primary)!;
    withRanks.forEach((t) => {
      t._rank = t[`_rank_${primaryCol.key}`];
    });
    return withRanks;
  }, [teams, tab]);

  const visibleTeams = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    let out = rankedTeams;
    if (needle) {
      out = out.filter((t) => t.team.toLowerCase().includes(needle) || t.conf.toLowerCase().includes(needle));
    }
    const key = sortKey || "rank";
    const dir = sortDir === "asc" ? 1 : -1;
    out = out.slice().sort((a, b) => {
      const av = key === "rank" ? a._rank : a[key];
      const bv = key === "rank" ? b._rank : b[key];
      if (na(av as number | null)) return na(bv as number | null) ? 0 : 1;
      if (na(bv as number | null)) return -1;
      if (typeof av === "string") return av.localeCompare(bv as string) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
    return out;
  }, [rankedTeams, filter, sortKey, sortDir]);

  function onHeaderClick(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "rank" ? "asc" : "desc");
    }
  }

  const tabDef = TABS[tab];
  const effectiveMobileMetric = tabDef.columns.some((c) => c.key === mobileMetric) ? mobileMetric : tabDef.primaryKey;
  const selectedWeekCount = startWeek !== null && endWeek !== null ? weeks.filter((w) => w >= startWeek && w <= endWeek).length : 0;

  return (
    <>
      <a className="skip-link" href="#advancedTable">Skip to advanced analytics</a>
      <div className="has-mobile-premium-cta">
        <SiteHeader tagline="Advanced CFF Analytics" />
        <SiteNav />

        <nav className="breadcrumbs" aria-label="Breadcrumb">
          <Link href="/">Ratings</Link>
          <span className="crumb-sep">/</span>
          <span className="crumb-current">Advanced CFF</span>
        </nav>

        <section className="advanced-intro">
          <div className="advanced-intro__copy">
            <div className="advanced-intro__eyebrow">
              <span className="eyebrow">Advanced CFF</span>
              <span className="advanced-intro__badge">Beta</span>
            </div>
            <h1>Find the reason behind the rating</h1>
            <p>Separate overall strength into the things that actually drive games: offensive and defensive efficiency, success rate, explosiveness, finishing, field position, pace and selected week ranges.</p>
          </div>
          <div className="advanced-intro__value" aria-label="Advanced analytics views">
            <span className="advanced-intro__chip">General</span>
            <span className="advanced-intro__chip">Offense</span>
            <span className="advanced-intro__chip">Defense</span>
            <span className="advanced-intro__chip">Week ranges</span>
          </div>
        </section>

        <div className="control-bar control-bar--sticky">
          <div className="control-bar__inner">
            <span className="control-label">Season</span>
            <nav className="year-nav" aria-label="Season">
              {years.map((y) => (
                <button
                  key={y}
                  type="button"
                  className={String(y) === year ? "active" : undefined}
                  onClick={() => setYear(String(y))}
                >
                  {y}
                </button>
              ))}
            </nav>
            <div className="filter-box">
              <label className="sr-only" htmlFor="filterInput">Search advanced analytics</label>
              <input
                id="filterInput"
                type="search"
                placeholder="Search team or conference…"
                autoComplete="off"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
            </div>
            <span className="row-count" aria-live="polite">
              {visibleTeams.length} {visibleTeams.length === 1 ? "team" : "teams"} · {startWeek !== null && endWeek !== null ? weekRangeLabel(startWeek, endWeek) : ""} ({selectedWeekCount} {selectedWeekCount === 1 ? "week" : "weeks"})
            </span>
          </div>

          <div className="control-bar__inner control-bar__inner--secondary">
            <span className="control-label">Weeks</span>
            <div className="week-range">
              <span className="control-label week-range__label">Start</span>
              <select
                aria-label="Start week"
                value={startWeek ?? ""}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setStartWeek(v);
                  if (endWeek !== null && v > endWeek) setEndWeek(v);
                }}
              >
                {weeks.map((w) => (
                  <option key={w} value={w}>{weekLabel(w)}</option>
                ))}
              </select>
              <span className="week-range__sep">&ndash;</span>
              <span className="control-label week-range__label">End</span>
              <select
                aria-label="End week"
                value={endWeek ?? ""}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setEndWeek(v);
                  if (startWeek !== null && v < startWeek) setStartWeek(v);
                }}
              >
                {weeks.map((w) => (
                  <option key={w} value={w}>{weekLabel(w)}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="container tab-bar">
            <nav className="tab-nav" aria-label="Analytics phase">
              {Object.entries(TABS).map(([key, def]) => (
                <button
                  key={key}
                  type="button"
                  className={tab === key ? "active" : undefined}
                  onClick={() => {
                    setTab(key as keyof typeof TABS);
                    setSortKey(null);
                    setSortDir("asc");
                  }}
                >
                  {def.label}
                </button>
              ))}
            </nav>
            <p className="adv-note">Rate stats use exactly the selected week range. Opponent-adjusted model stats are snapshots as of the selected end week.</p>
          </div>
        </div>

        <div className="mobile-table-tools advanced-mobile-table-tools container" aria-label="Mobile advanced table display options">
          <label className="mobile-table-tools__label" htmlFor="advancedMobileMetricSelect">Compare</label>
          <select
            id="advancedMobileMetricSelect"
            className="mobile-table-tools__select"
            value={effectiveMobileMetric}
            onChange={(e) => setMobileMetric(e.target.value)}
          >
            {tabDef.columns.map((col) => (
              <option key={col.key} value={col.key}>{col.label}</option>
            ))}
          </select>
          <span className="mobile-table-tools__hint">Choose one metric to compare across every team without horizontal scrolling.</span>
        </div>

        <main id="advancedTable" className="table-main container">
          <div className="table-scroll" role="region" aria-label="Advanced CFF analytics table" tabIndex={0}>
            <table className="data-table adv-table">
              <caption className="sr-only">Advanced CollegeFootballFocus team analytics</caption>
              <thead>
                <tr>
                  <th scope="col" className="num rank-cell sortable" aria-sort={sortKey === "rank" || !sortKey ? (sortDir === "asc" ? "ascending" : "descending") : "none"} onClick={() => onHeaderClick("rank")}>
                    <span>Rk</span>
                    <TipTrigger text={`Rank by ${tabDef.label} primary rating`} />
                    <span className="sort-indicator">{(sortKey === "rank" || !sortKey) ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                  </th>
                  <th scope="col" className="team-cell sortable" onClick={() => onHeaderClick("team")}>
                    <span>Team</span>
                    <span className="sort-indicator">{sortKey === "team" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                  </th>
                  <th scope="col" className="conf-cell sortable" onClick={() => onHeaderClick("conf")}>
                    <span>Conf</span>
                    <span className="sort-indicator">{sortKey === "conf" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                  </th>
                  <th scope="col" className="num record-cell sortable" onClick={() => onHeaderClick("wins")}>
                    <span>Rec</span>
                    <TipTrigger text="Real record within the selected week range" />
                    <span className="sort-indicator">{sortKey === "wins" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                  </th>
                  {tabDef.columns.map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className={"num metric-cell" + (col.rankable ? " sortable" : "")}
                      data-metric-key={col.key}
                      onClick={col.rankable ? () => onHeaderClick(col.key) : undefined}
                    >
                      <span>{col.label}</span>
                      <TipTrigger text={col.tooltip} />
                      {col.rankable ? (
                        <span className="sort-indicator">{sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                      ) : null}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 14 }).map((_, i) => (
                    <tr key={i} className="skeleton-row">
                      {Array.from({ length: 4 + tabDef.columns.length }).map((__, c) => (
                        <td key={c}>
                          <span className="skeleton-bar" style={{ width: (c === 1 ? 75 : 45 + ((c * 11) % 30)) + "%" }} />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : visibleTeams.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={4 + tabDef.columns.length}>No teams match &ldquo;{filter}&rdquo;.</td>
                  </tr>
                ) : (
                  visibleTeams.map((t) => (
                    <tr key={t.slug}>
                      <td className="num rank-cell">{t._rank ? String(t._rank) : "—"}</td>
                      <td className="team-cell">
                        <TeamLink team={t.team} teamId={t.teamId} slug={t.slug} />
                      </td>
                      <td className="conf-cell">{t.conf}</td>
                      <td className="num record-cell">{t.record}</td>
                      {tabDef.columns.map((col) => (
                        <td
                          key={col.key}
                          className={"num stat-cell metric-cell" + (col.primary ? " primary" : "") + (col.key === effectiveMobileMetric ? " mobile-selected-metric" : "")}
                          data-metric-key={col.key}
                        >
                          {col.fmt === "split0" ? splitText(t[col.key] as number | null) : FORMATTERS[col.fmt](t[col.key] as number | null)}
                          {col.rankable ? (
                            <span className="rank-sub">{t[`_rank_${col.key}`] ? ` (${t[`_rank_${col.key}`]})` : ""}</span>
                          ) : null}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </main>

        <aside className="mobile-premium-cta" aria-label="Advanced analytics subscription">
          <div className="mobile-premium-cta__copy">
            <strong>Advanced CFF</strong>
            <span>Built for deeper weekly team analysis</span>
          </div>
        </aside>

        <SiteFooter note="Advanced CFF combines selected-range rate statistics with end-week opponent-adjusted model snapshots. Special teams remains blank until a real source and validated definition are added." />
      </div>
    </>
  );
}

function splitText(v: number | null): string {
  if (na(v)) return "—";
  const p = Math.round(v * 100);
  return `${p}% | ${100 - p}%`;
}
