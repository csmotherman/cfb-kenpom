"use client";

import type { PredictionsInitial } from "@/lib/initialData";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import MarketOddsCard from "@/components/MarketOddsCard";
import PrimeLoadingState from "@/components/PrimeLoadingState";
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
  const [filter, setFilter] = useState<GamesFilter>("all");
  const [search, setSearch] = useState("");
  const [conference, setConference] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("kickoff");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

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
      <SiteHeader tagline="Weekly Predictions" />
      <SiteNav />

      <main id="predictionsContent" className="container predictions-main predictions-main--compact">
        <PredictionsPerformanceSummary initial={initial?.performance} />
        {schedule === undefined ? (
          <>
            {seo?.lede ?? <h1 className="sr-only">College Football Predictions &amp; Matchup Analytics</h1>}
            <PrimeLoadingState variant="predictions" />
          </>
        ) : schedule === null ? (
          <p className="network-loading">Weekly schedule data is publishing with the next ratings refresh.</p>
        ) : (
          <>
            <section className="predictions-toolbar" aria-labelledby="predictionsTitle">
              <div className="predictions-toolbar__primary">
                <div className="predictions-toolbar__title">
                  <h1 id="predictionsTitle">{season ? `${season} College Football Predictions` : "College Football Predictions"}</h1>
                  <span>{sorted.length} games</span>
                </div>

                <label className="predictions-toolbar__field predictions-toolbar__field--week">
                  <span>Week</span>
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

                <div className="predictions-toolbar__search">
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

                <label className="predictions-toolbar__field predictions-toolbar__field--conference">
                  <span className="sr-only">Conference</span>
                  <select
                    value={conference}
                    onChange={(e) => setConference(e.target.value)}
                    aria-label="Filter predictions by conference"
                  >
                    <option value="">All conferences</option>
                    {conferences.map((name) => (
                      <option key={name} value={name}>{name}</option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="predictions-toolbar__secondary">
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
            </section>

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
                          className={`predictions-table__row${game.completed ? " predictions-table__row--final" : ""}`}
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

      </main>

      {seo?.content}

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
