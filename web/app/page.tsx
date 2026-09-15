"use client";

import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, useCfpResultsSeason, useRankingsSeason } from "@/lib/data";
import { columnRange, heatBackground } from "@/lib/heatmap";
import Link from "next/link";

type Column = {
  key: "rank" | "team" | "adjEM" | "adjO" | "adjD" | "sos" | "sor";
  label: string;
  numeric: boolean;
  defaultDir: "asc" | "desc";
  primary?: boolean;
  rankKey?: "adjORank" | "adjDRank" | "sosRank" | "sorRank";
  tooltip?: string;
};

const COLUMNS: Column[] = [
  { key: "rank", label: "Rk", numeric: true, defaultDir: "asc", tooltip: "Overall rank by Adj. Net" },
  { key: "team", label: "Team", numeric: false, defaultDir: "asc" },
  { key: "adjEM", label: "Adj. Net", numeric: true, defaultDir: "desc", primary: true, tooltip: "Overall opponent-adjusted rating. Adj. Net = Adj. Off + Adj. Def" },
  { key: "adjO", label: "Adj. Off", numeric: true, defaultDir: "desc", rankKey: "adjORank", tooltip: "Opponent-adjusted offensive rating combining EPA, Success Rate, and Explosiveness. Higher is better." },
  { key: "adjD", label: "Adj. Def", numeric: true, defaultDir: "desc", rankKey: "adjDRank", tooltip: "Opponent-adjusted defensive rating combining EPA, Success Rate, and Explosiveness. Higher is better." },
  { key: "sos", label: "SOS", numeric: true, defaultDir: "desc", rankKey: "sosRank", tooltip: "Strength of schedule: average SRS strength of opponents played through the selected week." },
  { key: "sor", label: "SOR", numeric: true, defaultDir: "desc", rankKey: "sorRank", tooltip: "Strength of record: wins above what an exactly-average FBS team would be expected to get on this same schedule. A résumé measure (won/lost), not a performance measure like Adj. Net. Higher is better." },
];

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function statText(value: number | null, useSign: boolean, decimals: number) {
  if (na(value)) return "—";
  return useSign ? (value >= 0 ? "+" : "") + value.toFixed(decimals) : value.toFixed(decimals);
}

type CfpStatus = "champion" | "runnerUp" | "participant" | undefined;

function cfpCellClass(status: CfpStatus): string {
  if (status === "champion") return "team-cell team-cell--cfp-champion";
  if (status === "runnerUp") return "team-cell team-cell--cfp-runner-up";
  if (status === "participant") return "team-cell team-cell--cfp";
  return "team-cell";
}

function cfpCellTitle(status: CfpStatus, year: string): string | undefined {
  if (status === "champion") return `${year} National Champion`;
  if (status === "runnerUp") return `${year} National Championship runner-up`;
  if (status === "participant") return `${year} College Football Playoff field`;
  return undefined;
}

function RankChangeBadge({ change }: { change: number | null | undefined }) {
  if (change === null || change === undefined) {
    return (
      <span className="rank-change rank-change--new" aria-label="New to this week's rankings" title="New to this week's rankings">
        NEW
      </span>
    );
  }

  if (change > 0) {
    return (
      <span className="rank-change rank-change--up" aria-label={`Up ${change} spots from last week`} title={`Up ${change} spots from last week`}>
        ▲{change}
      </span>
    );
  }

  if (change < 0) {
    return (
      <span className="rank-change rank-change--down" aria-label={`Down ${Math.abs(change)} spots from last week`} title={`Down ${Math.abs(change)} spots from last week`}>
        ▼{Math.abs(change)}
      </span>
    );
  }

  return (
    <span className="rank-change rank-change--flat" aria-label="No change from last week" title="No change from last week">
      —
    </span>
  );
}

export default function RatingsPage() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<string>("");
  const [week, setWeek] = useState<string>("");
  const [sortKey, setSortKey] = useState<Column["key"]>("rank");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filter, setFilter] = useState("");
  const [conference, setConference] = useState("");

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
      setUpdatedAt(meta.generatedAt ?? null);
      setYears(meta.rankingsYears);
      setYear(String(meta.rankingsYears[meta.rankingsYears.length - 1]));
    }).catch(setLoadError);
  }, []);

  // Reads the cache reactively: renders instantly (no fetch, no flicker)
  // whenever this season was already prefetched or previously viewed.
  const season = useRankingsSeason(year || null);
  const loading = !season;
  const weeks = season?.weeks ?? [];

  // CFP field/champion/runner-up markers for the selected season -- null
  // (not yet fetched, or that season's CFP hasn't been decided) just means
  // no boxes render, never an error.
  const cfpResults = useCfpResultsSeason(year || null);
  const cfpStatusByTeamId = useMemo(() => {
    const byTeamId = new Map<number, "champion" | "runnerUp" | "participant">();
    if (!cfpResults) return byTeamId;
    for (const team of cfpResults.participants) byTeamId.set(team.teamId, "participant");
    if (cfpResults.runnerUp) byTeamId.set(cfpResults.runnerUp.teamId, "runnerUp");
    if (cfpResults.champion) byTeamId.set(cfpResults.champion.teamId, "champion");
    return byTeamId;
  }, [cfpResults]);

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

  // Each stat column gets its own min/max color scale, computed against the
  // full week's teams (not the filtered/searched subset) so a team's shade
  // stays meaningful when narrowing to one conference.
  const ranges = useMemo(() => ({
    adjEM: columnRange(rows.map((t) => t.adjEM)),
    adjO: columnRange(rows.map((t) => t.adjO)),
    adjD: columnRange(rows.map((t) => t.adjD)),
    sos: columnRange(rows.map((t) => t.sos)),
    sor: columnRange(rows.map((t) => t.sor)),
  }), [rows]);

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
    document.title = `${year} LEILA Ratings`;
  }, [year]);

  function onHeaderClick(col: Column) {
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir(col.defaultDir);
    }
  }

  const total = rows.length;
  const isFiltered = !!filter.trim() || !!conference;

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#mainContent">Skip to ratings</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <section className="ratings-hero container" aria-labelledby="ratingsTitle">
        <div className="ratings-hero__copy">
          <span className="eyebrow">LEILA Ratings</span>
          <h1 id="ratingsTitle">{year ? `${year} LEILA Ratings` : "LEILA Ratings"}</h1>
          <p className="ratings-hero__description">
            Opponent-adjusted team performance, measuring how teams perform relative to what their opponents typically allow.
          </p>
        </div>
        <div className="ratings-hero__meta">
          <span className="ratings-status">
            {loading ? "Loading season…" : `${year} • through ${weekLabel(Number(week), true)} • ${total} teams`}
          </span>
          <Link className="utility-link" href="/methodology">Methodology ↗</Link>
          {updatedAt ? (
            <time className="data-updated" dateTime={updatedAt}>
              Data updated {new Intl.DateTimeFormat("en-US", {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
                timeZone: "America/New_York",
                timeZoneName: "short",
              }).format(new Date(updatedAt))}
            </time>
          ) : null}
        </div>
      </section>

      <section className="onboarding-strip container" aria-label="New here">
        <p className="onboarding-strip__lede">
          <strong>Adj. Net</strong> ranks every FBS team by opponent-adjusted performance &mdash; Adj. Off + Adj. Def,
          accounting for who they played, not just the scoreboard. Hover any column header for what it means.
        </p>
        <div className="onboarding-strip__links">
          <Link href="/predictions">See this week&rsquo;s games →</Link>
          <Link href="/methodology">How the ratings work →</Link>
        </div>
      </section>

      <div className="control-bar">
        <div className="control-bar__inner">
          <span className="control-label">Season</span>
          <nav className="year-nav" aria-label="Season">
            {[...years].reverse().map((y) => (
              <button
                key={y}
                type="button"
                className={String(y) === year ? "active" : undefined}
                aria-label={`${y} season`}
                aria-pressed={String(y) === year}
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
                  aria-pressed={String(w) === week}
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
            Click a column to sort. National metric ranks appear in parentheses.
          </p>
        </div>
      </div>

      <main id="mainContent" className="table-main container">
        <div className="table-scroll" role="region" aria-label="LEILA Ratings college football ratings table" tabIndex={0}>
          <table id="ratingsTable" className="data-table">
            <caption className="sr-only">LEILA Ratings college football rankings</caption>
            <thead>
              <tr>
                {COLUMNS.slice(0, 2).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
                <th scope="col" className="num record-cell">W-L</th>
                {COLUMNS.slice(2).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={sortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 9 }).map((_, i) => (
                  <tr key={i} className="skeleton-row">
                    {Array.from({ length: 8 }).map((__, c) => (
                      <td key={c}>
                        <span className="skeleton-bar" style={{ width: (c === 1 ? 70 : 40 + ((c * 13) % 30)) + "%" }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr className="empty-row">
                  <td colSpan={8}>No teams match the current filters.</td>
                </tr>
              ) : (
                filtered.map((t) => (
                  <tr key={t.slug} className={t.rank !== null && t.rank <= 10 ? "rank-tier-top10" : undefined}>
                    <td className="num rank-cell">
                      <span className="rank-cell-inner">
                        <span className="rank-value">{t.rank === null ? "—" : t.rank}</span>
                        {t.rank !== null ? <RankChangeBadge change={t.rankChange} /> : null}
                      </span>
                    </td>
                    <td
                      className={cfpCellClass(cfpStatusByTeamId.get(t.teamId))}
                      title={cfpCellTitle(cfpStatusByTeamId.get(t.teamId), year)}
                    >
                      <div className="team-cell-stack">
                        <TeamLink team={t.team} teamId={t.teamId} slug={t.slug} />
                        <span className="team-conf-label">{t.conf}</span>
                      </div>
                    </td>
                    <td className="num record-cell">{t.record}</td>
                    <StatCell value={t.adjEM} rank={t.rank} primary useSign decimals={1} metricKey="adjEM" bg={heatBackground(t.adjEM, ranges.adjEM)} />
                    <StatCell value={t.adjO} rank={t.adjORank} useSign decimals={2} metricKey="adjO" bg={heatBackground(t.adjO, ranges.adjO)} />
                    <StatCell value={t.adjD} rank={t.adjDRank} useSign decimals={2} metricKey="adjD" bg={heatBackground(t.adjD, ranges.adjD)} />
                    <StatCell value={t.sos} rank={t.sosRank} useSign decimals={1} metricKey="sos" bg={heatBackground(t.sos, ranges.sos)} />
                    <StatCell value={t.sor} rank={t.sorRank} useSign decimals={1} metricKey="sor" bg={heatBackground(t.sor, ranges.sor)} />
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>

      <aside className="premium-teaser container" aria-label="LEILA Pro advanced analytics preview">
        <div className="premium-teaser__copy">
          <span className="premium-teaser__title">The rating tells you who is good. LEILA Pro tells you why.</span>
          <span className="premium-teaser__text">Break teams down by offense, defense, success rate, explosiveness, finishing drives, field position and custom week ranges.</span>
        </div>
        <Link className="premium-teaser__link" href="/advanced">Explore LEILA Pro</Link>
      </aside>

      <div id="methodology" tabIndex={-1}>
        <SiteFooter note="Ratings and W-L include completed FBS-vs-FBS games only; FCS opponents are excluded. Early-season estimates are provisional, and SOS/SOR omit games without pregame opponent ratings. Adj. Off and Adj. Def are opponent-adjusted ratings combining EPA, Success Rate, and Explosiveness; higher is better for both. Adj. Net = Adj. Off + Adj. Def. SOR is wins above an average team on the same schedule -- a résumé measure, separate from Adj. Net's performance measure." />
      </div>
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
    >
      <button type="button" className="column-sort" onClick={() => onHeaderClickSafe(onClick, col)}>
        {col.label}
        <span className="sort-indicator" aria-hidden="true">{active ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
      </button>
      {col.tooltip ? <TipTrigger text={col.tooltip} /> : null}
    </th>
  );
}

function onHeaderClickSafe(onClick: (col: Column) => void, col: Column) {
  onClick(col);
}

function StatCell({
  value,
  rank,
  primary,
  useSign,
  decimals,
  metricKey,
  bg,
}: {
  value: number | null;
  rank?: number | null;
  primary?: boolean;
  useSign: boolean;
  decimals: number;
  metricKey: string;
  bg?: string;
}) {
  return (
    <td
      className={"num stat-cell metric-cell" + (primary ? " primary" : "")}
      data-metric-key={metricKey}
      style={bg ? { backgroundColor: bg } : undefined}
    >
      {statText(value, useSign, decimals)}
      {!na(rank) ? <span className="rank-sub">({rank})</span> : null}
    </td>
  );
}