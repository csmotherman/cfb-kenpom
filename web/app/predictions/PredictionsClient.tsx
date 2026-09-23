"use client";

import type { PredictionsInitial } from "@/lib/initialData";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import MatchupLoading from "@/components/MatchupLoading";
import PredictionsPerformanceSummary from "@/components/PredictionsPerformanceSummary";
import { logoUrl } from "@/lib/teamCode";
import {
  PremiumAccessError,
  getMeta,
  getMarketLinesSeason,
  getPredictionsWeek,
  getRankingsSeason,
  getScheduleSeason,
} from "@/lib/data";
import type {
  MarketLinesSeason,
  PredictionGame,
  RankingsRow,
  RankingsSeason,
  ScheduleGame,
  ScheduleSeason,
} from "@/lib/types";

type GamesFilter = "best" | "top25" | "all";
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
  { key: "best", label: "Featured" },
  { key: "top25", label: "Top 25" },
  { key: "all", label: "All Games" },
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

function pct(n: number | null): string {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

function pickText(winner: string, margin: number): string {
  return `${winner} to win by ${Math.abs(margin).toFixed(1)}`;
}

function number(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatUpdatedAt(value: string | null | undefined): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const day = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "America/New_York",
  });
  const time = date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  });
  return `Updated ${day}, ${time}`;
}

function recordLine(record: string | undefined, conference: string | null | undefined): string {
  if (record && conference) return `${record} (${conference})`;
  return record || conference || "Record unavailable";
}

function marketSummary(market: MarketLinesSeason["games"][string] | undefined): string {
  const quote = market?.primary;
  if (!market || !quote) return "Market unavailable";
  const spread = quote.formattedSpread || (quote.spread === null
    ? "Spread —"
    : quote.spread === 0
      ? "PK"
      : quote.spread < 0
        ? `${market.homeTeam} ${quote.spread.toFixed(1)}`
        : `${market.awayTeam} ${(-quote.spread).toFixed(1)}`);
  return `${spread}${quote.overUnder === null ? "" : `  |  O/U ${number(quote.overUnder)}`}`;
}

function projectedScores(row: Row, market: MarketLinesSeason["games"][string] | undefined): { away: number; home: number } | null {
  const total = market?.primary?.overUnder;
  if (!row.prediction || total === null || total === undefined) return null;
  const homeMargin = row.prediction.predictedWinner === row.game.homeTeam
    ? row.prediction.predictedMargin
    : -row.prediction.predictedMargin;
  return {
    home: Math.max(0, Math.round((total + homeMargin) / 2)),
    away: Math.max(0, Math.round((total - homeMargin) / 2)),
  };
}

function modelEdge(row: Row, market: MarketLinesSeason["games"][string] | undefined): string | null {
  const spread = market?.primary?.spread;
  if (!row.prediction || spread === null || spread === undefined) return null;
  const homeMargin = row.prediction.predictedWinner === row.game.homeTeam
    ? row.prediction.predictedMargin
    : -row.prediction.predictedMargin;
  const homeValue = homeMargin + spread;
  if (Math.abs(homeValue) < 0.5) return "No meaningful model edge";
  const team = homeValue > 0 ? row.game.homeTeam : row.game.awayTeam;
  return `${team} by ${Math.abs(homeValue).toFixed(1)} pts vs market`;
}

export default function PredictionsClient({ seo, initial }: { seo?: { lede: ReactNode; content: ReactNode }; initial?: PredictionsInitial | null }) {
  const router = useRouter();
  const [loadError, setLoadError] = useState<Error | null>(null);
  // With server-provided initial data (lib/initialData.ts) the current week renders in the first HTML; the full season
  // then loads quietly after hydration so other weeks are instant.
  const [season, setSeason] = useState<number | null>(initial?.season ?? null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(initial?.schedule);
  const [rankings, setRankings] = useState<RankingsSeason | null>(initial?.rankings ?? null);
  const [marketLines, setMarketLines] = useState<MarketLinesSeason | null>(initial?.marketLines ?? null);
  const [selectedWeek, setSelectedWeek] = useState<number | null>(initial?.selectedWeek ?? null);
  const [predictionsByWeek, setPredictionsByWeek] = useState<Map<number, PredictionGame[]>>(new Map());
  const [access, setAccess] = useState<Access>("unknown");
  const [filter, setFilter] = useState<GamesFilter>("best");
  const [search, setSearch] = useState("");
  const [conference, setConference] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (initial) {
      return () => { cancelled = true; };
    }
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
    })().catch((error: Error) => { if (!cancelled) setLoadError(error); });
    return () => { cancelled = true; };
  }, [initial]);

  // The server sent only the current week's games and ratings. Browsing to another week loads the full season once
  // (through the shared cache) and swaps it in; it is also started when the week picker gains focus.
  const fullLoad = useRef<Promise<void> | null>(null);
  function ensureFullSeason(): Promise<void> {
    if (!initial) return Promise.resolve();
    if (!fullLoad.current) {
      fullLoad.current = Promise.all([getScheduleSeason(initial.season), getRankingsSeason(initial.season), getMarketLinesSeason(initial.season)])
        .then(([scheduleData, rankingData, marketData]) => {
          if (scheduleData) setSchedule(scheduleData);
          setRankings(rankingData);
          setMarketLines(marketData);
        })
        .catch(() => { fullLoad.current = null; });
    }
    return fullLoad.current;
  }

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
  const updatedLabel = useMemo(() => formatUpdatedAt(marketLines?.generatedAt), [marketLines?.generatedAt]);

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

  const conferences = useMemo(() => {
    const names = new Set<string>();
    for (const row of rows) {
      if (row.game.homeConference) names.add(row.game.homeConference);
      if (row.game.awayConference) names.add(row.game.awayConference);
    }
    return [...names].sort((a, b) => a.localeCompare(b));
  }, [rows]);

  const conferenceRows = useMemo(() => {
    if (!conference) return rows;
    return rows.filter(
      (row) => row.game.homeConference === conference || row.game.awayConference === conference,
    );
  }, [rows, conference]);

  const rowsByFilter = useMemo(() => ({
    all: conferenceRows,
    top25: conferenceRows.filter((r) => topRanked.has(r.game.homeTeamId) || topRanked.has(r.game.awayTeamId)),
    best: conferenceRows.filter((r) => topRanked.has(r.game.homeTeamId) && topRanked.has(r.game.awayTeamId)),
  }), [conferenceRows, topRanked]);

  const searched = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const base = rowsByFilter[filter];
    if (!needle) return base;
    return base.filter((r) => [r.game.homeTeam, r.game.awayTeam, r.game.homeConference, r.game.awayConference].some((value) => value?.toLowerCase().includes(needle)));
  }, [rowsByFilter, filter, search]);

  const sorted = useMemo(() => [...searched].sort((a, b) => kickoffMs(a.game) - kickoffMs(b.game)), [searched]);

  const featuredPicks = useMemo(() => {
    const predicted = rows.filter((row) => row.prediction?.confidence !== null && row.prediction?.confidence !== undefined);
    const upsets = predicted
      .filter((row) => {
        const spread = marketByGameId[row.game.gameId]?.primary?.spread;
        if (spread === null || spread === undefined || spread === 0) return false;
        const marketFavorite = spread < 0 ? row.game.homeTeam : row.game.awayTeam;
        return row.prediction?.predictedWinner !== marketFavorite;
      })
      .sort((a, b) => (b.prediction?.confidence ?? 0) - (a.prediction?.confidence ?? 0));
    const gameOfWeek = [...predicted].sort((a, b) => {
      const aRank = (topRanked.get(a.game.homeTeamId) ?? 40) + (topRanked.get(a.game.awayTeamId) ?? 40);
      const bRank = (topRanked.get(b.game.homeTeamId) ?? 40) + (topRanked.get(b.game.awayTeamId) ?? 40);
      return aRank - bRank || Math.abs(a.prediction!.predictedMargin) - Math.abs(b.prediction!.predictedMargin);
    })[0];
    const upset = upsets.find((row) => row.game.gameId !== gameOfWeek?.game.gameId);
    return { upset, gameOfWeek };
  }, [rows, marketByGameId, topRanked]);

  const groupedRows = useMemo(() => {
    const groups = new Map<string, Row[]>();
    for (const row of sorted) {
      const key = gameTimeParts(row.game).date;
      groups.set(key, [...(groups.get(key) ?? []), row]);
    }
    return [...groups.entries()];
  }, [sorted]);

  function goToMatchup(gameId: string) {
    if (season === null) return;
    router.push(`/matchup/${season}/${encodeURIComponent(gameId)}`);
  }

  if (loadError) throw loadError;

  const predictionsReady =
    schedule === null ||
    (
      schedule !== undefined &&
      selectedWeek !== null &&
      (access === "locked" || predictionsByWeek.has(selectedWeek))
    );

  if (!predictionsReady) {
    return (
      <>
        <a className="skip-link" href="#predictionsContent">Skip to predictions</a>
        <SiteHeader tagline="Weekly Predictions" />
        <SiteNav />
        <MatchupLoading detail="Loading weekly predictions" />
      </>
    );
  }

  return (
    <>
      <a className="skip-link" href="#predictionsContent">Skip to predictions</a>
      <SiteHeader tagline="Weekly Predictions" />
      <SiteNav />

      <main id="predictionsContent" className="container predictions-main predictions-main--compact">
        {schedule === undefined ? (
          <>
            {seo?.lede ?? <h1 className="sr-only">College Football Predictions &amp; Matchup Analytics</h1>}
            <MatchupLoading detail="Loading weekly predictions" />
          </>
        ) : schedule === null ? (
          <p className="network-loading">Weekly schedule data is publishing with the next ratings refresh.</p>
        ) : (
          <>
            <section className="predictions-showcase__intro" aria-labelledby="predictionsTitle">
              <div>
                <span className="eyebrow">Week {selectedWeek} · {season}</span>
                <h1 id="predictionsTitle">Weekly Predictions</h1>
                <p>{rows.length} games · {updatedLabel ?? "Pregame model projections"}</p>
              </div>
              <label className="predictions-showcase__week">
                  <span className="sr-only">Week</span>
                  <select
                    value={selectedWeek ?? ""}
                    onFocus={() => void ensureFullSeason()}
                    onPointerDown={() => void ensureFullSeason()}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      void ensureFullSeason().then(() => setSelectedWeek(next));
                    }}
                    aria-label="Prediction week"
                  >
                    {schedule.weeks.map((week) => (
                      <option key={week} value={week}>
                        {schedule.weekLabels?.[String(week)] || `Wk ${week}`}
                      </option>
                    ))}
                  </select>
              </label>
            </section>

            {featuredPicks.gameOfWeek || featuredPicks.upset ? (
              <section className="prediction-highlights" aria-label="Featured predictions">
                {featuredPicks.gameOfWeek ? (
                  <FeaturedGameCard
                    label="Game of the Week"
                    row={featuredPicks.gameOfWeek}
                    market={marketByGameId[featuredPicks.gameOfWeek.game.gameId]}
                    awayRank={topRanked.get(featuredPicks.gameOfWeek.game.awayTeamId) ?? null}
                    homeRank={topRanked.get(featuredPicks.gameOfWeek.game.homeTeamId) ?? null}
                    onOpen={() => goToMatchup(featuredPicks.gameOfWeek!.game.gameId)}
                  />
                ) : null}
                {featuredPicks.upset ? (
                  <UpsetWatchCard
                    row={featuredPicks.upset}
                    market={marketByGameId[featuredPicks.upset.game.gameId]}
                    onOpen={() => goToMatchup(featuredPicks.upset!.game.gameId)}
                  />
                ) : null}
              </section>
            ) : null}

            <PredictionsPerformanceSummary initial={initial?.performance} />

            <section className="predictions-showcase__controls" aria-label="Prediction filters">
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
                    </button>
                  ))}
                </div>
                <div className="predictions-showcase__find">
                  <label>
                    <span className="sr-only">Search teams</span>
                    <input
                      id="predictionsSearch"
                      type="search"
                      placeholder="Search teams, conferences…"
                      autoComplete="off"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </label>
                  <details className="predictions-showcase__filter-menu">
                    <summary aria-label="Filters"><span className="sr-only">Filters</span></summary>
                    <label>
                      <span>Conference</span>
                      <select value={conference} onChange={(e) => setConference(e.target.value)} aria-label="Filter predictions by conference">
                        <option value="">All conferences</option>
                        {conferences.map((name) => <option key={name} value={name}>{name}</option>)}
                      </select>
                    </label>
                  </details>
                </div>
                {access === "locked" ? (
                  <Link className="utility-link predictions-unlock-link" href="/upgrade?feature=predictions">
                    Unlock picks &amp; win % →
                  </Link>
                ) : null}
            </section>

            {sorted.length === 0 ? (
              <p className="network-loading">
                {search.trim() ? `No games match "${search}".` : "No games involving an FBS team are listed for this week."}
              </p>
            ) : (
              <div className="predictions-showcase__slate">
                {groupedRows.map(([date, dateRows]) => (
                  <section className="prediction-date" key={date} aria-labelledby={`date-${date.replace(/\W/g, "")}`}>
                    <header>
                      <h2 id={`date-${date.replace(/\W/g, "")}`}>{date}</h2>
                      <span>{dateRows.length} game{dateRows.length === 1 ? "" : "s"}</span>
                    </header>
                    <div className="prediction-date__games">
                      {dateRows.map((row) => (
                        <PredictionCard
                          key={row.game.gameId}
                          row={row}
                          market={marketByGameId[row.game.gameId]}
                          access={access}
                          homeRank={topRanked.get(row.game.homeTeamId) ?? null}
                          awayRank={topRanked.get(row.game.awayTeamId) ?? null}
                          onOpen={() => goToMatchup(row.game.gameId)}
                        />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </>
        )}

      </main>

      {seo?.content}

      <SiteFooter note="Weekly Predictions are model-generated projections, not betting advice. Games without a complete graded model output are labeled Not enough data rather than being shown as substitute predictions." />
    </>
  );
}

function PredictionCard({ row, market, access, homeRank, awayRank, onOpen }: {
  row: Row;
  market: MarketLinesSeason["games"][string] | undefined;
  access: Access;
  homeRank: number | null;
  awayRank: number | null;
  onOpen: () => void;
}) {
  const { game, prediction, awayRating, homeRating } = row;
  const scores = projectedScores(row, market);
  const confidence = prediction?.confidence ?? null;
  const winnerIsHome = prediction?.predictedWinner === game.homeTeam;
  const homeProbability = confidence === null ? null : winnerIsHome ? confidence : 1 - confidence;
  const awayProbability = homeProbability === null ? null : 1 - homeProbability;
  const edge = modelEdge(row, market);
  const time = gameTimeParts(game);

  return (
    <article className={`prediction-card${game.completed ? " prediction-card--final" : ""}`}>
      <button className="prediction-card__body" type="button" onClick={onOpen} aria-label={`View matchup: ${game.awayTeam} at ${game.homeTeam}`}>
        <span className="prediction-card__meta">
          <strong>{game.completed ? "Final" : time.time || "Time TBA"}</strong>
          <span>{marketSummary(market)}</span>
        </span>
        <span className="prediction-card__matchup">
          <PredictionTeam team={game.awayTeam} teamId={game.awayTeamId} rank={awayRank} record={awayRating?.record} conference={game.awayConference} />
          <span className="prediction-card__score">
            <small>{game.completed ? "Final" : "Projected"}</small>
            <strong>{game.completed ? game.awayPoints ?? "—" : scores?.away ?? "—"}<i>–</i>{game.completed ? game.homePoints ?? "—" : scores?.home ?? "—"}</strong>
          </span>
          <PredictionTeam team={game.homeTeam} teamId={game.homeTeamId} rank={homeRank} record={homeRating?.record} conference={game.homeConference} align="right" />
        </span>
        {homeProbability !== null ? (
          <span className="prediction-card__probability-group">
          <span className="prediction-card__probability-labels">
            <span>{game.awayTeam} <strong>{pct(awayProbability)}</strong></span>
            <span>{game.homeTeam} <strong>{pct(homeProbability)}</strong></span>
          </span>
          <span className="prediction-card__probability" aria-hidden="true">
            <i style={{ width: `${Math.round(awayProbability! * 100)}%` }} />
          </span>
          </span>
        ) : null}
      </button>
      <footer>
        <span>
          <strong>PRIME {edge ? "edge" : "pick"}:</strong>{" "}
          {access === "locked" ? "Locked" : edge || (prediction ? pickText(prediction.predictedWinner, prediction.predictedMargin) : "Not enough data")}
        </span>
        <button type="button" onClick={onOpen}>View matchup <span aria-hidden="true">→</span></button>
      </footer>
    </article>
  );
}

function FeaturedGameCard({ label, row, market, awayRank, homeRank, onOpen }: {
  label: string;
  row: Row;
  market: MarketLinesSeason["games"][string] | undefined;
  awayRank: number | null;
  homeRank: number | null;
  onOpen: () => void;
}) {
  const { game, prediction, awayRating, homeRating } = row;
  const scores = projectedScores(row, market);
  const homeProbability = prediction?.confidence === null || prediction?.confidence === undefined
    ? null
    : prediction.predictedWinner === game.homeTeam ? prediction.confidence : 1 - prediction.confidence;
  const awayProbability = homeProbability === null ? null : 1 - homeProbability;
  const winner = prediction?.predictedWinner;
  const winnerProbability = prediction?.confidence ?? null;
  const time = gameTimeParts(game);

  return (
    <article className="featured-game">
      <header>
        <h2>{label}</h2>
        <span>{time.date} · {time.time || "Time TBA"}</span>
      </header>
      <button type="button" className="featured-game__body" onClick={onOpen}>
        <PredictionTeam team={game.awayTeam} teamId={game.awayTeamId} rank={awayRank} record={awayRating?.record} conference={game.awayConference} featured />
        <span className="featured-game__score">
          <small>Projected</small>
          <strong>{scores?.away ?? "—"}<i>–</i>{scores?.home ?? "—"}</strong>
        </span>
        <PredictionTeam team={game.homeTeam} teamId={game.homeTeamId} rank={homeRank} record={homeRating?.record} conference={game.homeConference} align="right" featured />
      </button>
      {homeProbability !== null ? (
        <div className="featured-game__probability">
          <span><strong>{pct(awayProbability)}</strong>{game.awayTeam}</span>
          <i aria-hidden="true"><b style={{ width: `${Math.round(awayProbability! * 100)}%` }} /></i>
          <span><strong>{pct(homeProbability)}</strong>{game.homeTeam}</span>
        </div>
      ) : null}
      {winnerProbability !== null ? (
        <div className="featured-game__pickline">
          <span>{pct(winnerProbability)} {winner}</span>
        </div>
      ) : null}
      <footer>
        <p>Top matchup by pregame ranking and projected competitiveness.</p>
        <button type="button" onClick={onOpen}>Full preview <span aria-hidden="true">→</span></button>
      </footer>
    </article>
  );
}

function UpsetWatchCard({ row, market, onOpen }: {
  row: Row;
  market: MarketLinesSeason["games"][string] | undefined;
  onOpen: () => void;
}) {
  const { game, prediction, awayRating, homeRating } = row;
  const scores = projectedScores(row, market);
  const time = gameTimeParts(game);
  const winner = prediction?.predictedWinner ?? "Model pick";
  const winnerIsAway = winner === game.awayTeam;
  return (
    <article className="upset-watch">
      <header>
        <h2>Upset Watch</h2>
        <span>{time.date} · {time.time || "Time TBA"}</span>
      </header>
      <button type="button" onClick={onOpen} className="upset-watch__body">
        <span className="upset-watch__team">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoUrl(game.awayTeamId)} alt="" />
          <span>
            <strong>{game.awayTeam}</strong>
            <small>{recordLine(awayRating?.record, game.awayConference)}</small>
          </span>
        </span>
        <span className="upset-watch__score">
          <small>Projected</small>
          <strong>{scores?.away ?? "—"}<i>–</i>{scores?.home ?? "—"}</strong>
        </span>
        <span className="upset-watch__team upset-watch__team--right">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoUrl(game.homeTeamId)} alt="" />
          <span>
            <strong>{game.homeTeam}</strong>
            <small>{recordLine(homeRating?.record, game.homeConference)}</small>
          </span>
        </span>
      </button>
      <footer>
        <p>{winner} is projected to beat the market favorite{winnerIsAway ? " on the road" : ""}.</p>
        <span className="upset-watch__confidence">{pct(prediction?.confidence ?? null)} confidence</span>
        <button type="button" onClick={onOpen} aria-label="View upset matchup">→</button>
      </footer>
    </article>
  );
}

function PredictionTeam({ team, teamId, rank, record, conference, align = "left", featured = false }: {
  team: string;
  teamId: number;
  rank: number | null;
  record?: string;
  conference?: string | null;
  align?: "left" | "right";
  featured?: boolean;
}) {
  return (
    <span className={`prediction-card__team prediction-card__team--${align}${featured ? " prediction-card__team--featured" : ""}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={logoUrl(teamId)} alt="" loading="lazy" decoding="async" />
      <span className="prediction-card__team-name">
        <strong>{rank !== null ? <small>#{rank}</small> : null}{team}</strong>
        <small>{recordLine(record, conference)}</small>
      </span>
    </span>
  );
}
