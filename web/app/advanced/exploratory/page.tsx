"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, useExploratorySeason } from "@/lib/data";
import { columnRange, heatBackground } from "@/lib/heatmap";
import type { ExploratorySeason, ExploratoryRow, ExploratoryWeekCounts } from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function pct1(v: number | null): string {
  return na(v) ? "—" : (v * 100).toFixed(1) + "%";
}

// A single week's sample sizes for these metrics cluster well above this on
// a normal team-week (median ~29 series opportunities, ~18 recovery
// opportunities per team per week across the 2025 corpus audit) but the low
// end (single-digit-to-teens) carries real binomial noise -- e.g. a 70% true
// rate at N=15 has a standard error north of 10 points. One shared threshold
// across all six metrics rather than per-metric tuning, since their
// single-week denominators sit in a similar range.
const MIN_RELIABLE_N = 20;

type ExpColumn = {
  key: string;
  label: string;
  num: keyof ExploratoryWeekCounts;
  den: keyof ExploratoryWeekCounts;
  tooltip: string;
};

const OFFENSE_COLUMNS: ExpColumn[] = [
  {
    key: "seriesConversionRate", label: "Series Conversion %",
    num: "seriesConversions", den: "seriesOpportunities",
    tooltip: "How often a fresh set of downs ends with another first down or a touchdown. It counts conversions on any down, not just 3rd down.",
  },
  {
    key: "recoveryRate", label: "Recovery %",
    num: "recoveredSeries", den: "recoveryOpportunities",
    tooltip: "After an unsuccessful 1st- or 2nd-down play, how often the offense still earns another first down or touchdown in that same series.",
  },
  {
    key: "longDownAvoidanceRate", label: "Avoid 3rd & Long %",
    num: "longDownAvoidanceSeries", den: "eligibleSeries",
    tooltip: "How often the offense gets through a series without facing 3rd-and-7 or longer. Higher means it stays on schedule more often.",
  },
];

const DEFENSE_COLUMNS: ExpColumn[] = [
  {
    key: "seriesStopRate", label: "Series Stop %",
    num: "seriesStops", den: "seriesStopOpportunities",
    tooltip: "How often the defense ends an opponent's fresh set of downs before the offense gains another first down or scores a touchdown.",
  },
  {
    key: "closeoutRate", label: "Closeout %",
    num: "closeouts", den: "closeoutOpportunities",
    tooltip: "After the defense wins an early down, how often it finishes the series without allowing another first down or touchdown.",
  },
  {
    key: "longDownCreationRate", label: "Force 3rd & Long %",
    num: "longDownsCreated", den: "longDownCreationOpportunities",
    tooltip: "How often the defense forces an opponent into 3rd-and-7 or longer. Higher means more obvious passing situations created.",
  },
];

const ALL_COLUMNS = [...OFFENSE_COLUMNS, ...DEFENSE_COLUMNS];

function sumField(wk: Partial<ExploratoryWeekCounts>, field: keyof ExploratoryWeekCounts): number {
  return wk[field] ?? 0;
}

type Aggregated = {
  team: string;
  slug: string;
  teamId: number;
  conf: string;
  wk: Partial<ExploratoryWeekCounts>;
  [key: string]: unknown;
};

const EMPTY_WEEKS: number[] = [];
const EMPTY_BY_WEEK: Record<string, ExploratoryRow[]> = {};

export default function ExploratoryPage() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<string>("");
  const [startWeek, setStartWeek] = useState<number | null>(null);
  const [endWeek, setEndWeek] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<string>(OFFENSE_COLUMNS[0].key);
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
    const selectedWeeks = weeks.filter((week) => week >= startWeek && week <= endWeek);
    const byTeam = new Map<string, Aggregated>();

    selectedWeeks.forEach((week) => {
      const rows = seasonByWeek[String(week)] || [];
      rows.forEach((row) => {
        let acc = byTeam.get(row.slug);
        if (!acc) {
          acc = { team: row.team, slug: row.slug, teamId: row.teamId, conf: row.conf, wk: {} };
          byTeam.set(row.slug, acc);
        }
        const wkData = row.wk || {};
        (Object.keys(wkData) as (keyof ExploratoryWeekCounts)[]).forEach((key) => {
          acc!.wk[key] = (acc!.wk[key] ?? 0) + (wkData[key] ?? 0);
        });
      });
    });

    return Array.from(byTeam.values()).map((acc) => {
      const out: Aggregated = { ...acc };
      ALL_COLUMNS.forEach((col) => {
        const num = sumField(acc.wk, col.num);
        const den = sumField(acc.wk, col.den);
        out[col.key] = den > 0 ? num / den : null;
        out[`${col.key}_n`] = den;
      });
      return out;
    });
  }, [seasonByWeek, weeks, startWeek, endWeek]);

  const rankedTeams = useMemo(() => {
    const withRanks = teams.map((team) => ({ ...team }));
    ALL_COLUMNS.forEach((col) => {
      const ranked = withRanks.filter(
        (team) => !na(team[col.key] as number | null) && (team[`${col.key}_n`] as number) >= MIN_RELIABLE_N
      );
      ranked.sort((a, b) => (b[col.key] as number) - (a[col.key] as number));
      ranked.forEach((team, index) => { team[`_rank_${col.key}`] = index + 1; });
      withRanks.forEach((team) => {
        if (team[`_rank_${col.key}`] === undefined) team[`_rank_${col.key}`] = null;
      });
    });
    return withRanks;
  }, [teams]);

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
        teams.filter((t) => (t[`${col.key}_n`] as number) >= MIN_RELIABLE_N).map((t) => t[col.key] as number | null)
      );
    });
    return ranges;
  }, [teams]);

  const conferences = useMemo(() => [...new Set(teams.map((team) => team.conf))].filter(Boolean).sort(), [teams]);

  function onHeaderClick(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "team" ? "asc" : "desc");
    }
  }

  if (loadError) throw loadError;

  const activeRangeLabel = startWeek !== null && endWeek !== null ? weekRangeLabel(startWeek, endWeek) : "Selected weeks";

  return (
    <>
      <a className="skip-link" href="#exploratoryTable">Skip to exploratory analytics</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <section className="ratings-hero container" aria-labelledby="exploratoryTitle">
        <div className="ratings-hero__copy">
          <span className="eyebrow">Advanced · Exploratory</span>
          <h1 id="exploratoryTitle">{year} Series-Level Statistics</h1>
          <p className="ratings-hero__description">
            Research-stage stats that explain how teams sustain drives, recover after bad downs, finish defensive wins, and control 3rd-and-long situations.
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
            <input id="exploratoryFilterInput" type="search" placeholder="Search team…" autoComplete="off" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>
          <div className="conference-filter">
            <label className="sr-only" htmlFor="exploratoryConferenceSelect">Conference</label>
            <select id="exploratoryConferenceSelect" value={conference} onChange={(e) => setConference(e.target.value)}>
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
              onChange={(e) => {
                const value = Number(e.target.value);
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
              onChange={(e) => {
                const value = Number(e.target.value);
                setEndWeek(value);
                setProfileTeam(null);
                if (startWeek !== null && value < startWeek) setStartWeek(value);
              }}
            >
              {weeks.map((week) => <option key={week} value={week}>{weekLabel(week)}</option>)}
            </select>
          </div>
        </div>
        <p className="container adv-note">Every rate sums the raw counts across the selected week range, then divides. Grayed-out cells fell below {MIN_RELIABLE_N} qualifying series and are shown without a national rank.</p>
      </div>

      <main id="exploratoryTable" className="table-main container">
        <div className="advanced-table-shell">
          <div className="table-scroll" role="region" aria-label="Exploratory series-level analytics table" tabIndex={0}>
            <table className="data-table adv-table">
              <caption className="sr-only">LEILA Exploratory series-level team analytics</caption>
              <thead>
                <tr className="adv-section-row">
                  <th scope="colgroup" colSpan={3} className="adv-section-spacer">Team</th>
                  <th scope="colgroup" colSpan={OFFENSE_COLUMNS.length} className="adv-section-heading">Offense</th>
                  <th scope="colgroup" colSpan={DEFENSE_COLUMNS.length} className="adv-section-heading">Defense</th>
                </tr>
                <tr className="adv-column-row">
                  <th scope="col" className="team-cell sortable" aria-sort={sortKey === "team" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                    <button type="button" className="column-sort" onClick={() => onHeaderClick("team")}>Team</button>
                    <span className="sort-indicator">{sortKey === "team" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                  </th>
                  <th scope="col" className="num record-cell">Conf</th>
                  <th scope="col" className="profile-cell">Profile</th>
                  {ALL_COLUMNS.map((col, i) => (
                    <th
                      key={col.key}
                      scope="col"
                      className={`num metric-cell sortable${i === OFFENSE_COLUMNS.length ? " section-start" : ""}`}
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
                      {Array.from({ length: 3 + ALL_COLUMNS.length }).map((__, cellIndex) => (
                        <td key={cellIndex}><span className="skeleton-bar" style={{ width: (cellIndex === 0 ? 75 : 45 + ((cellIndex * 11) % 30)) + "%" }} /></td>
                      ))}
                    </tr>
                  ))
                ) : visibleTeams.length === 0 ? (
                  <tr className="empty-row">
                    <td colSpan={3 + ALL_COLUMNS.length}>No teams match &ldquo;{filter}&rdquo;.</td>
                  </tr>
                ) : (
                  visibleTeams.map((team) => (
                    <tr key={team.slug}>
                      <td className="team-cell">
                        <TeamLink team={team.team} teamId={team.teamId} slug={team.slug} />
                      </td>
                      <td className="num record-cell">{team.conf}</td>
                      <td className="profile-cell">
                        <button type="button" className="exploratory-profile-button" onClick={() => setProfileTeam(team)}>
                          View Profile
                        </button>
                      </td>
                      {ALL_COLUMNS.map((col, i) => {
                        const value = team[col.key] as number | null;
                        const n = team[`${col.key}_n`] as number;
                        const rank = team[`_rank_${col.key}`] as number | null;
                        const smallSample = n < MIN_RELIABLE_N;
                        return (
                          <td
                            key={col.key}
                            className={`num stat-cell metric-cell${i === OFFENSE_COLUMNS.length ? " section-start" : ""}${smallSample ? " small-sample" : ""}`}
                            style={!smallSample ? { backgroundColor: heatBackground(value, columnRanges[col.key], false) } : undefined}
                            title={`N=${n}`}
                          >
                            <span className="metric-value">{pct1(value)}</span>
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
                <p>{profileTeam.conf} · Research-stage series analytics</p>
              </div>
              <button type="button" className="exploratory-modal-close" aria-label="Close exploratory profile" onClick={() => setProfileTeam(null)}>×</button>
            </header>

            <div className="exploratory-profile-note">
              These metrics describe how {profileTeam.team} sustains and ends series. They do not affect LEILA Ratings or predictions.
            </div>

            {[
              { title: "Offense", columns: OFFENSE_COLUMNS },
              { title: "Defense", columns: DEFENSE_COLUMNS },
            ].map((group) => (
              <section className="exploratory-profile-section" key={group.title}>
                <h3>{group.title}</h3>
                <div className="exploratory-profile-metrics">
                  {group.columns.map((col) => {
                    const value = profileTeam[col.key] as number | null;
                    const n = profileTeam[`${col.key}_n`] as number;
                    const rank = profileTeam[`_rank_${col.key}`] as number | null;
                    const smallSample = n < MIN_RELIABLE_N;
                    return (
                      <div className="exploratory-profile-metric" key={col.key}>
                        <div className="exploratory-profile-metric__heading">
                          <strong>{col.label}</strong>
                          <span className="exploratory-profile-metric__value">{pct1(value)}</span>
                        </div>
                        <div className="exploratory-profile-metric__meta">
                          <span>{rank ? `#${rank} nationally` : smallSample ? "Small sample · no rank" : "Not ranked"}</span>
                          <span>N={n}</span>
                        </div>
                        <p>{col.tooltip}</p>
                      </div>
                    );
                  })}
                </div>
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