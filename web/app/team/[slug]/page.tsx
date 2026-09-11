"use client";

import { use, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { TipTrigger } from "@/components/Tooltip";
import {
  getMeta,
  getRankingsSeason,
  getScheduleSeason,
  getTeamStatsSeason,
  prefetchAllRankings,
} from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
import type {
  AdvancedRow,
  AdvancedSeason,
  RankingsRow,
  RankingsSeason,
  ScheduleGame,
  ScheduleSeason,
  TeamStatsRow,
} from "@/lib/types";

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function signed(n: number | null | undefined, digits = 1): string {
  if (na(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}`;
}

function pct(n: number | null | undefined): string {
  if (na(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function plain(n: number | null | undefined, digits = 1): string {
  if (na(n)) return "—";
  return n.toFixed(digits);
}

function fieldPos(n: number | null | undefined, digits = 1): string {
  if (na(n)) return "—";
  if (n > 50) return `Own ${(100 - n).toFixed(digits)}`;
  if (n < 50) return `Opp ${n.toFixed(digits)}`;
  return "50";
}

function rankText(n: number | null | undefined): string {
  return na(n) ? "—" : `#${n}`;
}

function rankBand(rank: number | null | undefined, totalTeams: number): string | null {
  if (rank === null || rank === undefined || totalTeams <= 0) return null;
  const share = rank / totalTeams;
  if (share <= 0.2) return "elite";
  if (share <= 0.4) return "good";
  if (share <= 0.6) return "middle";
  if (share <= 0.8) return "poor";
  return "bad";
}

function pregameRatingWeek(rankings: RankingsSeason, gameWeek: number): number | null {
  const prior = rankings.weeks.filter((week) => week < gameWeek);
  return prior.length ? prior[prior.length - 1] : null;
}

async function getTeamAdvancedSeason(year: number): Promise<AdvancedSeason | null> {
  const response = await fetch(`/api/matchup-advanced/${year}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(20000),
  });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`Failed to load team advanced analytics: ${response.status}`);
  return response.json() as Promise<AdvancedSeason>;
}

type SeasonRow = RankingsRow & { year: number; finalWeek: number; finalWeekLabel: string };
type TeamTab = "overview" | "offense" | "defense" | "epa" | "success" | "schedule";

type StatDatum = {
  value: string;
  rank: number | null | undefined;
  totalTeams: number;
};

type GroupMetric = StatDatum & {
  label: string;
  note?: string;
};

type MetricGroup = {
  title: string;
  metrics: GroupMetric[];
};

type EdgeMetric = {
  label: string;
  offenseKey: keyof AdvancedRow;
  defenseKey: keyof AdvancedRow;
};

type EdgeSection = {
  title: string;
  metrics: EdgeMetric[];
};

const TABS: { key: TeamTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "offense", label: "Offense" },
  { key: "defense", label: "Defense" },
  { key: "epa", label: "EPA" },
  { key: "success", label: "Success Rate" },
  { key: "schedule", label: "Schedule" },
];

const HISTORY_METRICS = [
  ["adjEM", "Overall rating (Adj. Net)"],
  ["rank", "Overall rank"],
  ["adjO", "Offense (Adj. Off)"],
  ["adjD", "Defense (Adj. Def)"],
  ["sos", "Strength of schedule"],
] as const;

const EPA_SECTIONS: EdgeSection[] = [
  {
    title: "Overall",
    metrics: [
      { label: "EPA / Play", offenseKey: "epaAdj", defenseKey: "epaAdjAllowed" },
    ],
  },
  {
    title: "Passing",
    metrics: [
      { label: "EPA / Dropback", offenseKey: "passEpaAdj", defenseKey: "passEpaAdjAllowed" },
      { label: "1st Down", offenseKey: "passEpaDown1Adj", defenseKey: "passEpaDown1AdjAllowed" },
      { label: "2nd Down", offenseKey: "passEpaDown2Adj", defenseKey: "passEpaDown2AdjAllowed" },
      { label: "3rd Down", offenseKey: "passEpaDown3Adj", defenseKey: "passEpaDown3AdjAllowed" },
    ],
  },
  {
    title: "Rushing",
    metrics: [
      { label: "EPA / Rush", offenseKey: "rushEpaAdj", defenseKey: "rushEpaAdjAllowed" },
      { label: "1st Down", offenseKey: "rushEpaDown1Adj", defenseKey: "rushEpaDown1AdjAllowed" },
      { label: "2nd Down", offenseKey: "rushEpaDown2Adj", defenseKey: "rushEpaDown2AdjAllowed" },
      { label: "3rd Down", offenseKey: "rushEpaDown3Adj", defenseKey: "rushEpaDown3AdjAllowed" },
    ],
  },
];

const SUCCESS_SECTIONS: EdgeSection[] = [
  {
    title: "Overall",
    metrics: [
      { label: "Success Rate", offenseKey: "successAdj", defenseKey: "successAdjAllowed" },
    ],
  },
  {
    title: "Passing",
    metrics: [
      { label: "Pass Success", offenseKey: "passSuccessAdj", defenseKey: "passSuccessAdjAllowed" },
      { label: "1st Down", offenseKey: "passSuccessDown1Adj", defenseKey: "passSuccessDown1AdjAllowed" },
      { label: "2nd Down", offenseKey: "passSuccessDown2Adj", defenseKey: "passSuccessDown2AdjAllowed" },
      { label: "3rd Down", offenseKey: "passSuccessDown3Adj", defenseKey: "passSuccessDown3AdjAllowed" },
    ],
  },
  {
    title: "Rushing",
    metrics: [
      { label: "Rush Success", offenseKey: "rushSuccessAdj", defenseKey: "rushSuccessAdjAllowed" },
      { label: "1st Down", offenseKey: "rushSuccessDown1Adj", defenseKey: "rushSuccessDown1AdjAllowed" },
      { label: "2nd Down", offenseKey: "rushSuccessDown2Adj", defenseKey: "rushSuccessDown2AdjAllowed" },
      { label: "3rd Down", offenseKey: "rushSuccessDown3Adj", defenseKey: "rushSuccessDown3AdjAllowed" },
    ],
  },
];

function advancedNumber(row: AdvancedRow | undefined, key: keyof AdvancedRow): number | null {
  if (!row) return null;
  const value = row[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function advancedRank(
  rows: AdvancedRow[],
  slug: string,
  key: keyof AdvancedRow,
  lowerBetter = false,
): { rank: number | null; total: number } {
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: advancedNumber(row, key) }))
    .filter((row): row is { slug: string; value: number } => row.value !== null)
    .sort((a, b) => lowerBetter ? a.value - b.value : b.value - a.value);
  const index = ranked.findIndex((row) => row.slug === slug);
  return { rank: index >= 0 ? index + 1 : null, total: ranked.length };
}

function marginValue(row: AdvancedRow | undefined, offenseKey: keyof AdvancedRow, defenseKey: keyof AdvancedRow): number | null {
  const offense = advancedNumber(row, offenseKey);
  const defense = advancedNumber(row, defenseKey);
  // Both offense and defense-allowed edges are oriented higher-is-better,
  // so a team's combined margin is their sum, not offense minus defense.
  return offense === null || defense === null ? null : offense + defense;
}

function marginRank(
  rows: AdvancedRow[],
  slug: string,
  offenseKey: keyof AdvancedRow,
  defenseKey: keyof AdvancedRow,
): { rank: number | null; total: number } {
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: marginValue(row, offenseKey, defenseKey) }))
    .filter((row): row is { slug: string; value: number } => row.value !== null)
    .sort((a, b) => b.value - a.value);
  const index = ranked.findIndex((row) => row.slug === slug);
  return { rank: index >= 0 ? index + 1 : null, total: ranked.length };
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
  const [advanced, setAdvanced] = useState<AdvancedSeason | null | undefined>(undefined);
  const [historyMetric, setHistoryMetric] = useState<string>("adjEM");
  const [tab, setTab] = useState<TeamTab>("overview");

  useEffect(() => {
    let cancelled = false;
    getMeta().then(async (meta) => {
      const sortedYears = meta.rankingsYears.slice().sort((a, b) => b - a);
      if (cancelled) return;
      prefetchAllRankings(sortedYears);
      const latest = sortedYears[0];
      const [allSeasons, publicStats, scheduleData, advancedData] = await Promise.all([
        Promise.all(sortedYears.map((year) => getRankingsSeason(year))),
        latest ? getTeamStatsSeason(latest) : Promise.resolve(null),
        latest ? getScheduleSeason(latest) : Promise.resolve(null),
        latest ? getTeamAdvancedSeason(latest) : Promise.resolve(null),
      ]);
      if (cancelled) return;

      const results: SeasonRow[] = [];
      allSeasons.forEach((season, i) => {
        const year = sortedYears[i];
        const finalWeek = season.weeks[season.weeks.length - 1];
        const finalWeekLabel = season.weekLabels?.[String(finalWeek)] || `Week ${finalWeek}`;
        const rows = season.byWeek[String(finalWeek)] || [];
        const match = rows.find((team) => team.slug === slug);
        if (match) results.push({ ...match, year, finalWeek, finalWeekLabel });
      });

      setSeasons(results);
      setLatestRankings(allSeasons[0] ?? null);
      setLatestYear(latest ?? null);
      setTeamStats(publicStats?.teams.find((row) => row.slug === slug) ?? null);
      setTeamStatsLabel(publicStats?.weekLabel ?? null);
      setSchedule(scheduleData);
      setAdvanced(advancedData);
    }).catch((error: Error) => {
      if (!cancelled) setLoadError(error);
    });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  const latest = seasons?.[0];

  useEffect(() => {
    if (latest) document.title = `${latest.team} Analytics | LEILA Ratings`;
  }, [latest]);

  const teamGames = useMemo(() => {
    if (!schedule) return [];
    const games: ScheduleGame[] = [];
    schedule.weeks.forEach((week) => {
      (schedule.byWeek[String(week)] || []).forEach((game) => {
        if (game.homeSlug === slug || game.awaySlug === slug) games.push(game);
      });
    });
    return games;
  }, [schedule, slug]);

  const advancedWeek = useMemo(() => {
    if (!advanced || !latest) return null;
    const available = advanced.weeks.filter((week) => week <= latest.finalWeek);
    return available.length ? available[available.length - 1] : null;
  }, [advanced, latest]);

  const advancedRows = useMemo(() => {
    if (!advanced || advancedWeek === null) return [];
    return advanced.byWeek[String(advancedWeek)] || [];
  }, [advanced, advancedWeek]);

  const advancedTeam = useMemo(
    () => advancedRows.find((row) => row.slug === slug),
    [advancedRows, slug],
  );

  const totalRated = latestRankings && latest
    ? (latestRankings.byWeek[String(latest.finalWeek)] || []).filter((row) => row.rank !== null).length
    : 0;
  const totalStatted = teamStats ? Math.max(
    teamStats.successRateRank ?? 0,
    teamStats.successRateAllowedRank ?? 0,
    1,
  ) : 0;

  if (loadError) throw loadError;

  if (seasons === null) {
    return (
      <>
        <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
        <SiteNav />
        <main className="container weekly-state">Loading team profile…</main>
      </>
    );
  }

  if (!latest) {
    return (
      <>
        <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
        <SiteNav />
        <main className="container weekly-state">
          Team not found. <Link href="/">Back to ratings →</Link>
        </main>
      </>
    );
  }

  const headline = [
    { label: "Overall", short: "Adj. Net", value: signed(latest.adjEM, 1), rank: latest.rank },
    { label: "Offense", short: "Adj. Off", value: signed(latest.adjO, 2), rank: latest.adjORank },
    { label: "Defense", short: "Adj. Def", value: signed(latest.adjD, 2), rank: latest.adjDRank },
    { label: "Schedule", short: "SOS", value: signed(latest.sos, 1), rank: latest.sosRank },
    { label: "Résumé", short: "SOR", value: signed(latest.sor, 1), rank: latest.sorRank },
  ];

  return (
    <>
      <a className="skip-link" href="#teamContent">Skip to team profile</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />

      <main id="teamContent" className="container team-v2-main" aria-live="polite">
        <section className="team-v2-masthead">
          <div className="team-v2-identity">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoUrl(latest.teamId, 192)} alt="" decoding="async" />
            <div>
              <span>{latest.conf} · {latest.year} through {latest.finalWeekLabel}</span>
              <h1>{latest.team}</h1>
              <p><strong>{latest.record}</strong> · {latest.rank ? `#${latest.rank} LEILA` : "Unranked"}</p>
            </div>
          </div>
          <div className="team-v2-masthead__note">Value · national rank</div>
        </section>

        <section className="team-v2-rating-strip" aria-label="Current LEILA ratings">
          {headline.map((item) => (
            <RatingTile
              key={item.label}
              label={item.label}
              short={item.short}
              value={item.value}
              rank={item.rank}
              totalTeams={totalRated}
            />
          ))}
        </section>

        <section className="team-v2-workbench">
          <nav className="team-v2-tabs" aria-label="Team analytics">
            {TABS.map((item) => (
              <button
                key={item.key}
                type="button"
                className={tab === item.key ? "active" : undefined}
                aria-pressed={tab === item.key}
                onClick={() => setTab(item.key)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="team-v2-panel">
            {tab === "overview" ? (
              <OverviewTab
                latest={latest}
                teamStats={teamStats}
                advanced={advancedTeam}
                advancedRows={advancedRows}
                totalStatted={totalStatted}
                slug={slug}
                label={teamStatsLabel}
              />
            ) : tab === "offense" ? (
              <GroupedMetrics
                eyebrow="Offense"
                title={`${latest.team} offensive profile`}
                note="Raw season results and opponent-adjusted context in the same grouped format as LEILA Advanced Analytics."
                groups={offenseGroups(latest, teamStats, advancedTeam, advancedRows, slug, totalStatted, totalRated)}
              />
            ) : tab === "defense" ? (
              <GroupedMetrics
                eyebrow="Defense"
                title={`${latest.team} defensive profile`}
                note="Allowed metrics rank lower as better. Adjusted defensive edges are framed so stronger performance ranks higher where noted."
                groups={defenseGroups(latest, teamStats, advancedTeam, advancedRows, slug, totalStatted, totalRated)}
              />
            ) : tab === "epa" ? (
              <EdgeTable
                team={latest.team}
                row={advancedTeam}
                rows={advancedRows}
                sections={EPA_SECTIONS}
                formatter={(value) => signed(value, 3)}
                note="Opponent-adjusted, confidence-weighted EPA. Both offense and defense are oriented higher-is-better. Margin = offense plus defense allowed."
              />
            ) : tab === "success" ? (
              <EdgeTable
                team={latest.team}
                row={advancedTeam}
                rows={advancedRows}
                sections={SUCCESS_SECTIONS}
                formatter={(value) => signed(value, 2)}
                note="Opponent-adjusted, confidence-weighted success-rate edge. Both offense and defense are oriented higher-is-better. Margin = offense plus defense allowed."
              />
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
          </div>
        </section>

        <section className="team-v2-history">
          <div className="team-v2-section-head">
            <div>
              <span>Program history</span>
              <h2>Season Ratings</h2>
            </div>
            <small>{seasons.length} {seasons.length === 1 ? "season" : "seasons"} available</small>
          </div>

          <div className="history-mobile-tools">
            <label htmlFor="historyMetricSelect">Compare</label>
            <select id="historyMetricSelect" value={historyMetric} onChange={(event) => setHistoryMetric(event.target.value)}>
              {HISTORY_METRICS.map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </div>

          <div className="table-scroll history-table-scroll" role="region" aria-label={`${latest.team} season history`} tabIndex={0}>
            <table className="data-table" id="historyTable">
              <thead>
                <tr>
                  <th scope="col" className="year-cell">Year</th>
                  <th scope="col" className="conf-cell">Conf</th>
                  <th scope="col" className="num record-cell">W-L</th>
                  <th scope="col" className={historyMetric === "rank" ? "num history-rank-cell mobile-selected-history-metric" : "num history-rank-cell"}>Rk</th>
                  <th scope="col" className={historyMetric === "adjEM" ? "num history-metric-cell mobile-selected-history-metric" : "num history-metric-cell"}>Adj. Net</th>
                  <th scope="col" className={historyMetric === "adjO" ? "num history-metric-cell mobile-selected-history-metric" : "num history-metric-cell"}>Adj. Off</th>
                  <th scope="col" className={historyMetric === "adjD" ? "num history-metric-cell mobile-selected-history-metric" : "num history-metric-cell"}>Adj. Def</th>
                  <th scope="col" className={historyMetric === "sos" ? "num history-metric-cell mobile-selected-history-metric" : "num history-metric-cell"}>SOS</th>
                </tr>
              </thead>
              <tbody>
                {seasons.map((season) => (
                  <tr key={season.year} className={season.year === latest.year ? "history-current" : undefined}>
                    <td className="mono year-cell">{season.year}</td>
                    <td className="conf-cell">{season.conf}</td>
                    <td className="num record-cell">{season.record}</td>
                    <td className={historyMetric === "rank" ? "num mono history-rank-cell mobile-selected-history-metric" : "num mono history-rank-cell"}>{na(season.rank) ? "—" : season.rank}</td>
                    <HistoryStat value={season.adjEM} digits={1} primary selected={historyMetric === "adjEM"} />
                    <HistoryStat value={season.adjO} rank={season.adjORank} digits={2} selected={historyMetric === "adjO"} />
                    <HistoryStat value={season.adjD} rank={season.adjDRank} digits={2} selected={historyMetric === "adjD"} />
                    <HistoryStat value={season.sos} rank={season.sosRank} digits={1} selected={historyMetric === "sos"} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </main>

      <SiteFooter note="Team profiles use LEILA's latest published season snapshot. Rank colors are based on national rank among teams with available data. Adjusted defensive EPA and success values are oriented higher-is-better, same as Adj. Def. Schedule links open the corresponding pregame matchup page." />
    </>
  );
}

function RatingTile({
  label,
  short,
  value,
  rank,
  totalTeams,
}: {
  label: string;
  short: string;
  value: string;
  rank: number | null | undefined;
  totalTeams: number;
}) {
  const band = rankBand(rank, totalTeams);
  return (
    <div className="team-v2-rating-tile">
      <div>
        <span>{label}</span>
        <small>{short}</small>
      </div>
      <StatCell value={value} rank={rank} totalTeams={totalTeams} />
    </div>
  );
}

function StatCell({ value, rank, totalTeams }: StatDatum) {
  const band = rankBand(rank, totalTeams);
  return (
    <span className="team-v2-stat">
      <strong className="mono">{value}</strong>
      <em className={band ? `team-v2-rank team-v2-rank--${band}` : "team-v2-rank"}>{rankText(rank)}</em>
    </span>
  );
}

function OverviewTab({
  latest,
  teamStats,
  advanced,
  advancedRows,
  totalStatted,
  slug,
  label,
}: {
  latest: SeasonRow;
  teamStats: TeamStatsRow | null | undefined;
  advanced: AdvancedRow | undefined;
  advancedRows: AdvancedRow[];
  totalStatted: number;
  slug: string;
  label: string | null;
}) {
  if (teamStats === undefined || advanced === undefined) {
    return <div className="weekly-state">Loading team analytics…</div>;
  }
  if (!teamStats || !advanced) {
    return <div className="weekly-state">This season&rsquo;s full team profile is not published yet.</div>;
  }

  const epaOff = advancedRank(advancedRows, slug, "epaAdj");
  const epaDef = advancedRank(advancedRows, slug, "epaAdjAllowed");
  const passOff = advancedRank(advancedRows, slug, "passEpaAdj");
  const passDef = advancedRank(advancedRows, slug, "passEpaAdjAllowed");
  const rushOff = advancedRank(advancedRows, slug, "rushEpaAdj");
  const rushDef = advancedRank(advancedRows, slug, "rushEpaAdjAllowed");

  const offense: GroupMetric[] = [
    { label: "EPA / Play", value: signed(advanced.epaAdj, 3), rank: epaOff.rank, totalTeams: epaOff.total },
    { label: "EPA / Pass", value: signed(advanced.passEpaAdj, 3), rank: passOff.rank, totalTeams: passOff.total },
    { label: "EPA / Rush", value: signed(advanced.rushEpaAdj, 3), rank: rushOff.rank, totalTeams: rushOff.total },
    { label: "Success Rate", value: pct(teamStats.successRate), rank: teamStats.successRateRank, totalTeams: totalStatted },
    { label: "Yards / Play", value: plain(teamStats.yardsPerPlay, 2), rank: teamStats.yardsPerPlayRank, totalTeams: totalStatted },
  ];

  const defense: GroupMetric[] = [
    { label: "EPA / Play", value: signed(advanced.epaAdjAllowed, 3), rank: epaDef.rank, totalTeams: epaDef.total },
    { label: "EPA / Pass", value: signed(advanced.passEpaAdjAllowed, 3), rank: passDef.rank, totalTeams: passDef.total },
    { label: "EPA / Rush", value: signed(advanced.rushEpaAdjAllowed, 3), rank: rushDef.rank, totalTeams: rushDef.total },
    { label: "Success Rate", value: pct(teamStats.successRateAllowed), rank: teamStats.successRateAllowedRank, totalTeams: totalStatted },
    { label: "Yards / Play", value: plain(teamStats.yardsPerPlayAllowed, 2), rank: teamStats.yardsPerPlayAllowedRank, totalTeams: totalStatted },
  ];

  return (
    <div className="team-v2-overview">
      <div className="team-v2-panel-heading">
        <div>
          <span>Season snapshot</span>
          <h2>{latest.team} at a glance</h2>
        </div>
        <small>{label ? `Through ${label}` : "Latest published data"}</small>
      </div>

      <div className="team-v2-overview-grid">
        <MiniProfile title="Offense" subtitle={`#${latest.adjORank ?? "—"} Adj. Off`} metrics={offense} />
        <MiniProfile title="Defense" subtitle={`#${latest.adjDRank ?? "—"} Adj. Def`} metrics={defense} />
      </div>

      <div className="team-v2-context-strip">
        <ContextStat label="Explosive %" value={pct(teamStats.explosivePlayRate)} rank={teamStats.explosivePlayRateRank} total={totalStatted} />
        <ContextStat label="Explosive Allowed" value={pct(teamStats.explosivePlayRateAllowed)} rank={teamStats.explosivePlayRateAllowedRank} total={totalStatted} />
        <ContextStat label="Finishing" value={plain(teamStats.finishingRate, 2)} rank={teamStats.finishingRateRank} total={totalStatted} />
        <ContextStat label="Finishing Allowed" value={plain(teamStats.finishingRateAllowed, 2)} rank={teamStats.finishingRateAllowedRank} total={totalStatted} />
        <ContextStat label="Havoc Forced" value={pct(teamStats.havocRateForced)} rank={teamStats.havocRateForcedRank} total={totalStatted} />
      </div>
    </div>
  );
}

function MiniProfile({ title, subtitle, metrics }: { title: string; subtitle: string; metrics: GroupMetric[] }) {
  return (
    <section className="team-v2-mini-profile">
      <div className="team-v2-mini-profile__head">
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      {metrics.map((metric) => (
        <div className="team-v2-mini-profile__row" key={metric.label}>
          <span>{metric.label}</span>
          <StatCell value={metric.value} rank={metric.rank} totalTeams={metric.totalTeams} />
        </div>
      ))}
    </section>
  );
}

function ContextStat({ label, value, rank, total }: { label: string; value: string; rank: number | null | undefined; total: number }) {
  return (
    <div className="team-v2-context-stat">
      <span>{label}</span>
      <StatCell value={value} rank={rank} totalTeams={total} />
    </div>
  );
}

function GroupedMetrics({
  eyebrow,
  title,
  note,
  groups,
}: {
  eyebrow: string;
  title: string;
  note: string;
  groups: MetricGroup[];
}) {
  if (!groups.length) return <div className="weekly-state">This profile is not published yet.</div>;
  return (
    <div className="team-v2-grouped">
      <div className="team-v2-panel-heading">
        <div>
          <span>{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        <small>{note}</small>
      </div>
      <div className="team-v2-group-grid">
        {groups.map((group) => (
          <section className="team-v2-group" key={group.title}>
            <h3>{group.title}</h3>
            {group.metrics.map((metric) => (
              <div className="team-v2-group__row" key={metric.label}>
                <span>
                  {metric.label}
                  {metric.note ? <TipTrigger text={metric.note} /> : null}
                </span>
                <StatCell value={metric.value} rank={metric.rank} totalTeams={metric.totalTeams} />
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}

function offenseGroups(
  latest: SeasonRow,
  stats: TeamStatsRow | null | undefined,
  advanced: AdvancedRow | undefined,
  advancedRows: AdvancedRow[],
  slug: string,
  totalStatted: number,
  totalRated: number,
): MetricGroup[] {
  if (!stats) return [];
  const adjExp = { rank: stats.adjustedExplosivenessOffenseRank, total: totalStatted };
  const adjFin = { rank: stats.adjustedFinishingOffenseRank, total: totalStatted };
  const adjHavoc = { rank: stats.adjustedHavocOffenseRank, total: totalStatted };
  const epa = advancedRank(advancedRows, slug, "epaAdj");

  return [
    {
      title: "Overall",
      metrics: [
        { label: "Adj. Off", value: signed(latest.adjO, 2), rank: latest.adjORank, totalTeams: totalRated },
        { label: "EPA / Play", value: signed(advanced?.epaAdj, 3), rank: epa.rank, totalTeams: epa.total },
        { label: "Yards / Play", value: plain(stats.yardsPerPlay, 2), rank: stats.yardsPerPlayRank, totalTeams: totalStatted },
        { label: "Success Rate", value: pct(stats.successRate), rank: stats.successRateRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Style",
      metrics: [
        { label: "Pass SR", value: pct(stats.passSuccessRate), rank: stats.passSuccessRateRank, totalTeams: totalStatted },
        { label: "Rush SR", value: pct(stats.rushSuccessRate), rank: stats.rushSuccessRateRank, totalTeams: totalStatted },
        { label: "Pass Rate", value: pct(stats.passRate), rank: null, totalTeams: 0 },
        { label: "Pace", value: `${plain(stats.pace, 1)} plays/g`, rank: null, totalTeams: 0 },
      ],
    },
    {
      title: "Explosiveness",
      metrics: [
        { label: "Adjusted", value: signed(stats.adjustedExplosivenessOffense, 2), rank: adjExp.rank, totalTeams: adjExp.total },
        { label: "Raw %", value: pct(stats.explosivePlayRate), rank: stats.explosivePlayRateRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Finishing",
      metrics: [
        { label: "Adjusted", value: signed(stats.adjustedFinishingOffense, 2), rank: adjFin.rank, totalTeams: adjFin.total },
        { label: "Pts / Opp", value: plain(stats.finishingRate, 2), rank: stats.finishingRateRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Field Position",
      metrics: [
        { label: "Adjusted", value: signed(stats.fieldPositionEdge, 1), rank: stats.fieldPositionEdgeRank, totalTeams: totalStatted },
        { label: "Raw", value: fieldPos(stats.fieldPositionRaw, 1), rank: stats.fieldPositionRawRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Havoc",
      metrics: [
        { label: "Avoid Adj", value: signed(stats.adjustedHavocOffense, 3), rank: adjHavoc.rank, totalTeams: adjHavoc.total },
        { label: "Allowed %", value: pct(stats.havocRateAllowed), rank: stats.havocRateAllowedRank, totalTeams: totalStatted },
      ],
    },
  ];
}

function defenseGroups(
  latest: SeasonRow,
  stats: TeamStatsRow | null | undefined,
  advanced: AdvancedRow | undefined,
  advancedRows: AdvancedRow[],
  slug: string,
  totalStatted: number,
  totalRated: number,
): MetricGroup[] {
  if (!stats) return [];
  const epa = advancedRank(advancedRows, slug, "epaAdjAllowed");

  return [
    {
      title: "Overall",
      metrics: [
        { label: "Adj. Def", value: signed(latest.adjD, 2), rank: latest.adjDRank, totalTeams: totalRated },
        { label: "EPA / Play Allowed", value: signed(advanced?.epaAdjAllowed, 3), rank: epa.rank, totalTeams: epa.total },
        { label: "YPP Allowed", value: plain(stats.yardsPerPlayAllowed, 2), rank: stats.yardsPerPlayAllowedRank, totalTeams: totalStatted },
        { label: "Success Allowed", value: pct(stats.successRateAllowed), rank: stats.successRateAllowedRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Opponent Style",
      metrics: [
        { label: "Pass SR Allowed", value: pct(stats.passSuccessRateAllowed), rank: stats.passSuccessRateAllowedRank, totalTeams: totalStatted },
        { label: "Rush SR Allowed", value: pct(stats.rushSuccessRateAllowed), rank: stats.rushSuccessRateAllowedRank, totalTeams: totalStatted },
        { label: "Opponent Pass Rate", value: pct(stats.passRateAgainst), rank: null, totalTeams: 0 },
      ],
    },
    {
      title: "Explosiveness",
      metrics: [
        { label: "Adjusted", value: signed(stats.adjustedExplosivenessDefense, 2), rank: stats.adjustedExplosivenessDefenseRank, totalTeams: totalStatted },
        { label: "Allowed %", value: pct(stats.explosivePlayRateAllowed), rank: stats.explosivePlayRateAllowedRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Finishing",
      metrics: [
        { label: "Adjusted", value: signed(stats.adjustedFinishingDefense, 2), rank: stats.adjustedFinishingDefenseRank, totalTeams: totalStatted },
        { label: "Pts / Opp Allowed", value: plain(stats.finishingRateAllowed, 2), rank: stats.finishingRateAllowedRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Field Position",
      metrics: [
        { label: "Opp Start", value: fieldPos(stats.fieldPositionRawAllowed, 1), rank: stats.fieldPositionRawAllowedRank, totalTeams: totalStatted },
      ],
    },
    {
      title: "Havoc",
      metrics: [
        { label: "Forced Adj", value: signed(stats.adjustedHavocDefense, 3), rank: stats.adjustedHavocDefenseRank, totalTeams: totalStatted },
        { label: "Forced %", value: pct(stats.havocRateForced), rank: stats.havocRateForcedRank, totalTeams: totalStatted },
      ],
    },
  ];
}

function EdgeTable({
  team,
  row,
  rows,
  sections,
  formatter,
  note,
}: {
  team: string;
  row: AdvancedRow | undefined;
  rows: AdvancedRow[];
  sections: EdgeSection[];
  formatter: (value: number | null | undefined) => string;
  note: string;
}) {
  if (!row) return <div className="weekly-state">Advanced data is not published for this team yet.</div>;

  return (
    <div className="team-v2-edge-wrap">
      <div className="team-v2-panel-heading">
        <div>
          <span>Advanced analytics</span>
          <h2>{team}</h2>
        </div>
        <small>{note}</small>
      </div>

      <div className="team-v2-edge-table" role="table" aria-label={`${team} advanced analytics`}>
        <div className="team-v2-edge-head" role="row">
          <span>Metric</span>
          <span>Offense</span>
          <span>Defense</span>
          <span>Margin</span>
        </div>
        {sections.map((section) => (
          <div className="team-v2-edge-section" key={section.title}>
            <div className="team-v2-edge-section__title">{section.title}</div>
            {section.metrics.map((metric) => {
              const offenseValue = advancedNumber(row, metric.offenseKey);
              const defenseValue = advancedNumber(row, metric.defenseKey);
              const margin = marginValue(row, metric.offenseKey, metric.defenseKey);
              const offenseRank = advancedRank(rows, row.slug, metric.offenseKey);
              const defenseRank = advancedRank(rows, row.slug, metric.defenseKey);
              const marginInfo = marginRank(rows, row.slug, metric.offenseKey, metric.defenseKey);
              return (
                <div className="team-v2-edge-row" role="row" key={`${section.title}-${metric.label}`}>
                  <span className="team-v2-edge-row__label">{metric.label}</span>
                  <StatCell value={formatter(offenseValue)} rank={offenseRank.rank} totalTeams={offenseRank.total} />
                  <StatCell value={formatter(defenseValue)} rank={defenseRank.rank} totalTeams={defenseRank.total} />
                  <StatCell value={formatter(margin)} rank={marginInfo.rank} totalTeams={marginInfo.total} />
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

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
    <div className="team-v2-schedule-wrap">
      <div className="team-v2-panel-heading">
        <div>
          <span>Schedule</span>
          <h2>Results & upcoming matchups</h2>
        </div>
        <small>Click any opponent or View Matchup to open the pregame comparison.</small>
      </div>
      <div className="table-scroll" role="region" aria-label="Team schedule" tabIndex={0}>
        <table className="data-table schedule-table team-v2-schedule">
          <thead>
            <tr>
              <th scope="col">Week</th>
              <th scope="col">Opponent</th>
              <th scope="col">Result</th>
              <th scope="col" className="num">Opp Adj. Net<TipTrigger text="The opponent's LEILA Adj. Net from the week strictly before this game." /></th>
              <th scope="col" className="team-v2-schedule__action">Matchup</th>
            </tr>
          </thead>
          <tbody>
            {games.map((game) => {
              const isHome = game.homeSlug === slug;
              const opponent = isHome ? game.awayTeam : game.homeTeam;
              const opponentSlug = isHome ? game.awaySlug : game.homeSlug;
              const opponentId = isHome ? game.awayTeamId : game.homeTeamId;
              const ourPoints = isHome ? game.homePoints : game.awayPoints;
              const opponentPoints = isHome ? game.awayPoints : game.homePoints;
              const pregameWeek = rankings ? pregameRatingWeek(rankings, game.week) : null;
              const opponentRow = rankings && pregameWeek !== null
                ? (rankings.byWeek[String(pregameWeek)] || []).find((row) => row.slug === opponentSlug)
                : undefined;
              const weekLabel = weekLabels?.[String(game.week)] || `Wk ${game.week}`;
              const matchupHref = year ? `/matchup/${year}/${encodeURIComponent(game.gameId)}` : "#";

              let result = "—";
              let resultClass = "";
              if (game.completed && !na(ourPoints) && !na(opponentPoints)) {
                result = ourPoints! > opponentPoints! ? `W ${ourPoints}-${opponentPoints}` : `L ${ourPoints}-${opponentPoints}`;
                resultClass = ourPoints! > opponentPoints! ? "schedule-win" : "schedule-loss";
              } else if (game.startDate && !game.startTimeTBD) {
                result = new Date(game.startDate).toLocaleDateString("en-US", { month: "short", day: "numeric" });
              }

              return (
                <tr key={game.gameId}>
                  <td className="mono">{weekLabel}</td>
                  <td>
                    <Link href={matchupHref} className="schedule-opp team-v2-matchup-link" prefetch={false}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl(opponentId)} alt="" loading="lazy" decoding="async" />
                      <span>{game.neutralSite ? "vs" : isHome ? "vs" : "@"} {opponent}</span>
                    </Link>
                  </td>
                  <td className={`mono ${resultClass}`}>{result}</td>
                  <td className="num mono">
                    {opponentRow && !na(opponentRow.adjEM) ? `${signed(opponentRow.adjEM, 1)} · ${rankText(opponentRow.rank)}` : "—"}
                  </td>
                  <td className="team-v2-schedule__action">
                    {year ? <Link href={matchupHref} prefetch={false}>View Matchup →</Link> : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="team-v2-method-note">Opponent Adj. Net is frozen to the snapshot strictly before each game. Matchup pages use the same pregame-only logic.</p>
    </div>
  );
}

function HistoryStat({
  value,
  rank,
  digits,
  primary,
  selected,
}: {
  value: number | null;
  rank?: number | null;
  digits: number;
  primary?: boolean;
  selected?: boolean;
}) {
  return (
    <td className={(primary ? "num mono primary-stat history-metric-cell" : "num mono history-metric-cell") + (selected ? " mobile-selected-history-metric" : "")}>
      {na(value) ? "—" : signed(value, digits)}
      {!primary && !na(rank) ? <span className="rank-sub">#{rank}</span> : null}
    </td>
  );
}
