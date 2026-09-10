"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { logoUrl } from "@/lib/teamCode";
import { getMeta, getPredictionsWeek, getPreseasonPower, getRankingsSeason, getScheduleSeason } from "@/lib/data";
import type { PredictionGame, PreseasonPower, RankingsSeason, ScheduleGame, ScheduleSeason } from "@/lib/types";

type PredictionsFilter = "all" | "top25" | "best";

const FILTERS: { key: PredictionsFilter; label: string }[] = [
  { key: "all", label: "All Games" },
  { key: "top25", label: "Top 25" },
  { key: "best", label: "Best Matchups" },
];

// Rankings publish a week later than predictions can (see the lookahead
// comment below) -- so "ranked" for a given game week means the latest
// rankings week that had already posted before that week's games kicked off.
function pregameRankWeek(rankings: RankingsSeason, gameWeek: number): number | null {
  const prior = rankings.weeks.filter((w) => w < gameWeek);
  return prior.length ? prior[prior.length - 1] : null;
}

function gameTimeLabel(game: ScheduleGame | undefined): string {
  if (!game) return "Time TBA";
  if (game.completed) return "Final";
  if (game.startTimeTBD || !game.startDate) return "Time TBA";
  const date = new Date(game.startDate);
  if (Number.isNaN(date.getTime())) return "Time TBA";
  return date.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function sortByKickoff(games: PredictionGame[], scheduleByGameId: Map<string, ScheduleGame>): PredictionGame[] {
  const kickoffMs = (g: PredictionGame): number => {
    const sched = scheduleByGameId.get(g.gameId);
    if (!sched || sched.startTimeTBD || !sched.startDate) return Infinity;
    const ms = new Date(sched.startDate).getTime();
    return Number.isNaN(ms) ? Infinity : ms;
  };
  return [...games].sort((a, b) => kickoffMs(a) - kickoffMs(b) || a.gameId.localeCompare(b.gameId));
}

function signedMargin(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(1);
}

function pct(n: number | null): string {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

type ConfidenceTier = { key: "lock" | "lean" | "toss-up"; label: string };

function confidenceTier(n: number | null): ConfidenceTier {
  if (n === null) return { key: "toss-up", label: "Unrated" };
  if (n >= 0.85) return { key: "lock", label: "Lock" };
  if (n >= 0.65) return { key: "lean", label: "Lean" };
  return { key: "toss-up", label: "Toss-up" };
}

export default function PredictionsPage() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [status, setStatus] = useState<"loading" | "no-data" | "ready">("loading");
  const [season, setSeason] = useState<number | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [games, setGames] = useState<PredictionGame[]>([]);
  const [power, setPower] = useState<PreseasonPower | null>(null);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null>(null);
  const [filter, setFilter] = useState<PredictionsFilter>("all");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const meta = await getMeta();
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const seasonData = await getRankingsSeason(latestSeason);
      const currentWeek = seasonData.weeks[seasonData.weeks.length - 1];
      if (cancelled) return;
      setSeason(latestSeason);
      setWeek(currentWeek);
      setRankings(seasonData);

      getPreseasonPower(latestSeason).then((p) => { if (!cancelled) setPower(p); }).catch(() => {});
      getScheduleSeason(latestSeason).then((s) => { if (!cancelled) setSchedule(s); }).catch(() => {});

      // Predictions are published for early-season weeks specifically (see
      // early_season_predictions.py) -- a week with no file yet just means
      // this model hasn't scored it (either too early in the pipeline, or
      // past the early-season window where LEILA's own AdjNet/SOR takes over).
      // The predictions pipeline often runs ahead of `currentWeek`, which
      // tracks the *rankings* week (only bumped once a week is fully final)
      // -- so a slate for the upcoming week can already be published while
      // rankings are still sitting on the prior one. Probe a couple weeks
      // ahead first and walk backward, landing on the latest published
      // slate; falling back below currentWeek covers a Tuesday-morning
      // visitor mid-week who wants last week's slate wrapping up, not a
      // blank page.
      const lookahead = 2;
      const candidates: number[] = [];
      for (let w = currentWeek + lookahead; w >= Math.max(1, currentWeek - 1); w--) candidates.push(w);
      for (const candidate of candidates) {
        const predictions = await getPredictionsWeek(latestSeason, candidate);
        if (cancelled) return;
        if (predictions && predictions.games.length > 0) {
          setWeek(candidate);
          setGames(predictions.games);
          setStatus("ready");
          return;
        }
      }
      setStatus("no-data");
    })().catch((error: Error) => { if (!cancelled) setLoadError(error); });
    return () => {
      cancelled = true;
    };
  }, []);

  const scheduleByGameId = useMemo(() => {
    const map = new Map<string, ScheduleGame>();
    if (schedule && week !== null) {
      for (const g of schedule.byWeek[String(week)] ?? []) map.set(g.gameId, g);
    }
    return map;
  }, [schedule, week]);

  const topRanked = useMemo(() => {
    const map = new Map<number, number>();
    if (!rankings || week === null) return map;
    const rankWeek = pregameRankWeek(rankings, week);
    if (rankWeek === null) return map;
    for (const row of rankings.byWeek[String(rankWeek)] ?? []) {
      if (row.rank !== null && row.rank <= 25) map.set(row.teamId, row.rank);
    }
    return map;
  }, [rankings, week]);

  const orderedGames = useMemo(() => sortByKickoff(games, scheduleByGameId), [games, scheduleByGameId]);

  const gamesByFilter = useMemo(() => ({
    all: orderedGames,
    top25: orderedGames.filter((g) => topRanked.has(g.homeTeamId) || topRanked.has(g.awayTeamId)),
    best: orderedGames.filter((g) => topRanked.has(g.homeTeamId) && topRanked.has(g.awayTeamId)),
  }), [orderedGames, topRanked]);

  const rankOf = (teamId: number): number | null => topRanked.get(teamId) ?? null;

  const visibleGames = gamesByFilter[filter];

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#predictionsContent">Skip to predictions</a>
      <SiteHeader tagline="Weekly Game Predictions" />
      <SiteNav />

      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Ratings</Link>
        <span className="crumb-sep">/</span>
        <span className="crumb-current">Predictions</span>
      </nav>

      <section className="advanced-intro">
        <div className="advanced-intro__copy">
          <div className="advanced-intro__eyebrow">
            <span className="eyebrow">Weekly Predictions</span>
            <span className="advanced-intro__badge">Beta</span>
          </div>
          <h1>This week&rsquo;s game-by-game picks</h1>
          <p>
            Model-projected winners and margins for published early-season FBS matchups. Weeks 1&ndash;5 blend a
            preseason power rating with real results as they come in; once a team&rsquo;s schedule is long enough
            for LEILA&rsquo;s own opponent-adjusted Adj. Net to take over, predictions retire in favor of that.
          </p>
        </div>
      </section>

      <main id="predictionsContent" className="container predictions-main">
        {status === "loading" ? (
          <div className="predictions-state">Loading predictions…</div>
        ) : status === "no-data" ? (
          <div className="predictions-state">
            <h2>No predictions published for {season} yet</h2>
            <p>
              The season is currently through Week {week}. Predictions publish once a week&rsquo;s prior week is
              fully final and this early-season model can still add something &mdash; check back soon.
            </p>
          </div>
        ) : (
          <div className="predictions-list">
            <div className="weekly-section-heading">
              <div>
                <span className="eyebrow">LEILA Predictions</span>
                <h2>Week {week}</h2>
              </div>
              <span>{predictionsSummary(games)}</span>
            </div>

            <div className="predictions-filters" role="tablist" aria-label="Filter predictions">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  role="tab"
                  aria-selected={filter === f.key}
                  className={`predictions-filters__btn${filter === f.key ? " active" : ""}`}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                  <span className="predictions-filters__count">{gamesByFilter[f.key].length}</span>
                </button>
              ))}
            </div>

            {visibleGames.length === 0 ? (
              <p className="predictions-empty">
                No games match this filter this week &mdash; try{" "}
                <button type="button" className="predictions-empty__reset" onClick={() => setFilter("all")}>
                  All Games
                </button>
                .
              </p>
            ) : (
              <div className="predictions-grid">
                {visibleGames.map((g) => (
                  <PredictionRow
                    key={g.gameId}
                    game={g}
                    schedule={scheduleByGameId.get(g.gameId)}
                    homeRank={rankOf(g.homeTeamId)}
                    awayRank={rankOf(g.awayTeamId)}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {power ? <PreseasonPowerTable power={power} /> : null}
      </main>

      <SiteFooter note="Weekly Predictions are model-generated projections, not betting advice. Early-season margins and win probabilities blend LEILA's preseason power rating with real results as they accumulate; see the Preseason Power table above for that model's own walk-forward accuracy record." />
    </>
  );
}

function predictionsSummary(games: PredictionGame[]): string {
  const locks = games.filter((g) => (g.confidence ?? 0) >= 0.85).length;
  const tossUps = games.filter((g) => g.confidence !== null && g.confidence < 0.65).length;
  const parts = [`${games.length} game${games.length === 1 ? "" : "s"}`];
  if (locks > 0) parts.push(`${locks} lock${locks === 1 ? "" : "s"}`);
  if (tossUps > 0) parts.push(`${tossUps} toss-up${tossUps === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

function PredictionRow({
  game,
  schedule,
  homeRank,
  awayRank,
}: {
  game: PredictionGame;
  schedule: ScheduleGame | undefined;
  homeRank: number | null;
  awayRank: number | null;
}) {
  const tier = confidenceTier(game.confidence);
  const homeIsWinner = game.predictedWinner === game.homeTeam;

  return (
    <article className={`predictions-row predictions-row--${tier.key}`}>
      <div className="predictions-row__time">{gameTimeLabel(schedule)}</div>
      <div className="predictions-row__matchup">
        <TeamChip team={game.awayTeam} teamId={game.awayTeamId} isWinner={!homeIsWinner} rank={awayRank} />
        <span className="predictions-row__at">at</span>
        <TeamChip team={game.homeTeam} teamId={game.homeTeamId} isWinner={homeIsWinner} rank={homeRank} />
      </div>

      <div className="predictions-row__pick">
        <span className="predictions-row__pick-label">Pick</span>
        <strong>{game.predictedWinner}</strong>
        <span className="mono predictions-row__margin">{signedMargin(game.predictedMargin)}</span>
      </div>

      <div className="predictions-row__confidence">
        <span className={`predictions-row__tier predictions-row__tier--${tier.key}`}>{tier.label}</span>
        <div className="predictions-row__meter" role="presentation">
          <div
            className="predictions-row__meter-fill"
            style={{ width: `${Math.round((game.confidence ?? 0) * 100)}%` }}
          />
        </div>
        <span className="mono predictions-row__confidence-value">{pct(game.confidence)}</span>
      </div>
    </article>
  );
}

function PreseasonPowerTable({ power }: { power: PreseasonPower }) {
  const top = power.teams.slice(0, 25);
  return (
    <section className="predictions-power">
      <div className="weekly-section-heading">
        <div>
          <span className="eyebrow">The Model Behind The Picks</span>
          <h2>Preseason Power</h2>
        </div>
        <span>Top 25 · {power.season}</span>
      </div>
      <p className="predictions-power__intro">
        Fit from prior-season results, recruiting and QB continuity only &mdash; never AP/Coaches Poll, SP+, FPI or
        betting lines. Held fixed for the season once frozen; this is what feeds the early-season blend above.
      </p>
      <ol className="predictions-power__list">
        {top.map((t) => (
          <li key={t.team}>
            <span className="predictions-power__rank">{t.rank}</span>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={logoUrl(t.teamId ?? 0)} alt="" loading="lazy" decoding="async" />
            <span className="predictions-power__team">{t.team}</span>
            <span className="predictions-power__conf">{t.conf}</span>
            <span className="mono predictions-power__score">{signedMargin(t.powerScore)}</span>
          </li>
        ))}
      </ol>
      <p className="predictions-power__backtest">
        Walk-forward accuracy on {power.backtest.n.toLocaleString()} historical early-season games: {power.backtest.winnerPct.toFixed(1)}%
        straight-up, {power.backtest.mae.toFixed(1)}-point average error. {power.backtest.description}
      </p>
    </section>
  );
}

function TeamChip({
  team,
  teamId,
  isWinner,
  rank,
}: {
  team: string;
  teamId: number;
  isWinner: boolean;
  rank: number | null;
}) {
  return (
    <span className={`predictions-row__team${isWinner ? " predictions-row__team--winner" : ""}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={logoUrl(teamId)} alt="" loading="lazy" decoding="async" />
      {rank !== null ? <span className="predictions-row__rank-badge">#{rank}</span> : null}
      {team}
    </span>
  );
}
