"use client";

import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import CfpTeamCell from "@/components/CfpTeamCell";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, useCfpResultsSeason, useProjectionSeason, useRankingsSeason } from "@/lib/data";
import { buildCfpStatusMap } from "@/lib/cfp";
import { columnRange, heatBackground } from "@/lib/heatmap";
import Link from "next/link";
import { ratingsTrustState } from "@/lib/trustState";

type Column = {
  key: "rank" | "team" | "adjEM" | "adjO" | "adjD" | "sos" | "sor" | "proj";
  label: string;
  numeric: boolean;
  defaultDir: "asc" | "desc";
  primary?: boolean;
  rankKey?: "adjORank" | "adjDRank" | "sosRank" | "sorRank" | "projRank";
  secondary?: boolean;
  tooltip?: string;
};

const COLUMNS: Column[] = [
  { key: "rank", label: "Rk", numeric: true, defaultDir: "asc", tooltip: "Overall rank by Net APR" },
  { key: "team", label: "Team", numeric: false, defaultDir: "asc" },
  { key: "adjEM", label: "Net APR", numeric: true, defaultDir: "desc", primary: true, tooltip: "Overall opponent-adjusted possession-efficiency rating. Net APR = Off APR + Def APR, expressed as points per 10 resolved possessions above or below the FBS average." },
  { key: "adjO", label: "Off APR", numeric: true, defaultDir: "desc", rankKey: "adjORank", tooltip: "Opponent-adjusted offensive points per resolved possession, scaled to points per 10 possessions above or below the FBS average. Higher is better." },
  { key: "adjD", label: "Def APR", numeric: true, defaultDir: "desc", rankKey: "adjDRank", tooltip: "Opponent-adjusted points per resolved possession prevented, scaled to points per 10 possessions above or below the FBS average. Higher is better." },
  { key: "sos", label: "SOS", numeric: true, defaultDir: "desc", rankKey: "sosRank", tooltip: "Average PRIME rating (Net APR) of opponents played through the selected week. Higher means a tougher schedule." },
  { key: "sor", label: "SOR", numeric: true, defaultDir: "desc", rankKey: "sorRank", tooltip: "Wins above what an average FBS team would be expected to achieve against the same opponents and game locations. A résumé measure (won/lost), not a performance measure like Net APR. Higher is better." },
  { key: "proj", label: "Proj", numeric: true, defaultDir: "desc", rankKey: "projRank", secondary: true, tooltip: "Projection, not a rating: a forward-looking estimate of team strength (expected margin versus an average FBS team on a neutral field). Early in the season it leans on preseason expectations and fades to this season's performance by Week 4. Net APR is what a team has earned; Projection is what we expect going forward." },
];

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function statText(value: number | null, useSign: boolean, decimals: number) {
  if (na(value)) return "—";
  return useSign ? (value >= 0 ? "+" : "") + value.toFixed(decimals) : value.toFixed(decimals);
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
  const projection = useProjectionSeason(year || null);
  const cfpStatusByTeamId = useMemo(() => buildCfpStatusMap(cfpResults), [cfpResults]);

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

  // Projection is a separate, forward-looking estimate merged in only for display; it never feeds the rating or its ranks.
  const rows = useMemo(() => {
    const base = season && week ? season.byWeek[week] || [] : [];
    const byTeam = new Map((projection?.byWeek?.[week] ?? []).map((p) => [p.team, p]));
    return base.map((t) => {
      const p = byTeam.get(t.team);
      return { ...t, proj: p?.projection ?? null, projRank: p?.rank ?? null };
    });
  }, [season, week, projection]);
  const showProj = Boolean(projection?.byWeek?.[week]);
  const columns = useMemo(() => COLUMNS.filter((c) => c.key !== "proj" || showProj), [showProj]);
  const effectiveSortKey = sortKey === "proj" && !showProj ? "rank" : sortKey;

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
      const av = (a as Record<string, unknown>)[effectiveSortKey] as string | number | null;
      const bv = (b as Record<string, unknown>)[effectiveSortKey] as string | number | null;
      if (na(av)) return na(bv) ? 0 : 1;
      if (na(bv)) return -1;
      if (typeof av === "string") return av.localeCompare(bv as string) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
    return out;
  }, [rows, filter, conference, effectiveSortKey, sortDir]);

  useEffect(() => {
    if (!year) return;
    document.title = `${year} Overall Ratings | PRIME Football`;
  }, [year]);

  function onHeaderClick(col: Column) {
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir(col.defaultDir);
    }
  }

  const trust = season && week ? ratingsTrustState(Number(week), Boolean(season.weekLabels?.[week])) : null;
  const total = rows.length;
  const isFiltered = !!filter.trim() || !!conference;

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#mainContent">Skip to ratings</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <section className="ratings-toolbar container" aria-labelledby="ratingsTitle">
        <div className="ratings-toolbar__heading">
          <h1 id="ratingsTitle">{year ? `${year} Ratings` : "Ratings"}</h1>
          <div className="ratings-toolbar__meta">
            {updatedAt ? (
              <time dateTime={updatedAt}>
                Updated {new Intl.DateTimeFormat("en-US", {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                  timeZone: "America/New_York",
                  timeZoneName: "short",
                }).format(new Date(updatedAt))}
              </time>
            ) : null}
            <Link href="/methodology">Methodology ↗</Link>
          </div>
        </div>

        <div className="ratings-toolbar__controls" aria-label="Ratings filters">
          <div className="ratings-control ratings-control--season">
            <label htmlFor="seasonSelect">Season</label>
            <select
              id="seasonSelect"
              value={year}
              onChange={(e) => {
                setYear(e.target.value);
                setConference("");
              }}
            >
              {[...years].reverse().map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>

          <div className="ratings-control ratings-control--week">
            <label htmlFor="weekSelect">Thru</label>
            <select
              id="weekSelect"
              value={week}
              onChange={(e) => {
                setWeek(e.target.value);
                setConference("");
              }}
            >
              {weeks.map((w) => <option key={w} value={w}>{weekLabel(w, true)}</option>)}
            </select>
          </div>

          <div className="ratings-search">
            <label className="sr-only" htmlFor="filterInput">Search ratings</label>
            <input
              id="filterInput"
              type="search"
              placeholder="Search team"
              autoComplete="off"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>

          <div className="ratings-conference">
            <label className="sr-only" htmlFor="conferenceSelect">Conference</label>
            <select
              id="conferenceSelect"
              aria-label="Filter by conference"
              value={conference}
              onChange={(e) => setConference(e.target.value)}
            >
              <option value="">All conferences</option>
              {conferences.map((conf) => <option key={conf} value={conf}>{conf}</option>)}
            </select>
          </div>

          <span className="ratings-toolbar__count" aria-live="polite">
            {isFiltered ? `${filtered.length}/${total}` : total}
          </span>
        </div>
      </section>

      <div className="container">
      {trust ? (
        <div className={`trust-state trust-state--${trust.level}`} role="note">
          <span className="trust-state__label">{weekLabel(Number(week), true)} · {trust.label}</span>
          <span>{trust.detail}</span>
          <span className="trust-state__links">
            <Link href="/network">Why early ranks move</Link> · <Link href="/methodology">Methodology</Link>
          </span>
        </div>
      ) : null}
      </div>


      <main id="mainContent" className="table-main container">
        <div className="table-scroll" role="region" aria-label="College football overall ratings table" tabIndex={0}>
          <table id="ratingsTable" className="data-table">
            <caption className="sr-only">College football overall ratings</caption>
            <thead>
              <tr>
                {columns.slice(0, 2).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={effectiveSortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
                <th scope="col" className="num record-cell">W-L</th>
                {columns.slice(2).map((col) => (
                  <HeaderCell key={col.key} col={col} sortKey={effectiveSortKey} sortDir={sortDir} onClick={onHeaderClick} />
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 9 }).map((_, i) => (
                  <tr key={i} className="skeleton-row">
                    {Array.from({ length: columns.length + 1 }).map((__, c) => (
                      <td key={c}>
                        <span className="skeleton-bar" style={{ width: (c === 1 ? 70 : 40 + ((c * 13) % 30)) + "%" }} />
                      </td>
                    ))}
                  </tr>
                ))
              ) : filtered.length === 0 ? (
                <tr className="empty-row">
                  <td colSpan={columns.length + 1}>No teams match the current filters.</td>
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
                    <CfpTeamCell
                      team={t.team}
                      teamId={t.teamId}
                      slug={t.slug}
                      conf={t.conf}
                      status={cfpStatusByTeamId.get(t.teamId)}
                      year={year}
                    />
                    <td className="num record-cell">{t.record}</td>
                    <StatCell value={t.adjEM} rank={t.rank} primary useSign decimals={1} metricKey="adjEM" bg={heatBackground(t.adjEM, ranges.adjEM)} />
                    <StatCell value={t.adjO} rank={t.adjORank} useSign decimals={2} metricKey="adjO" bg={heatBackground(t.adjO, ranges.adjO)} />
                    <StatCell value={t.adjD} rank={t.adjDRank} useSign decimals={2} metricKey="adjD" bg={heatBackground(t.adjD, ranges.adjD)} />
                    <StatCell value={t.sos} rank={t.sosRank} useSign decimals={1} metricKey="sos" bg={heatBackground(t.sos, ranges.sos)} />
                    <StatCell value={t.sor} rank={t.sorRank} useSign decimals={1} metricKey="sor" bg={heatBackground(t.sor, ranges.sor)} />
                    {showProj ? <StatCell value={t.proj} rank={t.projRank} useSign decimals={1} metricKey="proj" secondary /> : null}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>

      <section className="ratings-glossary container" aria-labelledby="ratingsGlossaryTitle">
        <div className="ratings-glossary__heading">
          <span className="eyebrow">Quick Reference</span>
          <h2 id="ratingsGlossaryTitle">Ratings glossary</h2>
        </div>
        <div className="ratings-glossary__grid">
          <div><strong>APR</strong><span>Adjusted Possession Rating — PRIME’s opponent-adjusted possession-efficiency rating system.</span></div>
          <div><strong>Net APR</strong><span>The overall team-strength rating. Net APR = Off APR + Def APR. Zero is FBS average; higher is better.</span></div>
          <div><strong>Off APR</strong><span>Opponent-adjusted offensive points per resolved possession, expressed per 10 resolved possessions above or below FBS average.</span></div>
          <div><strong>Def APR</strong><span>Opponent-adjusted points prevented per resolved possession, expressed per 10 resolved possessions above or below FBS average. Higher is better.</span></div>
          <div><strong>Resolved possession</strong><span>A possession with a usable offensive scoring outcome in the rating model. APR uses offensive drive points rather than defensive or special-teams scores.</span></div>
          <div><strong>SOS</strong><span>Strength of Schedule — average PRIME rating of opponents played through the selected week. Higher means a tougher schedule.</span></div>
          <div><strong>SOR</strong><span>Strength of Record — wins above what an average FBS team would be expected to achieve against the same opponents and game locations.</span></div>
          <div><strong>Projection</strong><span>Not a rating. A forward-looking estimate of team strength (expected margin against an average FBS team on a neutral field). Overall Rating shows what a team has earned this season; Projection is what we expect going forward, and leans on preseason information until about Week 4.</span></div>
        </div>
        <Link className="utility-link" href="/methodology">Full methodology ↗</Link>
      </section>

      <aside className="premium-teaser container" aria-label="PRIME Advanced analytics preview">
        <div className="premium-teaser__copy">
          <span className="premium-teaser__title">The overall rating tells you who is good. PRIME Advanced tells you why.</span>
          <span className="premium-teaser__text">Break teams down by offense, defense, success rate, explosiveness, finishing drives, field position and custom week ranges.</span>
        </div>
        <Link className="premium-teaser__link" href="/advanced">Explore PRIME Advanced</Link>
      </aside>

      <div id="methodology" tabIndex={-1}>
        <SiteFooter note="Ratings and W-L include completed FBS-vs-FBS games only; FCS opponents are excluded. Early-season estimates are provisional, and SOS/SOR omit games without pregame opponent ratings. Off APR and Def APR are recursively opponent-adjusted possession-efficiency ratings based on offensive drive points per resolved possession and scaled per 10 possessions; higher is better for both. Net APR = Off APR + Def APR. SOR is wins above an average team on the same schedule -- a résumé measure, separate from Net APR's performance measure." />
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
      className={[col.numeric ? "num" : "", `${col.key}-cell`, "sortable", "metric-cell", col.secondary ? "secondary-col" : ""].filter(Boolean).join(" ")}
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
  secondary,
}: {
  secondary?: boolean;
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
      className={"num stat-cell metric-cell" + (primary ? " primary" : "") + (secondary ? " secondary-col" : "")}
      data-metric-key={metricKey}
      style={bg ? { backgroundColor: bg } : undefined}
    >
      {statText(value, useSign, decimals)}
      {!na(rank) ? <span className="rank-sub">({rank})</span> : null}
    </td>
  );
}