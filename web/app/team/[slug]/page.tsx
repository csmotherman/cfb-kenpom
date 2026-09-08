"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { TipTrigger } from "@/components/Tooltip";
import { getMeta, getRankingsSeason, getScheduleSeason, getTeamStatsSeason, prefetchAllRankings } from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type { RankingsRow, RankingsSeason, ScheduleGame, ScheduleSeason, TeamStatsRow } from "@/lib/types";

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

function rankText(n: number | null | undefined): string {
  return na(n) ? "" : ` (#${n})`;
}

type SeasonRow = RankingsRow & { year: number; finalWeek: number; finalWeekLabel: string };
type TeamTab = "overall" | "offense" | "defense" | "schedule";

const TABS: { key: TeamTab; label: string }[] = [
  { key: "overall", label: "Overall" },
  { key: "offense", label: "Offense" },
  { key: "defense", label: "Defense" },
  { key: "schedule", label: "Schedule" },
];

const HISTORY_METRICS = [
  ["adjEM", "Overall rating (RPI)"],
  ["rank", "Overall rank"],
  ["adjO", "Offense (RPI-O)"],
  ["adjD", "Defense (RPI-D)"],
  ["sos", "Strength of schedule"],
] as const;

function pregameRatingWeek(rankings: RankingsSeason, gameWeek: number): number | null {
  const prior = rankings.weeks.filter((week) => week < gameWeek);
  return prior.length ? prior[prior.length - 1] : null;
}

export default function TeamPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  return <TeamProfile key={slug} slug={slug} />;
}

function TeamProfile({ slug }: { slug: string }) {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [seasons, setSeasons] = useState<SeasonRow[] | null>(null);
  const [latestRankings, setLatestRankings] = useState<RankingsSeason | null>(null);
  const [latestYear, setLatestYear] = useState<number | null>(null);
  const [teamStats, setTeamStats] = useState<TeamStatsRow | null | undefined>(undefined);
  const [teamStatsLabel, setTeamStatsLabel] = useState<string | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [historyMetric, setHistoryMetric] = useState<string>("adjEM");
  const [tab, setTab] = useState<TeamTab>("overall");

  useEffect(() => {
    let cancelled = false;
    getMeta().then(async (meta) => {
      const sortedYears = meta.rankingsYears.slice().sort((a, b) => b - a);
      if (cancelled) return;
      prefetchAllRankings(sortedYears);
      const [allSeasons, publicStats, scheduleData] = await Promise.all([
        Promise.all(sortedYears.map((year) => getRankingsSeason(year))),
        sortedYears.length ? getTeamStatsSeason(sortedYears[0]) : Promise.resolve(null),
        sortedYears.length ? getScheduleSeason(sortedYears[0]) : Promise.resolve(null),
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
      setLatestRankings(allSeasons[0] ?? null);
      setLatestYear(sortedYears[0] ?? null);
      setTeamStats(publicStats?.teams.find((row) => row.slug === slug) ?? null);
      setTeamStatsLabel(publicStats?.weekLabel ?? null);
      setSchedule(scheduleData);
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

  const teamGames = useMemo(() => {
    if (!schedule) return [];
    const games: ScheduleGame[] = [];
    for (const week of schedule.weeks) {
      for (const game of schedule.byWeek[String(week)] || []) {
        if (game.homeSlug === slug || game.awaySlug === slug) games.push(game);
      }
    }
    return games;
  }, [schedule, slug]);

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
              { label: "Overall", value: signed(latest.adjEM, 1), rank: latest.rank, detail: "RPI", tip: "Opponent-adjusted overall rating, walk-forward through the current week." },
              { label: "Offense", value: signed(latest.adjO, 2), rank: latest.adjORank, detail: "RPI-O", tip: "Opponent-adjusted offensive edge." },
              { label: "Defense", value: signed(latest.adjD, 2), rank: latest.adjDRank, detail: "RPI-D", tip: "Opponent-adjusted defensive edge." },
              { label: "Schedule", value: signed(latest.sos, 1), rank: latest.sosRank, detail: "SOS", tip: "Average opponent rating faced this season." },
              { label: "Résumé", value: signed(latest.sor, 1), rank: latest.sorRank, detail: "SOR", tip: "Wins above what a league-average team would get on this exact schedule. A results measure, not a quality measure." },
            ].map((item) => (
              <div className="snapshot-card" key={item.label}>
                <div className="snapshot-card__top">
                  <span className="snapshot-card__label">{item.label}</span>
                  <span className="snapshot-card__detail">{item.detail}<TipTrigger text={item.tip} /></span>
                </div>
                <div className="snapshot-card__values">
                  <strong className="mono">{item.value}</strong>
                  <span className="mono snapshot-card__rank">{na(item.rank) ? "—" : `#${item.rank}`}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="team-detail">
          <nav className="tab-nav" aria-label="Team detail">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                className={tab === t.key ? "active" : undefined}
                aria-pressed={tab === t.key}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </nav>

          {tab === "overall" ? (
            <OverallTab teamStats={teamStats} teamStatsLabel={teamStatsLabel} latest={latest} />
          ) : tab === "offense" ? (
            <MetricTable rows={teamStats ? offenseRows(teamStats) : []} loading={teamStats === undefined} label={teamStatsLabel} context={teamStats ? offenseContext(teamStats) : []} />
          ) : tab === "defense" ? (
            <MetricTable rows={teamStats ? defenseRows(teamStats) : []} loading={teamStats === undefined} label={teamStatsLabel} context={teamStats ? defenseContext(teamStats) : []} />
          ) : (
            <ScheduleTab
              games={teamGames}
              loading={schedule === undefined}
              slug={slug}
              rankings={latestRankings}
              year={latestYear}
              weekLabels={schedule?.weekLabels}
            />
          )}
        </section>

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
            The core team profile above stays public. Pro is for doing the work yourself: custom week ranges, deeper splits and eventually full matchup intelligence.
          </p>
          <div className="team-pro-tools">
            {[
              "Custom week ranges",
              "Deeper situational splits",
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

// ---------- Overall tab ----------

function OverallTab({ teamStats, teamStatsLabel, latest }: { teamStats: TeamStatsRow | null | undefined; teamStatsLabel: string | null; latest: SeasonRow }) {
  if (teamStats === undefined) return <div className="weekly-state">Loading team profile…</div>;
  if (!teamStats) return <div className="weekly-state">Season-to-date profile isn&rsquo;t published yet for {latest.team}.</div>;
  return (
    <div className="team-overall">
      <p className="team-overall__note">
        {latest.team} ranks <b>#{na(latest.rank) ? "—" : latest.rank}</b> nationally in RPI ({signed(latest.adjEM, 1)}), driven by an offense ranked <b>#{na(latest.adjORank) ? "—" : latest.adjORank}</b> and a defense ranked <b>#{na(latest.adjDRank) ? "—" : latest.adjDRank}</b>{teamStatsLabel ? `, through ${teamStatsLabel}` : ""}. See the Offense and Defense tabs for the full breakdown, including which numbers are raw results and which are opponent-adjusted.
      </p>
      <div className="team-profile-columns">
        <ProfileGroup
          title="Offense highlights"
          rows={[
            ["Success rate", pct(teamStats.successRate), teamStats.successRateRank],
            ["Explosiveness (adj.)", signed(teamStats.adjustedExplosivenessOffense, 2), teamStats.adjustedExplosivenessOffenseRank],
            ["Finishing drives (adj.)", signed(teamStats.adjustedFinishingOffense, 2), teamStats.adjustedFinishingOffenseRank],
          ]}
        />
        <ProfileGroup
          title="Defense highlights"
          rows={[
            ["Success rate allowed", pct(teamStats.successRateAllowed), teamStats.successRateAllowedRank],
            ["Explosiveness allowed (adj.)", signed(teamStats.adjustedExplosivenessDefense, 2), teamStats.adjustedExplosivenessDefenseRank],
            ["Finishing drives allowed (adj.)", signed(teamStats.adjustedFinishingDefense, 2), teamStats.adjustedFinishingDefenseRank],
          ]}
        />
      </div>
    </div>
  );
}

function ProfileGroup({ title, rows }: { title: string; rows: [string, string, number | null | undefined][] }) {
  return (
    <div className="team-profile-group">
      <h3>{title}</h3>
      {rows.map(([label, value, rank]) => (
        <div className="team-profile-row" key={label}>
          <span>{label}</span>
          <strong className="mono">{value}</strong>
          <em className="mono">{na(rank) ? "—" : `#${rank}`}</em>
        </div>
      ))}
    </div>
  );
}

// ---------- Offense / Defense tabs: raw vs opponent-adjusted ----------

type MetricRowData = {
  label: string;
  tip: string;
  raw: string | null;
  rawRank?: number | null;
  adjusted: string | null;
  adjustedRank?: number | null;
};

function offenseRows(t: TeamStatsRow): MetricRowData[] {
  return [
    { label: "Success rate", tip: "Season-to-date offensive success rate (raw, not opponent-adjusted).", raw: pct(t.successRate), rawRank: t.successRateRank, adjusted: null },
    { label: "Pass success", tip: "Season-to-date passing success rate (raw).", raw: pct(t.passSuccessRate), rawRank: t.passSuccessRateRank, adjusted: null },
    { label: "Rush success", tip: "Season-to-date rushing success rate (raw).", raw: pct(t.rushSuccessRate), rawRank: t.rushSuccessRateRank, adjusted: null },
    { label: "Yards / play", tip: "Season-to-date offensive yards per play (raw).", raw: plain(t.yardsPerPlay, 2), rawRank: t.yardsPerPlayRank, adjusted: null },
    {
      label: "Explosiveness",
      tip: "Explosive-play rate is raw (share of plays that gain an explosive amount of yardage). The adjusted edge is GRID's opponent-adjusted explosiveness model, a research-stage snapshot.",
      raw: pct(t.explosivePlayRate), rawRank: t.explosivePlayRateRank,
      adjusted: signed(t.adjustedExplosivenessOffense, 2), adjustedRank: t.adjustedExplosivenessOffenseRank,
    },
    {
      label: "Finishing drives",
      tip: "Raw is points scored per resolved scoring opportunity. The adjusted edge is GRID's opponent-adjusted finishing model, a research-stage snapshot.",
      raw: plain(t.finishingRate, 2), rawRank: t.finishingRateRank,
      adjusted: signed(t.adjustedFinishingOffense, 2), adjustedRank: t.adjustedFinishingOffenseRank,
    },
    {
      label: "Field position",
      tip: "Raw is average starting field position in yards from the opponent's goal line (lower is better -- it means starting closer to scoring). The adjusted edge is GRID's opponent-adjusted model, a research-stage snapshot.",
      raw: plain(t.fieldPositionRaw, 1), rawRank: t.fieldPositionRawRank,
      adjusted: signed(t.fieldPositionEdge, 1), adjustedRank: t.fieldPositionEdgeRank,
    },
  ];
}

function defenseRows(t: TeamStatsRow): MetricRowData[] {
  return [
    { label: "Success rate allowed", tip: "Season-to-date success rate allowed (raw, not opponent-adjusted). Lower is better.", raw: pct(t.successRateAllowed), rawRank: t.successRateAllowedRank, adjusted: null },
    { label: "Pass success allowed", tip: "Season-to-date passing success rate allowed (raw). Lower is better.", raw: pct(t.passSuccessRateAllowed), rawRank: t.passSuccessRateAllowedRank, adjusted: null },
    { label: "Rush success allowed", tip: "Season-to-date rushing success rate allowed (raw). Lower is better.", raw: pct(t.rushSuccessRateAllowed), rawRank: t.rushSuccessRateAllowedRank, adjusted: null },
    { label: "Yards / play allowed", tip: "Season-to-date yards per play allowed (raw). Lower is better.", raw: plain(t.yardsPerPlayAllowed, 2), rawRank: t.yardsPerPlayAllowedRank, adjusted: null },
    {
      label: "Explosiveness allowed",
      tip: "Explosive-play rate allowed is raw (lower is better). The adjusted edge is GRID's opponent-adjusted explosiveness model; higher is better there, since it's framed as beating expectation.",
      raw: pct(t.explosivePlayRateAllowed), rawRank: t.explosivePlayRateAllowedRank,
      adjusted: signed(t.adjustedExplosivenessDefense, 2), adjustedRank: t.adjustedExplosivenessDefenseRank,
    },
    {
      label: "Finishing drives allowed",
      tip: "Raw is points allowed per opponent scoring opportunity (lower is better). The adjusted edge is GRID's opponent-adjusted finishing model, a research-stage snapshot.",
      raw: plain(t.finishingRateAllowed, 2), rawRank: t.finishingRateAllowedRank,
      adjusted: signed(t.adjustedFinishingDefense, 2), adjustedRank: t.adjustedFinishingDefenseRank,
    },
    {
      label: "Field position allowed",
      tip: "Raw is the opponent's average starting field position in yards from GRID's goal line (higher is better -- it means forcing opponents to start further away).",
      raw: plain(t.fieldPositionRawAllowed, 1), rawRank: t.fieldPositionRawAllowedRank, adjusted: null,
    },
  ];
}

function offenseContext(t: TeamStatsRow) {
  return [
    { label: "Pace", value: `${plain(t.pace, 1)} plays/g`, tip: "Offensive plays per game with available play-by-play." },
    { label: "Pass rate", value: pct(t.passRate), tip: "Share of offensive plays that were a dropback rather than a rush attempt." },
  ];
}

function defenseContext(t: TeamStatsRow) {
  return [
    { label: "Opponent pass rate", value: pct(t.passRateAgainst), tip: "Share of plays faced that were a dropback rather than a rush attempt." },
  ];
}

function MetricTable({
  rows,
  loading,
  label,
  context,
}: {
  rows: MetricRowData[];
  loading: boolean;
  label: string | null;
  context: { label: string; value: string; tip: string }[];
}) {
  if (loading) return <div className="weekly-state">Loading team profile…</div>;
  if (!rows.length) return <div className="weekly-state">This profile isn&rsquo;t published yet.</div>;
  return (
    <div className="metric-table-wrap">
      <div className="table-scroll" role="region" aria-label="Team metric table" tabIndex={0}>
        <table className="data-table metric-table">
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col" className="num">Raw</th>
              <th scope="col" className="num">Opponent Adjusted</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}<TipTrigger text={row.tip} /></td>
                <td className="num mono">{row.raw === null ? "—" : `${row.raw}${rankText(row.rawRank)}`}</td>
                <td className="num mono">{row.adjusted === null ? "—" : `${row.adjusted}${rankText(row.adjustedRank)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {context.length ? (
        <div className="team-profile-context">
          {context.map((c) => (
            <div className="team-profile-context__item" key={c.label}>
              <span>{c.label}<TipTrigger text={c.tip} /></span>
              <strong className="mono">{c.value}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {label ? <p className="team-profile-method-note">Season-to-date through {label}. Raw figures are unadjusted results; Opponent Adjusted figures are GRID&rsquo;s schedule-adjusted model snapshots, research-stage where noted.</p> : null}
    </div>
  );
}

// ---------- Schedule tab ----------

function ScheduleTab({
  games,
  loading,
  slug,
  rankings,
  year,
  weekLabels,
}: {
  games: ScheduleGame[];
  loading: boolean;
  slug: string;
  rankings: RankingsSeason | null;
  year: number | null;
  weekLabels?: Record<string, string>;
}) {
  if (loading) return <div className="weekly-state">Loading schedule…</div>;
  if (!games.length) return <div className="weekly-state">No published FBS-vs-FBS schedule for this team yet.</div>;

  return (
    <div className="table-scroll" role="region" aria-label="Team schedule" tabIndex={0}>
      <table className="data-table schedule-table">
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col">Opponent</th>
            <th scope="col">Result</th>
            <th scope="col" className="num">Opp RPI<TipTrigger text="The opponent's GRID RPI from the week strictly before this game -- never a later, postgame snapshot." /></th>
          </tr>
        </thead>
        <tbody>
          {games.map((g) => {
            const isHome = g.homeSlug === slug;
            const oppTeam = isHome ? g.awayTeam : g.homeTeam;
            const oppSlug = isHome ? g.awaySlug : g.homeSlug;
            const oppTeamId = isHome ? g.awayTeamId : g.homeTeamId;
            const usPts = isHome ? g.homePoints : g.awayPoints;
            const oppPts = isHome ? g.awayPoints : g.homePoints;
            const pregameWeek = rankings ? pregameRatingWeek(rankings, g.week) : null;
            const oppRow = rankings && pregameWeek !== null ? (rankings.byWeek[String(pregameWeek)] || []).find((r) => r.slug === oppSlug) : undefined;
            const weekLabel = weekLabels?.[String(g.week)] || `Wk ${g.week}`;
            let result = "—";
            let resultClass = "";
            if (g.completed && !na(usPts) && !na(oppPts)) {
              result = usPts! > oppPts! ? `W ${usPts}-${oppPts}` : `L ${usPts}-${oppPts}`;
              resultClass = usPts! > oppPts! ? "schedule-win" : "schedule-loss";
            } else if (g.startDate && !g.startTimeTBD) {
              result = new Date(g.startDate).toLocaleDateString("en-US", { month: "short", day: "numeric" });
            }
            return (
              <tr key={g.gameId}>
                <td className="mono">{weekLabel}</td>
                <td>
                  <Link href={`/team/${encodeURIComponent(oppSlug)}`} className="schedule-opp" prefetch={false}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={logoUrl(oppTeamId)} alt="" loading="lazy" decoding="async" />
                    <span>{g.neutralSite ? "vs" : isHome ? "vs" : "@"} {oppTeam}</span>
                  </Link>
                </td>
                <td className={`mono ${resultClass}`}>{result}</td>
                <td className="num mono">
                  {oppRow && !na(oppRow.adjEM) ? `${signed(oppRow.adjEM, 1)}${rankText(oppRow.rank)}` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {year ? <p className="team-profile-method-note">Opponent RPI reflects GRID&rsquo;s rating the week before each game -- it never uses that week&rsquo;s or a later week&rsquo;s results, even after the season moves on.</p> : null}
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
