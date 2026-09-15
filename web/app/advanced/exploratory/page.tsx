"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, useExploratorySeason } from "@/lib/data";
import { ALL_COLUMNS, SECTION_START_KEYS, SECTIONS, SERIES_OFFENSE, aggregateExploratory, rankExploratory, minimumN, fanTier, type Aggregated } from "@/lib/exploratory";
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

export default function ExploratoryPage() {
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

  useEffect(() => {
    getMeta().then((meta) => {
      setYears(meta.advancedYears);
      setYear(String(meta.advancedYears[meta.advancedYears.length - 1]));
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

  const teams = useMemo<Aggregated[]>(() => {
    if (startWeek === null || endWeek === null) return [];
    return aggregateExploratory(seasonByWeek, weeks, startWeek, endWeek);
  }, [seasonByWeek, weeks, startWeek, endWeek]);

  const rankedTeams = useMemo(() => rankExploratory(teams), [teams]);

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

  if (loadError) throw loadError;

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
            possessions, and rely on (or avoid) explosive plays and costly mistakes -- built from LEILA&rsquo;s
            canonical play-by-play, not just box-score snapshots.
          </p>
        </div>
        <div className="ratings-hero__meta">
          <span className="ratings-status">
            {loading ? "Loading season…" : `${year} • ${activeRangeLabel} • ${teams.length} teams`}
          </span>
          <Link className="utility-link" href="/methodology">Methodology ↗</Link>
        </div>
      </section>

      <nav className="exploratory-subnav container" aria-label="Advanced sections">
        <Link href="/advanced">Advanced Analytics</Link>
        <Link href="/advanced/exploratory" className="active" aria-current="page">Exploratory</Link>
      </nav>

      <div className="container exploratory-disclaimer">
        Exploratory metrics are research-stage LEILA statistics designed to measure aspects of football performance
        not fully captured by traditional efficiency metrics. Definitions and methodology may evolve as they are
        validated. Exploratory metrics do not currently affect LEILA Ratings.
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
                onClick={() => { setYear(String(seasonYear)); setConference(""); setProfileTeam(null); }}
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

      <main id="exploratoryTable" className="table-main container">
        <div className="advanced-table-shell">
          <div className="table-scroll" role="region" aria-label="Exploratory analytics table" tabIndex={0}>
            <table className="data-table adv-table">
              <caption className="sr-only">LEILA Exploratory team analytics</caption>
              <thead>
                <tr className="adv-section-row">
                  <th scope="colgroup" colSpan={2} className="adv-section-spacer">Team</th>
                  {SECTIONS.map((section) => (
                    <th key={section.title} scope="colgroup" colSpan={section.columns.length} className="adv-section-heading">
                      {section.title}
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
                  {ALL_COLUMNS.map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className={`num metric-cell sortable${SECTION_START_KEYS.has(col.key) ? " section-start" : ""}`}
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
                      {Array.from({ length: 2 + ALL_COLUMNS.length }).map((__, cellIndex) => (
                        <td key={cellIndex}>
                          <span className="skeleton-bar" style={{ width: (cellIndex === 0 ? 75 : 45 + ((cellIndex * 11) % 30)) + "%" }} />
                        </td>
                      ))}
                    </tr>
                  ))
                ) : visibleTeams.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={2 + ALL_COLUMNS.length}>No teams match &ldquo;{filter}&rdquo;.</td>
                  </tr>
                ) : (
                  visibleTeams.map((team) => (
                    <tr key={team.slug}>
                      <td className="team-cell">
                        <div className="team-cell-stack">
                          <TeamLink team={team.team} teamId={team.teamId} slug={team.slug} />
                          <span className="team-conf-label">{team.conf}</span>
                        </div>
                      </td>
                      <td className="profile-cell">
                        <button type="button" className="exploratory-profile-button" onClick={() => setProfileTeam(team)}>
                          View Profile
                        </button>
                      </td>
                      {ALL_COLUMNS.map((col) => {
                        const value = team[col.key] as number | null;
                        const n = team[`${col.key}_n`] as number;
                        const rank = team[`_rank_${col.key}`] as number | null;
                        const smallSample = n < minimumN(col);
                        const format = FORMATTERS[col.fmt ?? "pct1"];
                        return (
                          <td
                            key={col.key}
                            className={`num stat-cell metric-cell${SECTION_START_KEYS.has(col.key) ? " section-start" : ""}${smallSample ? " small-sample" : ""}`}
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

      {profileTeam && (
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
              <div>
                <span className="eyebrow">Exploratory Profile · {year} · {activeRangeLabel}</span>
                <h2 id="exploratoryProfileTitle">{profileTeam.team}</h2>
                <p>{profileTeam.conf} · How this team wins and loses series</p>
              </div>
              <button
                type="button"
                className="exploratory-modal-close"
                aria-label="Close exploratory profile"
                onClick={() => setProfileTeam(null)}
              >
                ×
              </button>
            </header>

            <div className="exploratory-profile-note">
              <strong>Quick read:</strong> green is a strength, red is an area to watch. The label in the last column translates national rank into plain football language.
            </div>

            {SECTIONS.map((group) => (
              <section className="exploratory-profile-section" key={group.title}>
                <h3>{group.title}</h3>
                <table className="exploratory-profile-table">
                  <thead>
                    <tr>
                      <th scope="col">What it measures</th>
                      <th scope="col">Rate</th>
                      <th scope="col">National</th>
                      <th scope="col">Read</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.columns.map((col) => {
                      const value = profileTeam[col.key] as number | null;
                      const n = profileTeam[`${col.key}_n`] as number;
                      const rank = profileTeam[`_rank_${col.key}`] as number | null;
                      const smallSample = n < minimumN(col);
                      const eligibleCount = eligibleCounts[col.key] ?? 0;
                      const format = FORMATTERS[col.fmt ?? "pct1"];
                      const tier = fanTier(rank, eligibleCount, smallSample, col.noHeatmap);
                      return (
                        <tr key={col.key}>
                          <td className="profile-metric-name">
                            <strong>{col.label}</strong>
                            <span>{col.profileNote}</span>
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

            <footer className="exploratory-profile-footer">
              <TeamLink team={profileTeam.team} teamId={profileTeam.teamId} slug={profileTeam.slug} />
              <button type="button" className="exploratory-profile-done" onClick={() => setProfileTeam(null)}>Close</button>
            </footer>
          </section>
        </div>
      )}

      <div id="methodology" tabIndex={-1}>
        <SiteFooter note="Exploratory statistics include completed FBS-vs-FBS games only and are built from LEILA's canonical play-by-play. They are research-stage and do not feed Adj. Net, Adj. Off, Adj. Def, ASM, or any prediction model." />
      </div>
    </>
  );
}
