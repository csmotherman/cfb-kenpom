"use client";

import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, prefetchAllRankings, useRankingsSeason } from "@/lib/data";
import Link from "next/link";

type Column = {
  key: "rank" | "team" | "conf" | "adjEM" | "adjO" | "adjD" | "sos" | "sor";
  label: string;
  numeric: boolean;
  defaultDir: "asc" | "desc";
  primary?: boolean;
  rankKey?: "adjORank" | "adjDRank" | "sosRank" | "sorRank";
  tooltip?: string;
};

const COLUMNS: Column[] = [
  { key: "rank", label: "Rk", numeric: true, defaultDir: "asc", tooltip: "Overall rank by AdjEM, the site's schedule-adjusted strength rating." },
  { key: "team", label: "Team", numeric: false, defaultDir: "asc" },
  { key: "conf", label: "Conf", numeric: false, defaultDir: "asc" },
  { key: "adjEM", label: "AdjEM", numeric: true, defaultDir: "desc", primary: true, tooltip: "Schedule-adjusted point-margin strength from the site's walk-forward SRS model. Higher is better." },
  { key: "adjO", label: "AdjO", numeric: true, defaultDir: "desc", rankKey: "adjORank", tooltip: "Research-stage schedule-adjusted offensive yards-per-play edge. Higher is better; national rank is shown in parentheses." },
  { key: "adjD", label: "AdjD", numeric: true, defaultDir: "desc", rankKey: "adjDRank", tooltip: "Research-stage schedule-adjusted defensive yards-per-play edge. Higher is better; national rank is shown in parentheses." },
  { key: "sos", label: "SOS", numeric: true, defaultDir: "desc", rankKey: "sosRank", tooltip: "Strength of schedule: average SRS strength of opponents played through the selected week." },
  { key: "sor", label: "SOR", numeric: true, defaultDir: "desc", rankKey: "sorRank", tooltip: "Strength of record: wins above what an exactly-average FBS team would be expected to get on this same schedule. A résumé measure (won/lost), not a performance measure like AdjEM. Higher is better." },
];

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function statText(value: number | null, useSign: boolean, decimals: number) {
  if (na(value)) return "—";
  return useSign ? (value >= 0 ? "+" : "") + value.toFixed(decimals) : value.toFixed(decimals);
}

export default function RatingsPage() {
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<string>("");
  const [week, setWeek] = useState<string>("");
  const [sortKey, setSortKey] = useState<Column["key"]>("rank");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filter, setFilter] = useState("");
  const [conference, setConference] = useState("");
  const [mobileMetric, setMobileMetric] = useState<Column["key"]>("adjEM");

  // Query-string init (?q=, ?conf=) can only be read client-side, and there's
  // no external system to subscribe to here -- just a one-time read on mount.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("q")) setFilter(params.get("q")!);
    if (params.get("conf")) setConference(params.get("conf")!);
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    getMeta().then((meta) => {
      setYears(meta.rankingsYears);
      setYear(String(meta.rankingsYears[meta.rankingsYears.length - 1]));
      // Every season is a ~1MB JSON file -- small enough to just load them
      // all in the background up front, so clicking any year later reads
      // from cache instantly instead of waiting on a fetch.
      prefetchAllRankings(meta.rankingsYears);
    });
  }, []);

  // Reads the cache reactively: renders instantly (no fetch, no flicker)
  // whenever this season was already prefetched or previously viewed.
  const season = useRankingsSeason(year || null);
  const loading = !season;
  const weeks = season?.weeks ?? [];

  // Postseason site-weeks are named by CFBD's own playoff round (e.g. "CFP
  // Semifinal") instead of just numbered -- see lib/types.ts's WeekLabels.
  function weekLabel(w: number, long = false): string {
    const label = season?.weekLabels?.[String(w)];
    if (label) return label;
    return long ? `Week ${w}` : `Wk ${w}`;
  }

  // Switching years always jumps to that season's last week, matching the
  // original site. Adjusted during render (React's documented pattern for
  // resetting state when a dependency changes) rather than in an effect, so
  // it applies in the same pass -- no extra render, no flicker -- the moment
  // `season` is available, which (thanks to prefetching) is usually already
  // true the instant `year` changes.
  const [weekYear, setWeekYear] = useState(year);
  if (year !== weekYear && season) {
    setWeekYear(year);
    setWeek(String(season.weeks[season.weeks.length - 1]));
  }

  const rows = useMemo(() => (season && week ? season.byWeek[week] || [] : []), [season, week]);

  const conferences = useMemo(() => {
    const set = new Set<string>();
    rows.forEach((t) => t.conf && set.add(t.conf));
    return Array.from(set).sort();
  }, [rows]);

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    let out = rows;
    if (needle) out = out.filter((t) => t.team.toLowerCase().includes(needle));
    if (conference) out = out.filter((t) => t.conf === conference);
    const dir = sortDir === "asc" ? 1 : -1;
    out = out.slice().sort((a, b) => {
      const av = (a as Record<string, unknown>)[sortKey] as string | number | null;
      const bv = (b as Record<string, unknown>)[sortKey] as string | number | null;
      if (na(av)) return na(bv) ? 0 : 1;
      if (na(bv)) return -1;
      if (typeof av === "string") return av.localeCompare(bv as string) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
    return out;
  }, [rows, filter, conference, sortKey, sortDir]);

  useEffect(() => {
    if (!year) return;
    const title = `${year} College Football Ratings — CollegeFootballFocus`;
    document.title = title;
  }, [year]);

  function onHeaderClick(col: Column) {
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir(col.defaultDir);
    }
  }

  function deltaCell(change: number | null | undefined) {
    if (change === null || change === undefined) return <td className="num delta-cell delta-new">NEW</td>;
    if (change > 0) return <td className="num delta-cell delta-up">▲{change}</td>;
    if (change < 0) return <td className="num delta-cell delta-down">▼{Math.abs(change)}</td>;
    return <td className="num delta-cell delta-flat">—</td>;
  }

  const total = rows.length;
  const isFiltered = !!filter.trim() || !!conference;

  return (
    <>
      <a className="skip-link" href="#mainContent">Skip to ratings</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <section className="ratings-hero container" aria-labelledby="ratingsTitle">
        <div className="ratings-hero__copy">
          <span className="eyebrow">CFF Ratings</span>
          <h1 id="ratingsTitle">{year ? `${year} College Football Ratings` : "College Football Ratings"}</h1>
          <p className="ratings-hero__description">
            A schedule-adjusted view of how strong every FBS team has actually played, updated week by week from real game results.
          </p>
        </div>
        <div className="ratings-hero__meta">
          <span className="ratings-status">
            {loading ? "Loading season…" : `${year} · through ${weekLabel(Number(week), true)} · ${total} teams`}
          </span>
        </div>
      </section>

      <div className="control-bar">
        <div className="control-bar__inner">
          <span className="control-label">Season</span>
          <nav className="year-nav" aria-label="Season">
            {years.map((y) => (
              <button
                key={y}
                type="button"
                className={String(y) === year ? "active" : undefined}
                aria-label={`${y} season`}
                onClick={() => {
                  setYear(String(y));
                  setConference("");
                }}
              >
                {y}
              </button>
            ))}
          </nav>

          <div className="filter-box">
            <label className="sr-only" htmlFor="filterInput">Search ratings</label>
            <input
              id="filterInput"
              type="search"
              placeholder="Search team…"
              autoComplete="off"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>

          <div className="conference-filter">
            <label className="sr-only" htmlFor="conferenceSelect">Conference</label>
            <select
              id="conferenceSelect"
              aria-label="Filter by conference"
              value={conference}
              onChange={(e) => setConference(e.target.value)}
            >
              <option value="">All conferences</option>
              {conferences.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          <span className="row-count" aria-live="polite">
            {isFiltered ? `${filtered.length} of ${total} teams` : `${total} teams`}
          </span>
        </div>

        <div className="control-bar__inner control-bar__inner--secondary">
          <span className="control-label">Week</span>
          <nav className="week-nav" aria-label="Week">
            {weeks.map((w) => {
              const label = weekLabel(w);
              return (
                <button
                  key={w}
                  type="button"
                  className={String(w) === week ? "active" : undefined}
                  aria-label={label}
                  onClick={() => {
                    setWeek(String(w));
                    setConference("");
                  }}
                >
                  {label}
                </button>
              );
            })}
          </nav>
          <p className="control-help">
            Week 0 is opening-week data. Tap or click a metric header to sort. National rank for AdjO, AdjD and SOS appears in parentheses.
          </p>
        </div>
      </div>

      <div className="mobile-table-tools container" aria-label="Mobile table display options">
        <label className="mobile-table-tools__label" htmlFor="mobileMetricSelect">Compare</label>
        <select
          id="mobileMetricSelect"
          className="mobile-table-tools__select"
          value={mobileMetric}
          onChange={(e) => setMobileMetric(e.target.value as Column["key"])}
        >
          <option value="adjEM">Overall rating (AdjEM)</option>
          <option value="adjO">Offense (AdjO)</option>
          <option value="adjD">Defense (AdjD)</option>
          <option value="sos">Strength of schedule</option>
          <option value="sor">Strength of record</option>
        </select>
        <span className="mobile-table-tools__hint">Mobile keeps Rank + Team fixed and lets you choose the comparison stat.</span>
      </div>

      <main id="mainContent" className="table-main container">
        <div className="table-scroll" role="region" aria-label="College football ratings table" tabIndex={0}>
          <table id="ratingsTable" className="data-table">
            <caption className="sr-only">College football opponent-adjusted ratings</caption>
            <thead>
              <tr>
                {COLUMNS.slice(0, 1).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
                <th scope="col" className="num delta-cell">
                  Wk Δ
                  <TipTrigger text="Change in overall rank from the previous week." />
                </th>
                {COLUMNS.slice(1, 3).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
                <th scope="col" className="num record-cell">W-L</th>
                {COLUMNS.slice(3).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="skeleton-row">
                    {Array.from({ length: 10 }).map((__, c) => (
                      <td key={c}>
                        <span className="skeleton-bar" style={{ width: (c === 2 ? 70 : 40 + ((c * 13) % 30)) + "%" }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr className="empty-row">
                  <td colSpan={10}>No teams match the current filters.</td>
                </tr>
              ) : (
                filtered.map((t) => (
                  <tr key={t.slug} className={t.rank !== null && t.rank <= 10 ? "rank-tier-top10" : undefined}>
                    <td className="num rank-cell">{t.rank === null ? "—" : t.rank}</td>
                    {deltaCell(t.rank === null ? undefined : t.rankChange)}
                    <td className="team-cell">
                      <TeamLink team={t.team} teamId={t.teamId} slug={t.slug} />
                    </td>
                    <td className="conf-cell">{t.conf}</td>
                    <td className="num record-cell">{t.record}</td>
                    <StatCell value={t.adjEM} primary useSign decimals={1} metricKey="adjEM" mobileMetric={mobileMetric} />
                    <StatCell value={t.adjO} rank={t.adjORank} useSign decimals={2} metricKey="adjO" mobileMetric={mobileMetric} />
                    <StatCell value={t.adjD} rank={t.adjDRank} useSign decimals={2} metricKey="adjD" mobileMetric={mobileMetric} />
                    <StatCell value={t.sos} rank={t.sosRank} useSign decimals={1} metricKey="sos" mobileMetric={mobileMetric} />
                    <StatCell value={t.sor} rank={t.sorRank} useSign decimals={1} metricKey="sor" mobileMetric={mobileMetric} />
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>

      <aside className="premium-teaser container" aria-label="Advanced analytics preview">
        <div className="premium-teaser__copy">
          <span className="premium-teaser__title">The rating tells you who is good. Advanced CFF tells you why.</span>
          <span className="premium-teaser__text">Break teams down by offense, defense, success rate, explosiveness, finishing drives, field position and custom week ranges.</span>
        </div>
        <Link className="premium-teaser__link" href="/advanced">Explore Advanced</Link>
      </aside>

      <SiteFooter note="CollegeFootballFocus uses real game data. AdjEM is the site's schedule-adjusted SRS strength rating. AdjO/AdjD are research-stage opponent-adjusted efficiency measures. SOR is wins above an average team on the same schedule -- a résumé measure, separate from AdjEM's performance measure." />
    </>
  );
}

function HeaderCell({
  col,
  sortKey,
  sortDir,
  onClick,
}: {
  col: Column;
  sortKey: Column["key"];
  sortDir: "asc" | "desc";
  onClick: (col: Column) => void;
}) {
  const active = sortKey === col.key;
  return (
    <th
      scope="col"
      className={[col.numeric ? "num" : "", `${col.key}-cell`, "sortable", "metric-cell"].filter(Boolean).join(" ")}
      data-metric-key={col.key}
      aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      onClick={() => onClick(col)}
    >
      <span>{col.label}</span>
      {col.tooltip ? <TipTrigger text={col.tooltip} /> : null}
      <span className="sort-indicator" aria-hidden="true">{active ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
    </th>
  );
}

function StatCell({
  value,
  rank,
  primary,
  useSign,
  decimals,
  metricKey,
  mobileMetric,
}: {
  value: number | null;
  rank?: number | null;
  primary?: boolean;
  useSign: boolean;
  decimals: number;
  metricKey: string;
  mobileMetric: string;
}) {
  return (
    <td
      className={"num stat-cell metric-cell" + (primary ? " primary" : "") + (metricKey === mobileMetric ? " mobile-selected-metric" : "")}
      data-metric-key={metricKey}
    >
      {statText(value, useSign, decimals)}
      {!na(rank) ? <span className="rank-sub">({rank})</span> : null}
    </td>
  );
}
