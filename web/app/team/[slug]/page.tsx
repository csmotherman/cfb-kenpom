"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { getMeta, getRankingsSeason, getTeamStatsSeason, prefetchAllRankings } from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type { RankingsRow, TeamStatsRow } from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function signed(n: number | null | undefined, digits = 1): string {
  if (na(n)) return "—";
  return (n >= 0 ? "+" : "") + n.toFixed(digits);
}

function pct(n: number | null | undefined): string {
  if (na(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function plain(n: number | null | undefined, digits = 1): string {
  if (na(n)) return "—";
  return n.toFixed(digits);
}

type SeasonRow = RankingsRow & { year: number; finalWeek: number; finalWeekLabel: string };

const HISTORY_METRICS = [
  ["adjEM", "Overall rating (RPI)"],
  ["rank", "Overall rank"],
  ["adjO", "Offense (RPI-O)"],
  ["adjD", "Defense (RPI-D)"],
  ["sos", "Strength of schedule"],
] as const;

export default function TeamPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return <TeamProfile key={slug} slug={slug} />;
}

function TeamProfile({ slug }: { slug: string }) {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [seasons, setSeasons] = useState<SeasonRow[] | null>(null);
  const [teamStats, setTeamStats] = useState<TeamStatsRow | null | undefined>(undefined);
  const [teamStatsLabel, setTeamStatsLabel] = useState<string | null>(null);
  const [historyMetric, setHistoryMetric] = useState<string>("adjEM");

  useEffect(() => {
    let cancelled = false;
    getMeta().then(async (meta) => {
      const sortedYears = meta.rankingsYears.slice().sort((a, b) => b - a);
      if (cancelled) return;
      prefetchAllRankings(sortedYears);
      const [allSeasons, publicStats] = await Promise.all([
        Promise.all(sortedYears.map((year) => getRankingsSeason(year))),
        sortedYears.length ? getTeamStatsSeason(sortedYears[0]) : Promise.resolve(null),
      ]);
      if (cancelled) return;
      const results: SeasonRow[] = [];
      allSeasons.forEach((season, i) => {
        const year = sortedYears[i];
        const finalWeek = season.weeks[season.weeks.length - 1];
        const finalWeekLabel = season.weekLabels?.[String(finalWeek)] || `Week ${finalWeek}`;
        const rows = season.byWeek[String(finalWeek)] || [];
        const match = rows.find((t) => t.slug === slug);
        if (match) results.push({ ...match, year, finalWeek, finalWeekLabel });
      });
      setSeasons(results);
      setTeamStats(publicStats?.teams.find((row) => row.slug === slug) ?? null);
      setTeamStatsLabel(publicStats?.weekLabel ?? null);
    }).catch((error: Error) => { if (!cancelled) setLoadError(error); });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const latest = seasons && seasons[0];

  useEffect(() => {
    if (latest) {
      document.title = `${latest.team} RPI | GRID`;
    }
  }, [latest]);

  if (loadError) throw loadError;

  if (seasons === null) {
    return (
      <>
        <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
        <SiteNav />
        <main id="teamContent" className="container loading-state" aria-live="polite">Loading team history…</main>
        <SiteFooter note="Records include completed FBS-vs-FBS games only. GRID uses real game data and opponent-adjusted ratings to describe team strength, not poll position. Relative Performance Index (RPI) measures team performance relative to opponent expectations and adjusts for opponent strength." />
      </>
    );
  }

  if (!latest) {
    return (
      <>
        <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
        <SiteNav />
        <main id="teamContent" className="container" aria-live="polite">
          <div className="not-found">
            Team not found. <Link href="/">Back to all ratings &rarr;</Link>
          </div>
        </main>
        <SiteFooter note="Records include completed FBS-vs-FBS games only. GRID uses real game data and opponent-adjusted ratings to describe team strength, not poll position. Relative Performance Index (RPI) measures team performance relative to opponent expectations and adjusts for opponent strength." />
      </>
    );
  }

  return (
    <>
      <a className="skip-link" href="#teamContent">Skip to team profile</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Ratings</Link>
        <span className="crumb-sep">/</span>
        <Link href={`/?conf=${encodeURIComponent(latest.conf)}`}>{latest.conf}</Link>
        <span className="crumb-sep">/</span>
        <span className="crumb-current">{latest.team}</span>
      </nav>

      <main id="teamContent" className="container" aria-live="polite">
        <section className="team-hero">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            className="team-hero__logo"
            src={logoUrl(latest.teamId, 256)}
            alt={`${latest.team} logo`}
            decoding="async"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
            }}
          />
          <div className="team-hero__info">
            <span className="eyebrow">{latest.conf} · {latest.year} through {latest.finalWeekLabel}</span>
            <h1 className="team-hero__name">{latest.team}</h1>
            <div className="team-hero__current">
              <b>{na(latest.rank) ? "—" : `#${latest.rank}`}</b> nationally &middot; <b>{latest.record}</b> &middot; RPI <b>{signed(latest.adjEM, 1)}</b>
            </div>
          </div>
        </section>

        <section className="team-snapshot">
          <div className="section-heading">
            <h2>Current Rating Snapshot</h2>
            <span>Value · national rank</span>
          </div>
          <div className="snapshot-grid">
            {[
              { label: "Overall", value: signed(latest.adjEM, 1), rank: latest.rank, detail: "RPI" },
              { label: "Offense", value: signed(latest.adjO, 2), rank: latest.adjORank, detail: "RPI-O" },
              { label: "Defense", value: signed(latest.adjD, 2), rank: latest.adjDRank, detail: "RPI-D" },
              { label: "Schedule", value: signed(latest.sos, 1), rank: latest.sosRank, detail: "SOS" },
            ].map((item) => (
              <div className="snapshot-card" key={item.label}>
                <div className="snapshot-card__top">
                  <span className="snapshot-card__label">{item.label}</span>
                  <span className="snapshot-card__detail">{item.detail}</span>
                </div>
                <div className="snapshot-card__values">
                  <strong className="mono">{item.value}</strong>
                  <span className="mono snapshot-card__rank">{na(item.rank) ? "—" : `#${item.rank}`}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {teamStats ? (
          <section className="team-free-profile">
            <div className="section-heading">
              <h2>Team Profile</h2>
              <span>{teamStatsLabel ? `Season-to-date through ${teamStatsLabel}` : "Season-to-date"} · core stats stay free</span>
            </div>
            <div className="team-profile-columns">
              <ProfileGroup
                title="Offense"
                rows={[
                  ["Success rate", pct(teamStats.successRate), teamStats.successRateRank],
                  ["Pass success", pct(teamStats.passSuccessRate), teamStats.passSuccessRateRank],
                  ["Rush success", pct(teamStats.rushSuccessRate), teamStats.rushSuccessRateRank],
                  ["Yards / play", plain(teamStats.yardsPerPlay, 2), teamStats.yardsPerPlayRank],
                  ["Explosive rate", pct(teamStats.explosivePlayRate), teamStats.explosivePlayRateRank],
                ]}
              />
              <ProfileGroup
                title="Defense"
                rows={[
                  ["Success allowed", pct(teamStats.successRateAllowed), teamStats.successRateAllowedRank],
                  ["Pass success allowed", pct(teamStats.passSuccessRateAllowed), teamStats.passSuccessRateAllowedRank],
                  ["Rush success allowed", pct(teamStats.rushSuccessRateAllowed), teamStats.rushSuccessRateAllowedRank],
                  ["Yards / play allowed", plain(teamStats.yardsPerPlayAllowed, 2), teamStats.yardsPerPlayAllowedRank],
                  ["Explosive rate allowed", pct(teamStats.explosivePlayRateAllowed), teamStats.explosivePlayRateAllowedRank],
                ]}
              />
            </div>
            <div className="team-profile-context">
              <ProfileContext label="Pass rate" value={pct(teamStats.passRate)} />
              <ProfileContext label="Pace" value={plain(teamStats.pace, 1)} suffix="plays/g" />
              <ProfileContext label="Field position edge" value={signed(teamStats.fieldPositionEdge, 1)} rank={teamStats.fieldPositionEdgeRank} />
              <ProfileContext label="Adj. finishing O" value={signed(teamStats.adjustedFinishingOffense, 2)} rank={teamStats.adjustedFinishingOffenseRank} />
              <ProfileContext label="Adj. finishing D" value={signed(teamStats.adjustedFinishingDefense, 2)} rank={teamStats.adjustedFinishingDefenseRank} />
            </div>
            <p className="team-profile-method-note">
              Success, yards/play, explosiveness and tendencies are season-to-date raw results. RPI and the labeled adjusted edges use GRID&rsquo;s opponent-adjusted model snapshots.
            </p>
          </section>
        ) : null}

        <section className="team-history">
          <div className="section-heading">
            <h2>Season History</h2>
            <span>{seasons.length} {seasons.length === 1 ? "season" : "seasons"} available</span>
          </div>

          <div className="history-mobile-tools">
            <label htmlFor="historyMetricSelect">Compare</label>
            <select id="historyMetricSelect" value={historyMetric} onChange={(e) => setHistoryMetric(e.target.value)}>
              {HISTORY_METRICS.map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>

          <div className="table-scroll history-table-scroll" role="region" aria-label={`${latest.team} season history`} tabIndex={0}>
            <table className="data-table" id="historyTable">
              <caption className="sr-only">{latest.team} historical GRID RPI ratings</caption>
              <thead>
                <tr>
                  <th scope="col" className="year-cell">Year</th>
                  <th scope="col" className="conf-cell">Conf</th>
                  <th scope="col" className="num record-cell">W-L</th>
                  <th scope="col" className={"num history-rank-cell" + (historyMetric === "rank" ? " mobile-selected-history-metric" : "")}>Rk</th>
                  <th scope="col" className={"num history-metric-cell" + (historyMetric === "adjEM" ? " mobile-selected-history-metric" : "")}>RPI</th>
                  <th scope="col" className={"num history-metric-cell" + (historyMetric === "adjO" ? " mobile-selected-history-metric" : "")}>RPI-O</th>
                  <th scope="col" className={"num history-metric-cell" + (historyMetric === "adjD" ? " mobile-selected-history-metric" : "")}>RPI-D</th>
                  <th scope="col" className={"num history-metric-cell" + (historyMetric === "sos" ? " mobile-selected-history-metric" : "")}>SOS</th>
                </tr>
              </thead>
              <tbody>
                {seasons.map((s) => (
                  <tr key={s.year} className={s.year === latest.year ? "history-current" : undefined}>
                    <td className="mono year-cell">{s.year}</td>
                    <td className="conf-cell">{s.conf}</td>
                    <td className="num record-cell">{s.record}</td>
                    <td className={"num mono history-rank-cell" + (historyMetric === "rank" ? " mobile-selected-history-metric" : "")}>
                      {na(s.rank) ? "—" : s.rank}
                    </td>
                    <HistoryStat value={s.adjEM} digits={1} primary selected={historyMetric === "adjEM"} />
                    <HistoryStat value={s.adjO} rank={s.adjORank} digits={2} selected={historyMetric === "adjO"} />
                    <HistoryStat value={s.adjD} rank={s.adjDRank} digits={2} selected={historyMetric === "adjD"} />
                    <HistoryStat value={s.sos} rank={s.sosRank} digits={1} selected={historyMetric === "sos"} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="adv-preview adv-preview--workbench">
          <div className="adv-preview__heading">
            <h2>GRID Pro Workbench</h2>
            <span className="adv-preview__badge">PRO</span>
          </div>
          <p className="adv-preview__note">
            The core team profile above stays public. Pro is for doing the work yourself: custom week ranges, offense/defense tables, deeper splits and eventually full matchup intelligence.
          </p>
          <div className="team-pro-tools">
            {[
              "Custom week ranges",
              "Advanced offense / defense tables",
              "Situational split builder",
              "Full matchup intelligence",
            ].map((label) => <span key={label}>{label}</span>)}
          </div>
          <Link className="subscribe-btn team-pro-tools__link" href="/advanced">Open Advanced Analytics</Link>
        </section>
      </main>

      <SiteFooter note="Records include completed FBS-vs-FBS games only. GRID uses real game data and opponent-adjusted ratings to describe team strength, not poll position. Relative Performance Index (RPI) measures team performance relative to opponent expectations and adjusts for opponent strength. RPI-O and RPI-D are the corresponding opponent-adjusted offensive and defensive performance measures." />
    </>
  );
}

function ProfileGroup({ title, rows }: { title: string; rows: [string, string, number | null][] }) {
  return (
    <div className="team-profile-group">
      <h3>{title}</h3>
      {rows.map(([label, value, rank]) => (
        <div className="team-profile-row" key={label}>
          <span>{label}</span>
          <strong className="mono">{value}</strong>
          <em className="mono">{rank === null ? "—" : `#${rank}`}</em>
        </div>
      ))}
    </div>
  );
}

function ProfileContext({ label, value, rank, suffix }: { label: string; value: string; rank?: number | null; suffix?: string }) {
  return (
    <div className="team-profile-context__item">
      <span>{label}</span>
      <strong className="mono">{value}{suffix ? ` ${suffix}` : ""}</strong>
      {rank !== undefined ? <em className="mono">{rank === null ? "—" : `#${rank}`}</em> : null}
    </div>
  );
}

function HistoryStat({ value, rank, digits, primary, selected }: { value: number | null; rank?: number | null; digits: number; primary?: boolean; selected?: boolean }) {
  return (
    <td className={(primary ? "num mono primary-stat history-metric-cell" : "num mono history-metric-cell") + (selected ? " mobile-selected-history-metric" : "")}>
      {na(value) ? "—" : signed(value, digits)}
      {!primary && !na(rank) ? <span className="rank-sub">#{rank}</span> : null}
    </td>
  );
}
