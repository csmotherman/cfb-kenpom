"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import GameSampleSheet, { type SampleStatus } from "@/components/GameSampleSheet";
import CfpTeamCell from "@/components/CfpTeamCell";
import { TipTrigger } from "@/components/Tooltip";
import { logoUrl } from "@/lib/teamCode";
import { getExploratoryTeamSample, getMeta, useCfpResultsSeason, useExploratorySeason } from "@/lib/data";
import { parseExclusions, serializeExclusions } from "@/lib/custom-sample";
import { sumExploratory, verifyExploratoryParity, type ExploratorySampleData } from "@/lib/exploratory-sample";
import { buildCfpStatusMap } from "@/lib/cfp";
import { ALL_COLUMNS, SECTIONS, SERIES_OFFENSE, aggregateExploratory, buildAggregated, rankExploratory, minimumN, fanTier, type Aggregated } from "@/lib/exploratory";
import { columnRange, heatBackground } from "@/lib/heatmap";
import type { ExploratorySeason, ExploratoryRow } from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

const FORMATTERS: Record<string, (v: number | null) => string> = {
  pct1: (v) => (na(v) ? "—" : (v * 100).toFixed(1) + "%"),
  plain2: (v) => (na(v) ? "—" : v.toFixed(2)),
  plain3: (v) => (na(v) ? "—" : v.toFixed(3)),
  signed3: (v) => (na(v) ? "—" : (v >= 0 ? "+" : "") + v.toFixed(3)),
};

const EMPTY_WEEKS: number[] = [];
const EMPTY_BY_WEEK: Record<string, ExploratoryRow[]> = {};

type TableView = "series" | "possessions" | "style";

const PROFILE_SECTIONS = SECTIONS.slice(0, 5);
const TABLE_VIEWS = [
  { key: "series" as const, label: "Series", sections: PROFILE_SECTIONS.slice(0, 2) },
  { key: "possessions" as const, label: "Possessions", sections: PROFILE_SECTIONS.slice(2, 4) },
  { key: "style" as const, label: "Style & Risk", sections: PROFILE_SECTIONS.slice(4, 5) },
];

export default function ExploratoryClient() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<string>("");
  const [startWeek, setStartWeek] = useState<number | null>(null);
  const [endWeek, setEndWeek] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<string>(SERIES_OFFENSE[0].key);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [filter, setFilter] = useState("");
  const [conference, setConference] = useState("");
  const [profileTeam, setProfileTeam] = useState<Aggregated | null>(null);
  const [tableView, setTableView] = useState<TableView>("series");
  // Custom game samples (independent per team, keyed by slug) -- see docs/advanced_custom_samples.md.
  const [excluded, setExcluded] = useState<Record<string, string[]>>({});
  const [samples, setSamples] = useState<Record<string, { status: SampleStatus; data: ExploratorySampleData | null }>>({});
  const [sheetTeam, setSheetTeam] = useState<{ slug: string; team: string; teamId: number } | null>(null);
  const [urlHydrated, setUrlHydrated] = useState(false);
  const [linkNote, setLinkNote] = useState("");

  useEffect(() => {
    getMeta().then((meta) => {
      setYears(meta.advancedYears);
      const params = new URLSearchParams(window.location.search);
      const shared = parseExclusions(params.get("x"));
      const requested = Number(params.get("y"));
      if (Object.keys(shared).length) setExcluded(shared);
      setUrlHydrated(true);
      const latest = meta.advancedYears[meta.advancedYears.length - 1];
      setYear(String(meta.advancedYears.includes(requested) && Object.keys(shared).length ? requested : latest));
    }).catch(setLoadError);
  }, []);

  useEffect(() => {
    if (!profileTeam) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProfileTeam(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [profileTeam]);

  const season: ExploratorySeason | undefined = useExploratorySeason(year || null);
  const loading = !season;
  const weeks = season?.weeks ?? EMPTY_WEEKS;
  const seasonByWeek = season?.byWeek ?? EMPTY_BY_WEEK;

  const cfpResults = useCfpResultsSeason(year || null);
  const cfpStatusByTeamId = useMemo(() => buildCfpStatusMap(cfpResults), [cfpResults]);

  function weekLabel(w: number): string {
    return season?.weekLabels?.[String(w)] || `Week ${w}`;
  }

  function weekRangeLabel(start: number, end: number): string {
    return start === end ? weekLabel(start) : `${weekLabel(start)}–${weekLabel(end)}`;
  }

  const [rangeYear, setRangeYear] = useState(year);
  if (year !== rangeYear && season) {
    setRangeYear(year);
    setStartWeek(season.weeks[0]);
    setEndWeek(season.weeks[season.weeks.length - 1]);
  }

  // Official season-to-date totals: what an all-games sample must equal.
  const officialFull = useMemo(() => {
    const bySlug = new Map<string, Aggregated>();
    if (weeks.length) aggregateExploratory(seasonByWeek, weeks, weeks[0], weeks[weeks.length - 1]).forEach((team) => bySlug.set(team.slug, team));
    return bySlug;
  }, [seasonByWeek, weeks]);
  // Full season to date: from the first week through the last week that has data.
  const rangeAllowsCustom = startWeek !== null && endWeek !== null && weeks.length > 0 && startWeek === weeks[0] && endWeek >= weeks[weeks.length - 1];

  const ensureSample = useCallback((slug: string, teamId: number) => {
    const key = `${year}:${slug}`;
    setSamples((previous) => (previous[key] ? previous : { ...previous, [key]: { status: "loading", data: null } }));
    getExploratoryTeamSample(year, teamId)
      .then((data) => {
        if (!data) { setSamples((previous) => ({ ...previous, [key]: { status: "unavailable", data: null } })); return; }
        const official = officialFull.get(slug);
        const ok = !!official && verifyExploratoryParity(data, official.wk as Record<string, number>);
        setSamples((previous) => ({ ...previous, [key]: { status: ok ? "ready" : "stale", data: ok ? data : null } }));
      })
      .catch(() => setSamples((previous) => ({ ...previous, [key]: { status: "error", data: null } })));
  }, [year, officialFull]);

  // Load per-team data referenced by a shared link once team ids are known.
  useEffect(() => {
    Object.keys(excluded).forEach((slug) => {
      const team = officialFull.get(slug);
      if (team && !samples[`${year}:${slug}`]) ensureSample(slug, team.teamId);
    });
  }, [excluded, officialFull, samples, year, ensureSample]);

  useEffect(() => {
    if (!urlHydrated || !year) return;
    const params = new URLSearchParams(window.location.search);
    const value = serializeExclusions(excluded);
    if (value) { params.set("x", value); params.set("y", year); } else { params.delete("x"); params.delete("y"); }
    const query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : "") + window.location.hash);
  }, [excluded, year, urlHydrated]);

  function updateExclusions(slug: string, ids: string[]) {
    setExcluded((previous) => {
      const next = { ...previous };
      if (ids.length) next[slug] = ids; else delete next[slug];
      return next;
    });
  }

  function toggleExcluded(slug: string, gameId: string) {
    setExcluded((previous) => {
      const current = previous[slug] ?? [];
      const list = current.includes(gameId) ? current.filter((id) => id !== gameId) : [...current, gameId];
      const next = { ...previous };
      if (list.length) next[slug] = list; else delete next[slug];
      return next;
    });
  }

  function openSampleSheet(team: { slug: string; team: string; teamId: number }) {
    setSheetTeam({ slug: team.slug, team: team.team, teamId: team.teamId });
    ensureSample(team.slug, team.teamId);
  }

  function openProfile(team: Aggregated) {
    setProfileTeam(team);
  }

  async function copyShareLink() {
    try { await navigator.clipboard.writeText(window.location.href); setLinkNote("Link copied"); } catch { setLinkNote("Copy the address bar to share"); }
    setTimeout(() => setLinkNote(""), 2500);
  }

  const teams = useMemo<Aggregated[]>(() => {
    if (startWeek === null || endWeek === null) return [];
    const official = aggregateExploratory(seasonByWeek, weeks, startWeek, endWeek);
    if (!rangeAllowsCustom) return official;
    // A team with a custom sample is recomputed from its chosen games only; every other team is untouched.
    return official.map((team) => {
      const ids = excluded[team.slug];
      const entry = samples[`${year}:${team.slug}`];
      const data = entry?.status === "ready" ? entry.data : null;
      if (!ids?.length || !data || data.meta.season !== Number(year)) return team;
      const drop = new Set(ids);
      const sum = sumExploratory(data, new Set(data.team.games.map((game) => game.g).filter((id) => !drop.has(id))));
      if (sum.included >= sum.total) return team;
      return { ...buildAggregated({ ...team, wk: sum.counts }), _custom: { included: sum.included, total: sum.total } };
    });
  }, [seasonByWeek, weeks, startWeek, endWeek, rangeAllowsCustom, excluded, samples, year]);
  const customTeams = useMemo(() => teams.filter((team) => team._custom), [teams]);
  const customPaused = !rangeAllowsCustom && Object.keys(excluded).length > 0;

  const rankedTeams = useMemo(() => rankExploratory(teams), [teams]);

  const activeView = TABLE_VIEWS.find((view) => view.key === tableView) ?? TABLE_VIEWS[0];
  const activeSections = activeView.sections;
  const activeColumns = activeSections.flatMap((section) => section.columns);
  const activeSectionStartKeys = new Set(activeSections.map((section) => section.columns[0]?.key).filter(Boolean));

  const visibleTeams = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    let out = conference ? rankedTeams.filter((team) => team.conf === conference) : rankedTeams;
    if (needle) {
      out = out.filter((team) => team.team.toLowerCase().includes(needle) || team.conf.toLowerCase().includes(needle));
    }
    const direction = sortDir === "asc" ? 1 : -1;
    return out.slice().sort((a, b) => {
      if (sortKey === "team") return a.team.localeCompare(b.team) * direction;
      const av = a[sortKey] as number | null;
      const bv = b[sortKey] as number | null;
      if (na(av)) return na(bv) ? 0 : 1;
      if (na(bv)) return -1;
      return (av - bv) * direction;
    });
  }, [rankedTeams, filter, conference, sortKey, sortDir]);

  const columnRanges = useMemo(() => {
    const ranges: Record<string, { min: number; max: number }> = {};
    ALL_COLUMNS.forEach((col) => {
      ranges[col.key] = columnRange(
        teams
          .filter((team) => (team[`${col.key}_n`] as number) >= minimumN(col))
          .map((team) => team[col.key] as number | null)
      );
    });
    return ranges;
  }, [teams]);

  const eligibleCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    ALL_COLUMNS.forEach((col) => {
      counts[col.key] = teams.filter(
        (team) => !na(team[col.key] as number | null) && (team[`${col.key}_n`] as number) >= minimumN(col)
      ).length;
    });
    return counts;
  }, [teams]);

  const conferences = useMemo(
    () => [...new Set(teams.map((team) => team.conf))].filter(Boolean).sort(),
    [teams]
  );

  function onHeaderClick(key: string) {
    if (sortKey === key) {
      setSortDir((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      const column = ALL_COLUMNS.find((c) => c.key === key);
      setSortKey(key);
      setSortDir(key === "team" ? "asc" : column?.lowerBetter ? "asc" : "desc");
    }
  }

  function selectTableView(nextView: TableView) {
    const next = TABLE_VIEWS.find((view) => view.key === nextView) ?? TABLE_VIEWS[0];
    const nextColumns = next.sections.flatMap((section) => section.columns);
    setTableView(nextView);
    if (sortKey !== "team" && !nextColumns.some((column) => column.key === sortKey)) {
      const firstColumn = nextColumns[0];
      setSortKey(firstColumn.key);
      setSortDir(firstColumn.lowerBetter ? "asc" : "desc");
    }
  }

  if (loadError) throw loadError;

  const profile = profileTeam ? rankedTeams.find((team) => team.slug === profileTeam.slug) ?? profileTeam : null;
  const activeRangeLabel = startWeek !== null && endWeek !== null
    ? weekRangeLabel(startWeek, endWeek)
    : "Selected weeks";

  return (
    <>
      <a className="skip-link" href="#exploratoryTable">Skip to exploratory analytics</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <section className="ratings-hero container" aria-labelledby="exploratoryTitle">
        <div className="ratings-hero__copy">
          <span className="eyebrow">Advanced · Exploratory</span>
          <h1 id="exploratoryTitle">{year} Series &amp; Drive-Level Statistics</h1>
          <p className="ratings-hero__description">
            Research-stage stats that explain how teams sustain drives, recover after bad downs, stay clean on
            possessions, and create value with or without explosive plays -- built from PRIME&rsquo;s canonical
            play-by-play, not just box-score snapshots.
          </p>
        </div>
        <div className="ratings-hero__meta">
          <span className="ratings-status">
            {loading ? "Loading season…" : `${year} • ${activeRangeLabel} • ${teams.length} teams${customTeams.length ? " • CUSTOM SAMPLES" : ""}`}
          </span>
          <Link className="utility-link" href="/methodology">Methodology ↗</Link>
        </div>
      </section>

      <nav className="exploratory-subnav container" aria-label="Advanced sections">
        <Link href="/advanced">Advanced Analytics</Link>
        <Link href="/advanced/exploratory" className="active" aria-current="page">Exploratory</Link>
      </nav>

      <div className="container exploratory-disclaimer">
        Exploratory metrics are research-stage PRIME statistics designed to measure aspects of football performance
        not fully captured by traditional efficiency metrics. Definitions and methodology may evolve as they are
        validated. Exploratory metrics do not currently affect the overall rating.
      </div>

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
                onClick={() => { setYear(String(seasonYear)); setConference(""); setProfileTeam(null); setExcluded({}); setSheetTeam(null); }}
              >
                {seasonYear}
              </button>
            ))}
          </nav>
          <div className="filter-box">
            <label className="sr-only" htmlFor="exploratoryFilterInput">Search exploratory analytics</label>
            <input
              id="exploratoryFilterInput"
              type="search"
              placeholder="Search team…"
              autoComplete="off"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            />
          </div>
          <div className="conference-filter">
            <label className="sr-only" htmlFor="exploratoryConferenceSelect">Conference</label>
            <select
              id="exploratoryConferenceSelect"
              value={conference}
              onChange={(event) => setConference(event.target.value)}
            >
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
                setProfileTeam(null);
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
                setProfileTeam(null);
                if (startWeek !== null && value < startWeek) setStartWeek(value);
              }}
            >
              {weeks.map((week) => <option key={week} value={week}>{weekLabel(week)}</option>)}
            </select>
          </div>
        </div>
        <p className="container adv-note">
          Every rate sums the raw counts across the selected week range, then divides -- never an average of
          weekly percentages. Grayed-out cells fall below their metric’s sample floor (25 series, 16 recovery opportunities, or 10 for Wave 2; 20 for secondary failure diagnostics) and are shown without a
          national rank. Explosive Dependency is descriptive -- it is not color-coded good or bad.
        </p>
      </div>

      {customTeams.length > 0 || customPaused ? (
        <div className="container">
          <div className="cs-banner" role="status">
            <strong>Custom samples</strong>
            {customTeams.length > 0 ? (
              <div className="cs-banner__teams">
                {customTeams.map((team) => (
                  <button key={team.slug} type="button" className="cs-banner__team" onClick={() => openProfile(team)} aria-label={`Open ${team.team} custom profile`}>
                    {team.team} <span>{(team._custom as { included: number; total: number }).included}/{(team._custom as { included: number; total: number }).total} games</span>
                  </button>
                ))}
              </div>
            ) : null}
            <div className="cs-banner__actions">
              <button type="button" className="cs-link" onClick={copyShareLink}>{linkNote || "Copy link"}</button>
              <button type="button" className="cs-link" onClick={() => { setExcluded({}); setSheetTeam(null); }}>Reset all to full games</button>
            </div>
            <p className="cs-banner__paused">
              {customPaused
                ? "Custom samples are paused while the week range is narrowed. "
                : "Highlighted teams are NOT the official season stats: their rows and rankings here use only the games you chose. PRIME Ratings and predictions are unchanged. "}
              {customPaused ? <button type="button" className="cs-link" onClick={() => { if (weeks.length) { setStartWeek(weeks[0]); setEndWeek(weeks[weeks.length - 1]); } }}>Show the full season</button> : null}
            </p>
          </div>
        </div>
      ) : null}

      <main id="exploratoryTable" className="table-main container">
        <nav className="exploratory-table-tabs" aria-label="Exploratory metric groups" role="tablist">
          {TABLE_VIEWS.map((view) => (
            <button
              key={view.key}
              type="button"
              role="tab"
              aria-selected={tableView === view.key}
              className={tableView === view.key ? "active" : undefined}
              onClick={() => selectTableView(view.key)}
            >
              {view.label}
            </button>
          ))}
        </nav>

        <div className="advanced-table-shell exploratory-table-shell">
          <div className="table-scroll" role="region" aria-label={`${activeView.label} exploratory analytics table`} tabIndex={0}>
            <table className={`data-table adv-table exploratory-table exploratory-table--${tableView}`}>
              <caption className="sr-only">PRIME Exploratory {activeView.label} team analytics</caption>
              <thead>
                <tr className="adv-section-row">
                  <th scope="colgroup" colSpan={2} className="adv-section-spacer">Team</th>
                  {activeSections.map((section) => (
                    <th key={section.title} scope="colgroup" colSpan={section.columns.length} className="adv-section-heading">
                      {section.title.includes(" · ") ? section.title.split(" · ")[1] : section.title}
                    </th>
                  ))}
                </tr>
                <tr className="adv-column-row">
                  <th
                    scope="col"
                    className="team-cell sortable"
                    aria-sort={sortKey === "team" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                  >
                    <button type="button" className="column-sort" onClick={() => onHeaderClick("team")}>Team</button>
                    <span className="sort-indicator">{sortKey === "team" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                  </th>
                  <th scope="col" className="profile-cell">Profile</th>
                  {activeColumns.map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className={`num metric-cell sortable${activeSectionStartKeys.has(col.key) ? " section-start" : ""}`}
                      aria-sort={sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                    >
                      <button type="button" className="column-sort" onClick={() => onHeaderClick(col.key)}>{col.label}</button>
                      <TipTrigger text={col.tooltip} />
                      <span className="sort-indicator">{sortKey === col.key ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({ length: 14 }).map((_, rowIndex) => (
                    <tr key={rowIndex} className="skeleton-row">
                      {Array.from({ length: 2 + activeColumns.length }).map((__, cellIndex) => (
                        <td key={cellIndex}>
                          <span className="skeleton-bar" style={{ width: (cellIndex === 0 ? 75 : 45 + ((cellIndex * 11) % 30)) + "%" }} />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : visibleTeams.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={2 + activeColumns.length}>No teams match &ldquo;{filter}&rdquo;.</td>
                  </tr>
                ) : (
                  visibleTeams.map((team) => (
                    <tr key={team.slug} className={team._custom ? "cs-custom-row" : undefined}>
                      <CfpTeamCell
                        team={team.team}
                        teamId={team.teamId}
                        slug={team.slug}
                        conf={team.conf}
                        status={cfpStatusByTeamId.get(team.teamId)}
                        year={year}
                      />
                      <td className="profile-cell">
                        <button type="button" className="exploratory-profile-button" onClick={() => openProfile(team)}>
                          View Profile
                        </button>

                      </td>
                      {activeColumns.map((col) => {
                        const value = team[col.key] as number | null;
                        const n = team[`${col.key}_n`] as number;
                        const rank = team[`_rank_${col.key}`] as number | null;
                        const smallSample = n < minimumN(col);
                        const format = FORMATTERS[col.fmt ?? "pct1"];
                        return (
                          <td
                            key={col.key}
                            className={`num stat-cell metric-cell${activeSectionStartKeys.has(col.key) ? " section-start" : ""}${smallSample ? " small-sample" : ""}`}
                            style={!smallSample && !col.noHeatmap ? { backgroundColor: heatBackground(value, columnRanges[col.key], col.lowerBetter) } : undefined}
                            title={`N=${n}`}
                          >
                            <span className="metric-value">{format(value)}</span>
                            {rank ? <span className="rank-sub">#{rank}</span> : <span className="rank-sub rank-sub--n">N={n}</span>}
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

      {profile && (
        <div
          className="exploratory-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setProfileTeam(null);
          }}
        >
          <section
            className="exploratory-profile-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="exploratoryProfileTitle"
          >
            <header className="exploratory-profile-header">
              <div className="exploratory-profile-identity">
                <div className="exploratory-profile-logo-shell">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={logoUrl(profile.teamId, 96)} alt="" width={58} height={58} />
                </div>
                <div className="exploratory-profile-heading">
                  <span className="eyebrow">Exploratory Profile · {year}</span>
                  <div className="exploratory-profile-title-row">
                    <h2 id="exploratoryProfileTitle">{profile.team}</h2>
                    {profile._custom ? (
                      <span className="exploratory-profile-custom-badge">
                        Custom · {(profile._custom as { included: number }).included}/{(profile._custom as { total: number }).total}
                      </span>
                    ) : null}
                  </div>
                  <p>{profile.conf} · {activeRangeLabel}</p>
                </div>
              </div>
              <div className="exploratory-profile-actions">
                <button
                  type="button"
                  className={`exploratory-filter-games${profile._custom ? " is-custom" : ""}`}
                  onClick={() => openSampleSheet(profile)}
                >
                  <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
                    <path d="M2 5h8M13 5h3M2 13h3M8 13h8" />
                    <circle cx="11.5" cy="5" r="2" />
                    <circle cx="6.5" cy="13" r="2" />
                  </svg>
                  <span>Filter Games</span>
                  {profile._custom ? <b>{(profile._custom as { included: number }).included}/{(profile._custom as { total: number }).total}</b> : null}
                </button>
                <button
                  type="button"
                  className="exploratory-modal-close"
                  aria-label="Close exploratory profile"
                  onClick={() => setProfileTeam(null)}
                >
                  ×
                </button>
              </div>
            </header>

            <div className="exploratory-profile-legend" aria-label="Profile legend">
              <span><i className="is-strength" /> Strength</span>
              <span><i className="is-average" /> Average</span>
              <span><i className="is-watch" /> Area to watch</span>
              <em>Tap <b>?</b> for metric definitions.</em>
            </div>

            <div className="exploratory-profile-body">
              {PROFILE_SECTIONS.map((group, groupIndex) => (
                <section
                  className={`exploratory-profile-section${groupIndex === PROFILE_SECTIONS.length - 1 ? " exploratory-profile-section--wide" : ""}`}
                  key={group.title}
                >
                  <div className="exploratory-profile-section-head">
                    <h3>{group.title}</h3>
                    <span>{group.columns.length} metrics</span>
                  </div>
                  <table className="exploratory-profile-table">
                    <thead>
                      <tr>
                        <th scope="col">Metric</th>
                        <th scope="col">Value</th>
                        <th scope="col">National</th>
                        <th scope="col">Read</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.columns.map((col) => {
                        const value = profile[col.key] as number | null;
                        const n = profile[`${col.key}_n`] as number;
                        const rank = profile[`_rank_${col.key}`] as number | null;
                        const smallSample = n < minimumN(col);
                        const eligibleCount = eligibleCounts[col.key] ?? 0;
                        const format = FORMATTERS[col.fmt ?? "pct1"];
                        const tier = fanTier(rank, eligibleCount, smallSample, col.noHeatmap);
                        return (
                          <tr key={col.key}>
                            <td className="profile-metric-name">
                              <div className="profile-metric-label">
                                <strong>{col.label}</strong>
                                <TipTrigger text={`${col.tooltip} Formula: ${col.profileFormula}.`} />
                              </div>
                            </td>
                            <td
                              className={`profile-rate${smallSample ? " profile-rate--sample" : ""}`}
                              style={!smallSample && !col.noHeatmap ? { backgroundColor: heatBackground(value, columnRanges[col.key], col.lowerBetter) } : undefined}
                            >
                              <strong>{format(value)}</strong>
                              <small>N={n}</small>
                            </td>
                            <td className="profile-rank">
                              {rank ? (
                                <>
                                  <strong>#{rank}</strong>
                                  <small>of {eligibleCount}</small>
                                </>
                              ) : (
                                <>
                                  <strong>—</strong>
                                  <small>small sample</small>
                                </>
                              )}
                            </td>
                            <td className="profile-read">
                              <span className={`profile-tier ${tier.className}`}>{tier.label}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </section>
              ))}
            </div>

            <footer className="exploratory-profile-footer">
              <Link className="exploratory-profile-team-link" href={`/team/${profile.slug}`}>
                Full Team Profile <span aria-hidden="true">→</span>
              </Link>
              <button type="button" className="exploratory-profile-done" onClick={() => setProfileTeam(null)}>Close</button>
            </footer>
          </section>
        </div>
      )}

      {sheetTeam ? (() => {
        const entry = samples[`${year}:${sheetTeam.slug}`];
        const data = entry?.status === "ready" ? entry.data : null;
        return (
          <GameSampleSheet
            team={sheetTeam.team}
            teamId={sheetTeam.teamId}
            year={year}
            status={entry?.status ?? "loading"}
            games={data ? data.team.games : null}
            scopeNote={`Only ${sheetTeam.team}'s row, profile, and rankings here change. PRIME Ratings and predictions always use the full official sample.`}
            excluded={excluded[sheetTeam.slug] ?? []}
            rangeEnabled={rangeAllowsCustom}
            weekLabel={weekLabel}
            onChange={(ids) => updateExclusions(sheetTeam.slug, ids)}
            onToggle={(id) => toggleExcluded(sheetTeam.slug, id)}
            onShowFullRange={() => { if (weeks.length) { setStartWeek(weeks[0]); setEndWeek(weeks[weeks.length - 1]); } }}
            onClose={() => setSheetTeam(null)}
          />
        );
      })() : null}

      <div id="methodology" tabIndex={-1}>
        <SiteFooter note="Exploratory statistics include completed FBS-vs-FBS games only and are built from PRIME's canonical play-by-play. They are research-stage and do not feed Adj. Net, Adj. Off, Adj. Def, ASM, or any prediction model." />
      </div>
    </>
  );
}
