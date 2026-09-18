"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import MarketOddsCard from "@/components/MarketOddsCard";
import LeilaLoadingState from "@/components/LeilaLoadingState";
import { logoUrl } from "@/lib/teamCode";
import {
  PremiumAccessError,
  getMeta,
  getMarketLinesSeason,
  getPredictionsWeek,
  getPreseasonPower,
  getRankingsSeason,
  getScheduleSeason,
} from "@/lib/data";
import type {
  MarketLinesSeason,
  PredictionGame,
  PreseasonPower,
  RankingsRow,
  RankingsSeason,
  ScheduleGame,
  ScheduleSeason,
} from "@/lib/types";

type GamesFilter = "all" | "top25" | "best";
type SortKey = "kickoff" | "matchup" | "pick" | "confidence";
type Access = "unknown" | "locked" | "unlocked";

// The early-season model only scores games when it has enough information to
// publish a graded prediction. The schedule should still show every FBS-vs-FBS
// game, but games without a complete model output are explicitly labeled as
// "Not enough data" instead of presenting an Adj. Net comparison as a pick.
type Row = {
  game: ScheduleGame;
  homeRating: RankingsRow | undefined;
  awayRating: RankingsRow | undefined;
  prediction: PredictionGame | undefined;
  // Signed to the home team (positive = home favored) so every row sorts on
  // the same axis regardless of who the model likes. Adj. Net can still be
  // computed internally for context, but only real graded picks sort as picks.
  edgeValue: number | null;
  edgeIsRealPick: boolean;
};

const FILTERS: { key: GamesFilter; label: string }[] = [
  { key: "all", label: "All Games" },
  { key: "top25", label: "Top 25" },
  { key: "best", label: "Best Matchups" },
];

const EARLY_BLEND = [
  { games: "0", prior: 100, live: 0 },
  { games: "1", prior: 75, live: 25 },
  { games: "2", prior: 50, live: 50 },
  { games: "3", prior: 25, live: 75 },
  { games: "4+", prior: 0, live: 100 },
];

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

function pregameRatingWeek(rankings: RankingsSeason, gameWeek: number): number | null {
  const prior = rankings.weeks.filter((w) => w < gameWeek);
  return prior.length ? prior[prior.length - 1] : null;
}

// schedule.currentWeek tracks the latest week with any started game -- once
// that week's games wrap (e.g. Monday after a Thursday-Saturday slate), it
// still points at the just-finished week until the next week's first
// kickoff. A page about picking upcoming games should default to the next
// week with something left to predict, not the one that just ended.
function defaultPredictionsWeek(schedule: ScheduleSeason): number {
  for (const week of schedule.weeks) {
    const games = schedule.byWeek[String(week)] ?? [];
    if (games.some((g) => !g.completed)) return week;
  }
  return schedule.currentWeek;
}

function gameTimeParts(game: ScheduleGame): { date: string; time: string } {
  if (game.completed) return { date: "Final", time: "" };
  if (game.startTimeTBD || !game.startDate) return { date: "Time TBA", time: "" };
  const date = new Date(game.startDate);
  if (Number.isNaN(date.getTime())) return { date: "Time TBA", time: "" };
  return {
    date: date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      timeZone: "America/New_York",
    }),
    time: date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: "America/New_York",
      timeZoneName: "short",
    }),
  };
}

function kickoffMs(game: ScheduleGame): number {
  if (game.startTimeTBD || !game.startDate) return Infinity;
  const ms = new Date(game.startDate).getTime();
  return Number.isNaN(ms) ? Infinity : ms;
}

function signed(value: number, digits = 1): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function pct(n: number | null): string {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

function pickText(winner: string, margin: number): string {
  return `${winner} to win by ${Math.abs(margin).toFixed(1)}`;
}

export default function PredictionsPage() {
  const router = useRouter();
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [season, setSeason] = useState<number | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
  const [marketLines, setMarketLines] = useState<MarketLinesSeason | null>(null);
  const [power, setPower] = useState<PreseasonPower | null>(null);
  const [selectedWeek, setSelectedWeek] = useState<number | null>(null);
  const [predictionsByWeek, setPredictionsByWeek] = useState<Map<number, PredictionGame[]>>(new Map());
  const [access, setAccess] = useState<Access>("unknown");
  const [filter, setFilter] = useState<GamesFilter>("all");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("kickoff");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const meta = await getMeta();
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const [scheduleData, rankingData, marketData] = await Promise.all([
        getScheduleSeason(latestSeason),
        getRankingsSeason(latestSeason),
        getMarketLinesSeason(latestSeason),
      ]);
      if (cancelled) return;
      setSeason(latestSeason);
      setSchedule(scheduleData);
      setRankings(rankingData);
      setMarketLines(marketData);
      setSelectedWeek(scheduleData ? defaultPredictionsWeek(scheduleData) : null);
      getPreseasonPower(latestSeason).then((p) => { if (!cancelled) setPower(p); }).catch(() => {});
    })().catch((error: Error) => { if (!cancelled) setLoadError(error); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    document.title = season ? `${season} Predictions | LEILA Ratings` : "Predictions | LEILA Ratings";
  }, [season]);

  // Fetch each week's predictions on demand as the user browses weeks, and
  // remember a season-wide "locked" verdict the first time we see one so we
  // stop making requests we already know will 401/403 -- the game list
  // itself never depends on this, only the Pick/Win % columns do.
  useEffect(() => {
    if (season === null || selectedWeek === null) return;
    if (access === "locked") return;
    if (predictionsByWeek.has(selectedWeek)) return;
    let cancelled = false;
    getPredictionsWeek(season, selectedWeek)
      .then((weekData) => {
        if (cancelled) return;
        setAccess("unlocked");
        setPredictionsByWeek((prev) => new Map(prev).set(selectedWeek, weekData?.games ?? []));
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof PremiumAccessError) {
          setAccess("locked");
          return;
        }
        // Non-access errors (network blip, 500) leave the game visible and
        // clearly mark the model output as unavailable instead of inventing a pick.
        setPredictionsByWeek((prev) => new Map(prev).set(selectedWeek, []));
      });
    return () => { cancelled = true; };
  }, [season, selectedWeek, access, predictionsByWeek]);

  const ratingWeek = useMemo(() => {
    if (!rankings || selectedWeek === null) return null;
    return pregameRatingWeek(rankings, selectedWeek);
  }, [rankings, selectedWeek]);

  const ratingsBySlug = useMemo(() => {
    const map = new Map<string, RankingsRow>();
    if (!rankings || ratingWeek === null) return map;
    for (const row of rankings.byWeek[String(ratingWeek)] || []) map.set(row.slug, row);
    return map;
  }, [rankings, ratingWeek]);

  const topRanked = useMemo(() => {
    const map = new Map<number, number>();
    if (!rankings || ratingWeek === null) return map;
    for (const row of rankings.byWeek[String(ratingWeek)] || []) {
      if (row.rank !== null && row.rank <= 25) map.set(row.teamId, row.rank);
    }
    return map;
  }, [rankings, ratingWeek]);

  const predictionsByGameId = useMemo(() => {
    const map = new Map<string, PredictionGame>();
    if (selectedWeek === null) return map;
    for (const p of predictionsByWeek.get(selectedWeek) ?? []) map.set(p.gameId, p);
    return map;
  }, [predictionsByWeek, selectedWeek]);

  const marketByGameId = useMemo(() => marketLines?.games ?? {}, [marketLines]);

  const rows = useMemo((): Row[] => {
    if (!schedule || selectedWeek === null) return [];
    const games = schedule.byWeek[String(selectedWeek)] ?? [];
    return games.map((game) => {
      const homeRating = ratingsBySlug.get(game.homeSlug);
      const awayRating = ratingsBySlug.get(game.awaySlug);
      const prediction = predictionsByGameId.get(game.gameId);
      let edgeValue: number | null = null;
      let edgeIsRealPick = false;
      if (prediction) {
        edgeValue = prediction.predictedWinner === game.homeTeam ? prediction.predictedMargin : -prediction.predictedMargin;
        edgeIsRealPick = true;
      } else if (access === "unlocked" && !na(homeRating?.adjEM) && !na(awayRating?.adjEM)) {
        edgeValue = homeRating!.adjEM! - awayRating!.adjEM!;
      }
      return { game, homeRating, awayRating, prediction, edgeValue, edgeIsRealPick };
    });
  }, [schedule, selectedWeek, ratingsBySlug, predictionsByGameId, access]);

  const rowsByFilter = useMemo(() => ({
    all: rows,
    top25: rows.filter((r) => topRanked.has(r.game.homeTeamId) || topRanked.has(r.game.awayTeamId)),
    best: rows.filter((r) => topRanked.has(r.game.homeTeamId) && topRanked.has(r.game.awayTeamId)),
  }), [rows, topRanked]);

  const searched = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const base = rowsByFilter[filter];
    if (!needle) return base;
    return base.filter((r) => r.game.homeTeam.toLowerCase().includes(needle) || r.game.awayTeam.toLowerCase().includes(needle));
  }, [rowsByFilter, filter, search]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const out = [...searched];
    out.sort((a, b) => {
      switch (sortKey) {
        case "matchup":
          return a.game.homeTeam.localeCompare(b.game.homeTeam) * dir;
        case "pick": {
          const av = a.edgeIsRealPick ? a.edgeValue : null;
          const bv = b.edgeIsRealPick ? b.edgeValue : null;
          if (av === null) return bv === null ? 0 : 1;
          if (bv === null) return -1;
          return (Math.abs(av) - Math.abs(bv)) * dir;
        }
        case "confidence": {
          const av = a.prediction?.confidence ?? null;
          const bv = b.prediction?.confidence ?? null;
          if (av === null) return bv === null ? 0 : 1;
          if (bv === null) return -1;
          return (av - bv) * dir;
        }
        case "kickoff":
        default:
          return (kickoffMs(a.game) - kickoffMs(b.game)) * dir;
      }
    });
    return out;
  }, [searched, sortKey, sortDir]);

  function onHeaderClick(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "kickoff" || key === "matchup" ? "asc" : "desc");
    }
  }

  function goToMatchup(gameId: string) {
    if (season === null) return;
    router.push(`/matchup/${season}/${encodeURIComponent(gameId)}`);
  }

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#predictionsContent">Skip to predictions</a>
      <SiteHeader tagline="Weekly Game Predictions" />
      <SiteNav />

      <section className="ratings-hero container" aria-labelledby="predictionsTitle">
        <div className="ratings-hero__copy">
          <span className="eyebrow">LEILA Predictions</span>
          <h1 id="predictionsTitle">{season ? `${season} Predictions` : "Predictions"}</h1>
          <p className="ratings-hero__description">
            Every scheduled game involving an FBS team, sortable and searchable. Early-season LEILA projections
            blend a frozen preseason prior with results already played. A graded pick requires complete model inputs
            for both teams; otherwise the game stays on the slate and is labeled Not enough data.
          </p>
        </div>
      </section>

      <main id="predictionsContent" className="container predictions-main">
        {schedule === undefined ? (
          <LeilaLoadingState variant="predictions" />
        ) : schedule === null ? (
          <p className="network-loading">Weekly schedule data is publishing with the next ratings refresh.</p>
        ) : (
          <>
            <div className="control-bar">
              <div className="control-bar__inner">
                <span className="control-label">Week</span>
                <nav className="week-nav" aria-label="Schedule week">
                  {schedule.weeks.map((week) => (
                    <button
                      key={week}
                      type="button"
                      className={week === selectedWeek ? "active" : undefined}
                      aria-pressed={week === selectedWeek}
                      onClick={() => setSelectedWeek(week)}
                    >
                      {schedule.weekLabels?.[String(week)] || `Wk ${week}`}
                    </button>
                  ))}
                </nav>

                <div className="filter-box">
                  <label className="sr-only" htmlFor="predictionsSearch">Search teams</label>
                  <input
                    id="predictionsSearch"
                    type="search"
                    placeholder="Search team…"
                    autoComplete="off"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
              </div>
              <div className="control-bar__inner control-bar__inner--secondary">
                <div className="predictions-filters" role="tablist" aria-label="Filter games">
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
                      <span className="predictions-filters__count">{rowsByFilter[f.key].length}</span>
                    </button>
                  ))}
                </div>
                {access === "locked" ? (
                  <Link className="utility-link predictions-unlock-link" href="/upgrade?feature=predictions">
                    Unlock picks &amp; win % →
                  </Link>
                ) : null}
              </div>
            </div>

            {sorted.length === 0 ? (
              <p className="network-loading">
                {search.trim() ? `No games match "${search}".` : "No games involving an FBS team are listed for this week."}
              </p>
            ) : (
              <div className="table-scroll" role="region" aria-label="Weekly predictions table" tabIndex={0}>
                <table className="data-table predictions-table">
                  <thead>
                    <tr>
                      <th scope="col" className="sortable" aria-sort={sortKey === "kickoff" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                        <button type="button" className="column-sort" onClick={() => onHeaderClick("kickoff")}>Kickoff</button>
                        <span className="sort-indicator">{sortKey === "kickoff" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                      </th>
                      <th scope="col" className="sortable" aria-sort={sortKey === "matchup" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                        <button type="button" className="column-sort" onClick={() => onHeaderClick("matchup")}>Matchup</button>
                        <span className="sort-indicator">{sortKey === "matchup" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                      </th>
                      <th scope="col" className="num sortable" aria-sort={sortKey === "pick" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                        <button type="button" className="column-sort" onClick={() => onHeaderClick("pick")}>Pick</button>
                        <span className="sort-indicator">{sortKey === "pick" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                      </th>
                      <th scope="col" className="num sortable" aria-sort={sortKey === "confidence" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                        <button type="button" className="column-sort" onClick={() => onHeaderClick("confidence")}>Win %</button>
                        <span className="sort-indicator">{sortKey === "confidence" ? (sortDir === "asc" ? "▲" : "▼") : ""}</span>
                      </th>
                      <th scope="col" className="predictions-table__market-head">Market</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map(({ game, prediction, edgeIsRealPick }) => {
                      const hasPrediction = edgeIsRealPick && prediction?.confidence !== null && prediction?.confidence !== undefined;
                      return (
                        <tr
                          key={game.gameId}
                          className="predictions-table__row"
                          tabIndex={0}
                          role="link"
                          aria-label={`View matchup preview: ${game.awayTeam} at ${game.homeTeam}`}
                          onClick={() => goToMatchup(game.gameId)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              goToMatchup(game.gameId);
                            }
                          }}
                        >
                          <td className="predictions-table__time">
                            {game.completed && game.awayPoints !== null && game.homePoints !== null ? (
                              <span className="mono">{game.awayPoints}–{game.homePoints} Final</span>
                            ) : (
                              (() => {
                                const parts = gameTimeParts(game);
                                return (
                                  <span className="predictions-kickoff">
                                    <strong>{parts.date}</strong>
                                    {parts.time ? <small>{parts.time}</small> : null}
                                  </span>
                                );
                              })()
                            )}
                          </td>
                          <td>
                            <div className="predictions-table__matchup">
                              <TeamCell team={game.awayTeam} teamId={game.awayTeamId} rank={topRanked.get(game.awayTeamId) ?? null} />
                              <span className="predictions-table__at">{game.neutralSite ? "vs" : "@"}</span>
                              <TeamCell team={game.homeTeam} teamId={game.homeTeamId} rank={topRanked.get(game.homeTeamId) ?? null} />
                            </div>
                          </td>
                          <td className="num">
                            {access === "locked" ? (
                              <span className="predictions-table__locked">🔒 Locked</span>
                            ) : hasPrediction ? (
                              <span className="predictions-table__pick">
                                {pickText(prediction!.predictedWinner, prediction!.predictedMargin)}
                              </span>
                            ) : (
                              <span className="predictions-table__context">Not enough data</span>
                            )}
                          </td>
                          <td className="num">
                            {access === "locked" ? (
                              <span className="predictions-table__dash">—</span>
                            ) : hasPrediction ? (
                              <span className="mono">{pct(prediction!.confidence)}</span>
                            ) : (
                              <span className="predictions-table__dash">N/A</span>
                            )}
                          </td>
                          <td className="predictions-table__market">
                            <MarketOddsCard market={marketByGameId[game.gameId]} compact />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {power ? <PreseasonPowerTable power={power} /> : null}
      </main>

      <SiteFooter note="Weekly Predictions are model-generated projections, not betting advice. Games without a complete graded model output are labeled Not enough data rather than being shown as substitute predictions." />
    </>
  );
}

function TeamCell({ team, teamId, rank }: { team: string; teamId: number; rank: number | null }) {
  return (
    <span className="predictions-table__team">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={logoUrl(teamId)} alt="" loading="lazy" decoding="async" />
      {rank !== null ? <span className="predictions-table__rank">#{rank}</span> : null}
      {team}
    </span>
  );
}

function PreseasonPowerTable({ power }: { power: PreseasonPower }) {
  const top = power.teams.slice(0, 25);
  return (
    <section className="predictions-power predictions-model" aria-labelledby="predictionModelTitle">
      <div className="predictions-model__header">
        <div className="predictions-model__header-copy">
          <span className="eyebrow">The Model Behind The Picks</span>
          <h2 id="predictionModelTitle">How LEILA Builds a Pick</h2>
          <p className="predictions-model__lede">
            The active early-season engine starts with a frozen preseason estimate, then hands more weight to results
            from this season as each matchup gains evidence. It never uses AP or Coaches Poll votes, SP+, FPI, or betting lines.
          </p>
        </div>
        <span className="predictions-model__version">{power.freezeVersion}</span>
      </div>

      <div className="predictions-model__proof" aria-label="Historical model validation">
        <div className="predictions-model__proof-item">
          <span className="predictions-model__proof-value">{power.backtest.winnerPct.toFixed(1)}%</span>
          <span className="predictions-model__proof-label">Straight-up winners</span>
        </div>
        <div className="predictions-model__proof-item">
          <span className="predictions-model__proof-value">{power.backtest.mae.toFixed(1)}</span>
          <span className="predictions-model__proof-label">Points margin MAE</span>
        </div>
        <div className="predictions-model__proof-item">
          <span className="predictions-model__proof-value">{power.backtest.n.toLocaleString()}</span>
          <span className="predictions-model__proof-label">Walk-forward games</span>
        </div>
      </div>

      <div className="predictions-model__pipeline">
        <article className="predictions-model__stage">
          <span className="predictions-model__stage-number">01 / PRIOR</span>
          <h3>Build preseason power</h3>
          <p>
            Ridge regression combines each program&rsquo;s previous three seasons, three-year recruiting average,
            and whether its primary quarterback returns.
          </p>
        </article>
        <article className="predictions-model__stage">
          <span className="predictions-model__stage-number">02 / LIVE</span>
          <h3>Add this season&rsquo;s evidence</h3>
          <p>
            LEILA measures each team&rsquo;s average scoring margin from games already played. It is intentionally raw
            here because the early schedule graph is still too thin for stable opponent adjustment.
          </p>
        </article>
        <article className="predictions-model__stage">
          <span className="predictions-model__stage-number">03 / MATCHUP</span>
          <h3>Blend + home field</h3>
          <p>
            The prior fades as real games accumulate. The current frozen fit adds 2.7 points for home field and
            adds nothing on a neutral site.
          </p>
        </article>
        <article className="predictions-model__stage">
          <span className="predictions-model__stage-number">04 / CONFIDENCE</span>
          <h3>Calibrate the win chance</h3>
          <p>
            The final predicted margin is mapped to Win % with logistic calibration fitted on historical model
            predictions and actual winners rather than an arbitrary margin-to-probability rule.
          </p>
        </article>
      </div>

      <div className="predictions-model__blend">
        <div className="predictions-model__blend-copy">
          <h3>How preseason information fades out</h3>
          <p>
            The blend uses the team with fewer games played, so a lightly tested team cannot be treated as mature
            just because its opponent has played more often.
          </p>
          <span className="predictions-model__blend-note">
            Navy = preseason prior · Gold = current-season scoring margin
          </span>
        </div>
        <div className="predictions-model__blend-rows" aria-label="Preseason and in-season blend weights">
          {EARLY_BLEND.map((step) => (
            <div className="predictions-model__blend-row" key={step.games}>
              <span className="predictions-model__blend-games">{step.games} GP</span>
              <span className="predictions-model__blend-track" aria-hidden="true">
                <span className="predictions-model__blend-prior" style={{ width: `${step.prior}%` }} />
                <span className="predictions-model__blend-live" style={{ width: `${step.live}%` }} />
              </span>
              <span className="predictions-model__blend-label">{step.prior}/{step.live}</span>
            </div>
          ))}
        </div>
      </div>

      <p className="predictions-model__limits">
        <strong>Why some games say Not enough data:</strong> a graded early-season pick requires a complete preseason
        prior for both teams. That prior needs three seasons of program results plus the recruiting and quarterback
        inputs above, so games involving teams outside that model universe can stay on the slate without receiving a fabricated pick.
      </p>

      <details className="predictions-model__prior">
        <summary>
          <span className="predictions-model__prior-title">
            2026 Preseason Prior
            <small>the starting point, not the final weekly pick</small>
          </span>
          <span className="predictions-model__prior-action">View</span>
        </summary>
        <div className="predictions-model__prior-body">
          <p className="predictions-model__prior-intro">
            These are the frozen preseason power scores that feed step one. They do not update after kickoff;
            the weekly prediction changes because real 2026 results progressively replace this prior in the blend.
          </p>
          <ol className="predictions-power__list">
            {top.map((t) => (
              <li key={t.team}>
                <span className="predictions-power__rank">{t.rank}</span>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={logoUrl(t.teamId ?? 0)} alt="" loading="lazy" decoding="async" />
                <span className="predictions-power__team">{t.team}</span>
                <span className="predictions-power__conf">{t.conf}</span>
                <span className="mono predictions-power__score">{signed(t.powerScore)}</span>
              </li>
            ))}
          </ol>
          <p className="predictions-model__validation">
            Validation shown above is the model&rsquo;s leakage-safe Week 2 walk-forward test: each historical season was
            predicted using coefficients fit only on seasons that came before it. It is not an in-sample fit score.
          </p>
        </div>
      </details>
    </section>
  );
}
