"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { logoUrl } from "@/lib/teamCode";
import {
  PremiumAccessError,
  getMeta,
  getPredictionsWeek,
  getPreseasonPower,
  getRankingsSeason,
  getScheduleSeason,
} from "@/lib/data";
import type {
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

// The early-season model only scores games until a team's own schedule is
// long enough for Adj. Net to take over (see the copy below) -- a null
// result for an unlocked week means "not published for this week," not an
// error, and the table falls back to a plain Adj. Net comparison instead of
// going blank, so this page stays useful as the season's single "this
// week's games" destination all year, not just weeks 1-5.
type Row = {
  game: ScheduleGame;
  homeRating: RankingsRow | undefined;
  awayRating: RankingsRow | undefined;
  prediction: PredictionGame | undefined;
  // Signed to the home team (positive = home favored) so every row sorts on
  // the same axis regardless of who the model likes -- real predicted margin
  // when published, else the raw Adj. Net differential as context only.
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

function gameTimeLabel(game: ScheduleGame): string {
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

export default function PredictionsPage() {
  const router = useRouter();
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [season, setSeason] = useState<number | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null | undefined>(undefined);
  const [rankings, setRankings] = useState<RankingsSeason | null>(null);
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
      const [scheduleData, rankingData] = await Promise.all([
        getScheduleSeason(latestSeason),
        getRankingsSeason(latestSeason),
      ]);
      if (cancelled) return;
      setSeason(latestSeason);
      setSchedule(scheduleData);
      setRankings(rankingData);
      setSelectedWeek(scheduleData?.currentWeek ?? null);
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
        // Non-access errors (network blip, 500) just leave this week showing
        // the Adj. Net fallback rather than taking down the whole page.
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
          if (a.edgeValue === null) return b.edgeValue === null ? 0 : 1;
          if (b.edgeValue === null) return -1;
          return (Math.abs(a.edgeValue) - Math.abs(b.edgeValue)) * dir;
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
            Every FBS-vs-FBS game, sortable and searchable. Weeks 1-5ish blend a preseason power rating with real
            results as they come in; once a team&rsquo;s schedule is long enough for LEILA&rsquo;s own Adj. Net to
            take over, the Pick column falls back to an Adj. Net comparison instead of a graded pick.
          </p>
        </div>
      </section>

      <main id="predictionsContent" className="container predictions-main">
        {schedule === undefined ? (
          <p className="network-loading">Loading this week&rsquo;s slate…</p>
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
                {search.trim() ? `No games match "${search}".` : "No FBS-vs-FBS games are listed for this week."}
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
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map(({ game, prediction, edgeValue, edgeIsRealPick }) => (
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
                            gameTimeLabel(game)
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
                          ) : edgeValue === null ? (
                            <span className="predictions-table__dash">—</span>
                          ) : edgeIsRealPick ? (
                            <span className="predictions-table__pick">
                              {prediction!.predictedWinner} <span className="mono">{signed(prediction!.predictedMargin)}</span>
                            </span>
                          ) : (
                            <span className="predictions-table__context" title="No graded pick this week -- Adj. Net comparison shown for context only.">
                              Adj. Net <span className="mono">{signed(edgeValue)}</span> {edgeValue >= 0 ? game.homeTeam : game.awayTeam}
                            </span>
                          )}
                        </td>
                        <td className="num">
                          {access === "locked" ? (
                            <span className="predictions-table__dash">—</span>
                          ) : (
                            <span className="mono">{pct(prediction?.confidence ?? null)}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {power ? <PreseasonPowerTable power={power} /> : null}
      </main>

      <SiteFooter note="Weekly Predictions are model-generated projections, not betting advice. Once the early-season model retires for a game, the Pick column shows a plain Adj. Net comparison instead of a graded pick -- that context is not itself a validated prediction." />
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
            <span className="mono predictions-power__score">{signed(t.powerScore)}</span>
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
