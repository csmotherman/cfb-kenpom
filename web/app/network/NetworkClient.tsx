"use client";

import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import TeamLink from "@/components/TeamLink";
import { getMeta, getScheduleSeason, useRankingsSeason } from "@/lib/data";
import type { RankingsRow, ScheduleSeason } from "@/lib/types";

type TeamNetwork = {
  id: string;
  teams: string[];
  games: number;
};

function na(v: unknown): v is null | undefined {
  return v === null || v === undefined || (typeof v === "number" && Number.isNaN(v));
}

// Union-find over every FBS team, wired up by completed FBS-vs-FBS games
// through the selected week -- the exact same graph ASM's least-squares fit
// (fit_srs in iterative_ratings.py) solves over. Two teams are in the same
// network the moment any chain of played games connects them, even if
// neither played the other directly.
function buildNetworks(fbsTeams: string[], schedule: ScheduleSeason, throughWeek: number) {
  const parent = new Map<string, string>();
  fbsTeams.forEach((t) => parent.set(t, t));

  function find(x: string): string {
    let root = x;
    while (parent.get(root) !== root) root = parent.get(root)!;
    let cur = x;
    while (parent.get(cur) !== root) {
      const next = parent.get(cur)!;
      parent.set(cur, root);
      cur = next;
    }
    return root;
  }
  function union(a: string, b: string) {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent.set(ra, rb);
  }

  const teamSet = new Set(fbsTeams);
  const gamesPlayedByTeam = new Map<string, number>();

  for (const week of schedule.weeks) {
    if (week > throughWeek) continue;
    for (const g of schedule.byWeek[String(week)] || []) {
      if (!g.completed) continue;
      if (!teamSet.has(g.homeTeam) || !teamSet.has(g.awayTeam)) continue;
      union(g.homeTeam, g.awayTeam);
      gamesPlayedByTeam.set(g.homeTeam, (gamesPlayedByTeam.get(g.homeTeam) || 0) + 1);
      gamesPlayedByTeam.set(g.awayTeam, (gamesPlayedByTeam.get(g.awayTeam) || 0) + 1);
    }
  }

  const gamesByRoot = new Map<string, number>();
  for (const week of schedule.weeks) {
    if (week > throughWeek) continue;
    for (const g of schedule.byWeek[String(week)] || []) {
      if (!g.completed) continue;
      if (!teamSet.has(g.homeTeam) || !teamSet.has(g.awayTeam)) continue;
      const root = find(g.homeTeam);
      gamesByRoot.set(root, (gamesByRoot.get(root) || 0) + 1);
    }
  }

  const groups = new Map<string, string[]>();
  fbsTeams.forEach((t) => {
    const root = find(t);
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root)!.push(t);
  });

  const networks: TeamNetwork[] = Array.from(groups.entries()).map(([root, teams]) => ({
    id: root,
    teams: teams.sort(),
    games: gamesByRoot.get(root) || 0,
  }));
  networks.sort((a, b) => b.teams.length - a.teams.length);

  return { networks, gamesPlayedByTeam };
}

function bubbleDiameter(teamCount: number): number {
  return Math.round(Math.min(360, 64 + Math.sqrt(teamCount) * 40));
}

export default function NetworkClient() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState("");
  const [week, setWeek] = useState<number | null>(null);
  const [schedule, setSchedule] = useState<ScheduleSeason | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    getMeta().then((meta) => {
      setYears(meta.rankingsYears);
      setYear(String(meta.rankingsYears[meta.rankingsYears.length - 1]));
    }).catch(setLoadError);
  }, []);

  useEffect(() => {
    if (!year) return;
    let cancelled = false;
    getScheduleSeason(year).then((s) => { if (!cancelled) setSchedule(s); }).catch(() => {});
    return () => { cancelled = true; };
  }, [year]);

  const season = useRankingsSeason(year || null);
  const weeks = schedule?.weeks ?? season?.weeks ?? [];

  function weekLabel(w: number, long = false): string {
    const label = (schedule?.weekLabels ?? season?.weekLabels)?.[String(w)];
    if (label) return label;
    return long ? `Week ${w}` : `Wk ${w}`;
  }

  // Same render-phase reset used on the Ratings page: the moment `year`
  // changes and this season's weeks are available, jump to its most recent
  // completed week. Guarded so it only fires once per year change, and
  // self-corrects on a later render if weeks/schedule aren't loaded yet.
  const [weekYear, setWeekYear] = useState(year);
  if (year !== weekYear && weeks.length > 0) {
    setWeekYear(year);
    setWeek(schedule?.currentWeek ?? weeks[weeks.length - 1]);
    setSelectedId(null);
  }

  // The full FBS roster for this season -- unioned across every published
  // week rather than just the selected one, since an early week's rankings
  // snapshot can be missing teams that haven't been rated yet (see week 0).
  const fbsTeams = useMemo(() => {
    if (!season) return [];
    const set = new Set<string>();
    season.weeks.forEach((w) => (season.byWeek[String(w)] || []).forEach((r) => set.add(r.team)));
    return Array.from(set);
  }, [season]);

  // Latest-known row per team at or before the selected week, so a team
  // missing from an intermediate snapshot still shows its most recent stats.
  const rowMap = useMemo(() => {
    const map = new Map<string, RankingsRow>();
    if (!season || week === null) return map;
    for (const w of season.weeks) {
      if (w > week) break;
      (season.byWeek[String(w)] || []).forEach((r) => map.set(r.team, r));
    }
    return map;
  }, [season, week]);

  const { networks, gamesPlayedByTeam } = useMemo(() => {
    if (!schedule || week === null || fbsTeams.length === 0) {
      return { networks: [] as TeamNetwork[], gamesPlayedByTeam: new Map<string, number>() };
    }
    return buildNetworks(fbsTeams, schedule, week);
  }, [schedule, week, fbsTeams]);

  const networkStats = useMemo(() => {
    return networks.map((net) => {
      const emValues = net.teams.map((t) => rowMap.get(t)?.adjEM).filter((v): v is number => !na(v));
      const avgEm = emValues.length ? emValues.reduce((a, b) => a + b, 0) / emValues.length : null;
      const degrees = net.teams.map((t) => gamesPlayedByTeam.get(t) || 0);
      const bestTeam = net.teams
        .map((t) => ({ team: t, row: rowMap.get(t) }))
        .filter((x): x is { team: string; row: RankingsRow } => !!x.row && !na(x.row.rank))
        .sort((a, b) => (a.row.rank as number) - (b.row.rank as number))[0];
      return {
        ...net,
        avgEm,
        minGames: degrees.length ? Math.min(...degrees) : 0,
        maxGames: degrees.length ? Math.max(...degrees) : 0,
        bestTeam,
      };
    });
  }, [networks, rowMap, gamesPlayedByTeam]);

  const selected = networkStats.find((n) => n.id === selectedId) ?? null;
  const totalTeams = fbsTeams.length;
  const largest = networkStats[0];
  const fullyConnected = networkStats.length === 1;
  const loading = !season || !schedule || week === null;

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#mainContent">Skip to network</a>
      <SiteHeader tagline="Schedule Network" />
      <SiteNav />

      <section className="ratings-hero container" aria-labelledby="networkTitle">
        <div className="ratings-hero__copy">
          <span className="eyebrow">PRIME Football</span>
          <h1 id="networkTitle">Schedule Network</h1>
          <p className="ratings-hero__description">
            Every opponent-adjusted rating (ASM in particular) only compares teams that are tied together by a chain of
            played games. Early in a season the country splits into several disconnected pockets -- teams in different
            pockets aren&apos;t comparable yet, no matter what the numbers say. This page shows those pockets as bubbles,
            one per network, for any week of any season.
          </p>
        </div>
        <div className="ratings-hero__meta">
          <span className="ratings-status">
            {loading
              ? "Loading season…"
              : `${year} • through ${weekLabel(week as number, true)} • ${networkStats.length} network${networkStats.length === 1 ? "" : "s"} • largest ${largest?.teams.length ?? 0}/${totalTeams}${fullyConnected ? " • fully connected" : ""}`}
          </span>
        </div>
      </section>

      <div className="control-bar">
        <div className="control-bar__inner">
          <span className="control-label">Season</span>
          <nav className="year-nav" aria-label="Season">
            {[...years].reverse().map((y) => (
              <button
                key={y}
                type="button"
                className={String(y) === year ? "active" : undefined}
                aria-label={`${y} season`}
                aria-pressed={String(y) === year}
                onClick={() => setYear(String(y))}
              >
                {y}
              </button>
            ))}
          </nav>
        </div>

        <div className="control-bar__inner control-bar__inner--secondary">
          <span className="control-label">Through week</span>
          <nav className="week-nav" aria-label="Week">
            {weeks.map((w) => (
              <button
                key={w}
                type="button"
                className={w === week ? "active" : undefined}
                aria-label={weekLabel(w)}
                aria-pressed={w === week}
                onClick={() => {
                  setWeek(w);
                  setSelectedId(null);
                }}
              >
                {weekLabel(w)}
              </button>
            ))}
          </nav>
          <p className="control-help">
            Cumulative through the selected week. Each bubble is one connected network of teams -- click one to see its
            full roster.
          </p>
        </div>
      </div>

      <main id="mainContent" className="container network-page">
        {loading ? (
          <p className="network-loading">Loading network…</p>
        ) : (
          <>
            <div className="network-cloud">
              {networkStats.map((net) => {
                const size = bubbleDiameter(net.teams.length);
                const isBiggest = net === largest;
                return (
                  <button
                    key={net.id}
                    type="button"
                    className={`network-bubble${selectedId === net.id ? " network-bubble--active" : ""}${isBiggest ? " network-bubble--biggest" : ""}`}
                    style={{ width: size, height: size }}
                    onClick={() => setSelectedId(selectedId === net.id ? null : net.id)}
                    aria-pressed={selectedId === net.id}
                  >
                    <span className="network-bubble__count">{net.teams.length}</span>
                    <span className="network-bubble__label">{net.teams.length === 1 ? "team" : "teams"}</span>
                    {net.avgEm !== null ? (
                      <span className="network-bubble__stat">
                        {net.avgEm >= 0 ? "+" : ""}
                        {net.avgEm.toFixed(1)} avg
                      </span>
                    ) : null}
                    <span className="network-bubble__stat">{net.games} game{net.games === 1 ? "" : "s"}</span>
                  </button>
                );
              })}
            </div>

            {selected ? (
              <div className="network-detail">
                <div className="network-detail__header">
                  <h2>
                    Network of {selected.teams.length} team{selected.teams.length === 1 ? "" : "s"}
                  </h2>
                  <p>
                    {selected.games} game{selected.games === 1 ? "" : "s"} played within this network through{" "}
                    {weekLabel(week as number, true)}.{" "}
                    {selected.minGames === selected.maxGames
                      ? `Every team has played ${selected.minGames} game${selected.minGames === 1 ? "" : "s"}.`
                      : `Games played per team ranges from ${selected.minGames} to ${selected.maxGames} -- a wide range means part of this network is still thinly connected.`}
                    {selected.avgEm !== null ? ` Average Net APR: ${selected.avgEm >= 0 ? "+" : ""}${selected.avgEm.toFixed(1)}.` : ""}
                  </p>
                </div>
                <div className="network-detail__table-wrap">
                  <table className="network-detail__table">
                    <thead>
                      <tr>
                        <th>Rk</th>
                        <th>Team</th>
                        <th>Record</th>
                        <th>Net APR</th>
                        <th>Games</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.teams
                        .map((t) => rowMap.get(t))
                        .filter((r): r is RankingsRow => !!r)
                        .sort((a, b) => (a.rank ?? 9999) - (b.rank ?? 9999))
                        .map((row) => (
                          <tr key={row.team}>
                            <td>{row.rank ?? "—"}</td>
                            <td>
                              <TeamLink team={row.team} teamId={row.teamId} slug={row.slug} />
                            </td>
                            <td>{row.record}</td>
                            <td>{na(row.adjEM) ? "—" : `${row.adjEM! >= 0 ? "+" : ""}${row.adjEM!.toFixed(1)}`}</td>
                            <td>{gamesPlayedByTeam.get(row.team) ?? 0}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <p className="network-hint">Click a bubble above to see which teams are in it.</p>
            )}
          </>
        )}
      </main>

      <SiteFooter note="Networks are built from completed FBS-vs-FBS games only, the same graph ASM's opponent-adjusted least-squares fit solves over. Two teams are only comparable once a chain of played games connects them -- being in different networks doesn't mean one team is better, it means there isn't enough information yet to say." />
    </>
  );
}
