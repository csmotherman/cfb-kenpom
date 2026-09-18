"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import { getMeta, getScheduleSeason } from "@/lib/data";
import { logoUrl, teamCode } from "@/lib/teamCode";
import type { ScheduleGame, ScheduleSeason } from "@/lib/types";

type HistoryGame = ScheduleGame & {
  season: number;
  weekLabel: string;
};

type LoadedSeason = {
  year: number;
  schedule: ScheduleSeason;
};

type TeamOption = {
  id: number;
  name: string;
  slug: string;
  conf: string;
};

type SortMode = "newest" | "oldest" | "closest" | "highest";
type SiteMode = "all" | "campus" | "neutral";

const INITIAL_RESULTS = 60;
const normalize = (value: string) => value.trim().toLocaleLowerCase();

function gameDateMs(game: HistoryGame): number {
  const parsed = game.startDate ? new Date(game.startDate).getTime() : Number.NaN;
  if (!Number.isNaN(parsed)) return parsed;
  return game.season * 10_000_000 + game.week * 10_000;
}

function gameDateLabel(game: HistoryGame): string {
  if (!game.startDate) return "Date unavailable";
  const date = new Date(game.startDate);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function scoreMargin(game: HistoryGame): number {
  if (game.homePoints === null || game.awayPoints === null) return Number.POSITIVE_INFINITY;
  return Math.abs(game.homePoints - game.awayPoints);
}

function totalPoints(game: HistoryGame): number {
  return (game.homePoints ?? 0) + (game.awayPoints ?? 0);
}

function teamInputMatches(input: string, teamName: string, teamSlug: string, exactTeam: TeamOption | undefined, teamId: number): boolean {
  if (!input.trim()) return true;
  if (exactTeam) return exactTeam.id === teamId;
  const needle = normalize(input);
  return normalize(teamName).includes(needle) || normalize(teamSlug).includes(needle);
}

function gameContainsTeamPair(
  game: HistoryGame,
  teamA: string,
  teamB: string,
  exactA: TeamOption | undefined,
  exactB: TeamOption | undefined,
): boolean {
  const hasA = teamA.trim().length > 0;
  const hasB = teamB.trim().length > 0;
  if (!hasA && !hasB) return true;

  const homeA = teamInputMatches(teamA, game.homeTeam, game.homeSlug, exactA, game.homeTeamId);
  const awayA = teamInputMatches(teamA, game.awayTeam, game.awaySlug, exactA, game.awayTeamId);
  if (!hasB) return homeA || awayA;

  const homeB = teamInputMatches(teamB, game.homeTeam, game.homeSlug, exactB, game.homeTeamId);
  const awayB = teamInputMatches(teamB, game.awayTeam, game.awaySlug, exactB, game.awayTeamId);
  if (!hasA) return homeB || awayB;

  return (homeA && awayB) || (awayA && homeB);
}

export default function GameHistoryPage() {
  const [loaded, setLoaded] = useState<LoadedSeason[] | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [year, setYear] = useState("all");
  const [week, setWeek] = useState("all");
  const [teamA, setTeamA] = useState("");
  const [teamB, setTeamB] = useState("");
  const [conference, setConference] = useState("all");
  const [conferenceGamesOnly, setConferenceGamesOnly] = useState(false);
  const [siteMode, setSiteMode] = useState<SiteMode>("all");
  const [sortMode, setSortMode] = useState<SortMode>("newest");
  const [resultLimit, setResultLimit] = useState(INITIAL_RESULTS);

  useEffect(() => {
    let cancelled = false;
    document.title = "Game History | LEILA Ratings";

    (async () => {
      const meta = await getMeta();
      const years = [...(meta.scheduleYears ?? meta.rankingsYears)].sort((a, b) => a - b);
      const schedules = await Promise.all(years.map((season) => getScheduleSeason(season)));
      if (cancelled) return;
      setLoaded(
        years.flatMap((season, index) => {
          const schedule = schedules[index];
          return schedule ? [{ year: season, schedule }] : [];
        }),
      );
    })().catch((error: Error) => {
      if (!cancelled) setLoadError(error);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  const games = useMemo<HistoryGame[]>(() => {
    if (!loaded) return [];
    return loaded.flatMap(({ year: season, schedule }) =>
      schedule.weeks.flatMap((weekNumber) =>
        (schedule.byWeek[String(weekNumber)] ?? [])
          .filter((game) => game.completed && game.homePoints !== null && game.awayPoints !== null)
          .map((game) => ({
            ...game,
            season,
            weekLabel: schedule.weekLabels?.[String(weekNumber)] || `Week ${weekNumber}`,
          })),
      ),
    );
  }, [loaded]);

  const teams = useMemo<TeamOption[]>(() => {
    const byId = new Map<number, TeamOption>();
    for (const game of games) {
      byId.set(game.homeTeamId, {
        id: game.homeTeamId,
        name: game.homeTeam,
        slug: game.homeSlug,
        conf: game.homeConference ?? "Independent",
      });
      byId.set(game.awayTeamId, {
        id: game.awayTeamId,
        name: game.awayTeam,
        slug: game.awaySlug,
        conf: game.awayConference ?? "Independent",
      });
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [games]);

  const teamByExactName = useMemo(() => {
    const map = new Map<string, TeamOption>();
    for (const team of teams) map.set(normalize(team.name), team);
    return map;
  }, [teams]);

  const conferences = useMemo(() => {
    const values = new Set<string>();
    for (const game of games) {
      if (game.homeConference) values.add(game.homeConference);
      if (game.awayConference) values.add(game.awayConference);
    }
    return [...values].sort((a, b) => a.localeCompare(b));
  }, [games]);

  const yearOptions = useMemo(() => (loaded ? loaded.map((item) => item.year).sort((a, b) => b - a) : []), [loaded]);

  const weekOptions = useMemo(() => {
    if (!loaded) return [];
    const selected = year === "all" ? loaded : loaded.filter((item) => item.year === Number(year));
    const values = new Map<number, string>();
    for (const { schedule } of selected) {
      for (const weekNumber of schedule.weeks) {
        if (!values.has(weekNumber)) {
          values.set(weekNumber, schedule.weekLabels?.[String(weekNumber)] || `Week ${weekNumber}`);
        } else if (year === "all") {
          values.set(weekNumber, `Week ${weekNumber}`);
        }
      }
    }
    return [...values.entries()].sort((a, b) => a[0] - b[0]);
  }, [loaded, year]);

  const exactA = teamByExactName.get(normalize(teamA));
  const exactB = teamByExactName.get(normalize(teamB));

  const filtered = useMemo(() => {
    const rows = games.filter((game) => {
      if (year !== "all" && game.season !== Number(year)) return false;
      if (week !== "all" && game.week !== Number(week)) return false;
      if (!gameContainsTeamPair(game, teamA, teamB, exactA, exactB)) return false;
      if (conference !== "all" && game.homeConference !== conference && game.awayConference !== conference) return false;
      if (conferenceGamesOnly && !game.conferenceGame) return false;
      if (siteMode === "neutral" && !game.neutralSite) return false;
      if (siteMode === "campus" && game.neutralSite) return false;
      return true;
    });

    rows.sort((a, b) => {
      if (sortMode === "oldest") return gameDateMs(a) - gameDateMs(b);
      if (sortMode === "closest") return scoreMargin(a) - scoreMargin(b) || gameDateMs(b) - gameDateMs(a);
      if (sortMode === "highest") return totalPoints(b) - totalPoints(a) || gameDateMs(b) - gameDateMs(a);
      return gameDateMs(b) - gameDateMs(a);
    });
    return rows;
  }, [games, year, week, teamA, teamB, exactA, exactB, conference, conferenceGamesOnly, siteMode, sortMode]);

  const series = useMemo(() => {
    if (!exactA || !exactB || exactA.id === exactB.id) return null;
    const meetings = filtered.filter((game) =>
      (game.homeTeamId === exactA.id && game.awayTeamId === exactB.id) ||
      (game.homeTeamId === exactB.id && game.awayTeamId === exactA.id),
    );
    if (!meetings.length) return { meetings: 0, aWins: 0, bWins: 0, ties: 0, last: null as HistoryGame | null };

    let aWins = 0;
    let bWins = 0;
    let ties = 0;
    for (const game of meetings) {
      const aScore = game.homeTeamId === exactA.id ? game.homePoints! : game.awayPoints!;
      const bScore = game.homeTeamId === exactB.id ? game.homePoints! : game.awayPoints!;
      if (aScore > bScore) aWins += 1;
      else if (bScore > aScore) bWins += 1;
      else ties += 1;
    }
    const last = [...meetings].sort((a, b) => gameDateMs(b) - gameDateMs(a))[0] ?? null;
    return { meetings: meetings.length, aWins, bWins, ties, last };
  }, [filtered, exactA, exactB]);

  const visible = filtered.slice(0, resultLimit);
  const dataRange = yearOptions.length ? `${yearOptions[yearOptions.length - 1]}–${yearOptions[0]}` : "";

  function resetResults() {
    setResultLimit(INITIAL_RESULTS);
  }

  function clearFilters() {
    setYear("all");
    setWeek("all");
    setTeamA("");
    setTeamB("");
    setConference("all");
    setConferenceGamesOnly(false);
    setSiteMode("all");
    setSortMode("newest");
    resetResults();
  }

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#historyResults">Skip to game results</a>
      <SiteHeader tagline="College Football Game Archive" />
      <SiteNav />

      <section className="history-toolbar container" aria-labelledby="gameHistoryTitle">
        <div className="history-toolbar__top">
          <div className="history-toolbar__title">
            <h1 id="gameHistoryTitle">Game History</h1>
            <span>{filtered.length.toLocaleString()} games</span>
          </div>
          <div className="history-toolbar__archive">
            <strong>{games.length ? games.length.toLocaleString() : "—"}</strong>
            <span>FBS vs FBS finals{dataRange ? ` · ${dataRange}` : ""}</span>
          </div>
        </div>

        <div className="history-toolbar__controls" aria-label="Game history filters">
          <TeamPicker
            id="historyTeamA"
            label="Team"
            placeholder="Search team"
            value={teamA}
            teams={teams}
            onChange={(value) => {
              setTeamA(value);
              resetResults();
            }}
          />

          <TeamPicker
            id="historyTeamB"
            label="Opponent"
            placeholder="Any opponent"
            value={teamB}
            teams={teams}
            onChange={(value) => {
              setTeamB(value);
              resetResults();
            }}
          />

          <label className="history-compact-field">
            <span>Season</span>
            <select
              value={year}
              onChange={(event) => {
                setYear(event.target.value);
                setWeek("all");
                resetResults();
              }}
            >
              <option value="all">All</option>
              {yearOptions.map((season) => <option value={season} key={season}>{season}</option>)}
            </select>
          </label>

          <label className="history-compact-field">
            <span>Week</span>
            <select
              value={week}
              onChange={(event) => {
                setWeek(event.target.value);
                resetResults();
              }}
            >
              <option value="all">All</option>
              {weekOptions.map(([number, label]) => <option value={number} key={number}>{label}</option>)}
            </select>
          </label>

          <label className="history-compact-field history-compact-field--conference">
            <span>Conference</span>
            <select
              value={conference}
              onChange={(event) => {
                setConference(event.target.value);
                resetResults();
              }}
            >
              <option value="all">All conferences</option>
              {conferences.map((name) => <option value={name} key={name}>{name}</option>)}
            </select>
          </label>

          <label className="history-compact-field">
            <span>Site</span>
            <select
              value={siteMode}
              onChange={(event) => {
                setSiteMode(event.target.value as SiteMode);
                resetResults();
              }}
            >
              <option value="all">All sites</option>
              <option value="campus">Campus</option>
              <option value="neutral">Neutral</option>
            </select>
          </label>

          <label className="history-compact-field history-compact-field--sort">
            <span>Sort</span>
            <select
              value={sortMode}
              onChange={(event) => {
                setSortMode(event.target.value as SortMode);
                resetResults();
              }}
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="closest">Closest</option>
              <option value="highest">Highest scoring</option>
            </select>
          </label>

          <label className="history-toggle">
            <input
              type="checkbox"
              checked={conferenceGamesOnly}
              onChange={(event) => {
                setConferenceGamesOnly(event.target.checked);
                resetResults();
              }}
            />
            <span>Conf. only</span>
          </label>

          <button className="history-clear" type="button" onClick={clearFilters}>Clear</button>
        </div>
      </section>

      <main className="container history-main">
        {series && exactA && exactB ? (
          <section className="history-series" aria-label={`${exactA.name} versus ${exactB.name} series in the selected data`}>
            <div className="history-series__team">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={logoUrl(exactA.id, 96)} alt="" />
              <strong>{exactA.name}</strong>
              <span className="mono">{series.aWins}</span>
            </div>
            <div className="history-series__middle">
              <span className="eyebrow">Selected-data series</span>
              <strong>{series.meetings} {series.meetings === 1 ? "meeting" : "meetings"}</strong>
              {series.ties ? <small>{series.ties} tie{series.ties === 1 ? "" : "s"}</small> : null}
              {series.last ? <small>Last: {series.last.season} · {series.last.weekLabel}</small> : null}
            </div>
            <div className="history-series__team history-series__team--right">
              <span className="mono">{series.bWins}</span>
              <strong>{exactB.name}</strong>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={logoUrl(exactB.id, 96)} alt="" />
            </div>
          </section>
        ) : null}

        <section id="historyResults" className="history-results" aria-live="polite">
          <div className="history-results__heading">
            <div>
              <span className="eyebrow">Results</span>
              <h2>{exactA && exactB ? `${exactA.name} vs ${exactB.name}` : "Games"}</h2>
            </div>
            <span>{visible.length.toLocaleString()} of {filtered.length.toLocaleString()} shown</span>
          </div>

          {!loaded ? (
            <p className="history-empty">Loading the game archive…</p>
          ) : visible.length === 0 ? (
            <div className="history-empty">
              <strong>No games match those filters.</strong>
              <span>Try clearing a team, week, or conference filter.</span>
            </div>
          ) : (
            <div className="history-list">
              {visible.map((game) => <GameRow game={game} key={`${game.season}-${game.gameId}`} />)}
            </div>
          )}

          {visible.length < filtered.length ? (
            <button className="history-show-more" type="button" onClick={() => setResultLimit((limit) => limit + INITIAL_RESULTS)}>
              Show {Math.min(INITIAL_RESULTS, filtered.length - visible.length)} more games
            </button>
          ) : null}
        </section>
      </main>

      <SiteFooter note="Game History contains completed FBS-vs-FBS games for the seasons currently available in LEILA's dataset. Conference labels reflect each team's conference at the time of the game." />
    </>
  );
}

function GameRow({ game }: { game: HistoryGame }) {
  const awayWon = game.awayPoints! > game.homePoints!;
  const homeWon = game.homePoints! > game.awayPoints!;
  return (
    <Link className="history-game" href={`/matchup/${game.season}/${encodeURIComponent(game.gameId)}`}>
      <div className="history-game__meta">
        <strong>{game.season}</strong>
        <span>{game.weekLabel}</span>
        <small>{gameDateLabel(game)}</small>
      </div>

      <div className={`history-game__team${awayWon ? " is-winner" : ""}`}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logoUrl(game.awayTeamId, 64)} alt="" loading="lazy" decoding="async" />
        <span>
          <strong>{game.awayTeam}</strong>
          <small>{game.awayConference ?? "Independent"}</small>
        </span>
        <b className="mono">{game.awayPoints}</b>
      </div>

      <span className="history-game__at">{game.neutralSite ? "VS" : "@"}</span>

      <div className={`history-game__team history-game__team--home${homeWon ? " is-winner" : ""}`}>
        <b className="mono">{game.homePoints}</b>
        <span>
          <strong>{game.homeTeam}</strong>
          <small>{game.homeConference ?? "Independent"}</small>
        </span>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logoUrl(game.homeTeamId, 64)} alt="" loading="lazy" decoding="async" />
      </div>

      <div className="history-game__site">
        <span>{game.neutralSite ? "Neutral" : game.conferenceGame ? "Conference" : "Non-conference"}</span>
        <small>{game.venue ?? "Venue unavailable"}</small>
      </div>

      <span className="history-game__open" aria-hidden="true">→</span>
    </Link>
  );
}
