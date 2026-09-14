"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import TeamLink from "@/components/TeamLink";
import { getGameLogSeason } from "@/lib/data";
import type { GameLogEntry, GameLogFields } from "@/lib/types";

export type GameLogColumn = {
  key: string;
  label: string;
  num?: string[];
  den?: string[];
  opponentNum?: string[];
  opponentDen?: string[];
  lowerBetter?: boolean;
};

function sumField(fields: GameLogFields | undefined, keys: string[] | undefined): number {
  if (!fields || !keys) return 0;
  return keys.reduce((acc, k) => acc + (fields[k] ?? 0), 0);
}

function rate(num: number, den: number): number | null {
  return den > 0 ? num / den : null;
}

export default function GameLogModal({
  team,
  teamId,
  slug,
  year,
  column,
  startWeek,
  endWeek,
  weekLabel,
  format,
  onClose,
}: {
  team: string;
  teamId: number;
  slug: string;
  year: string;
  column: GameLogColumn;
  startWeek: number;
  endWeek: number;
  weekLabel: (week: number, long?: boolean) => string;
  format: (value: number | null) => string;
  onClose: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [rows, setRows] = useState<GameLogEntry[] | null>(null);
  const [error, setError] = useState(false);

  // SSR-safe portal mount, matching MatchupPredictionPortal: `document` only
  // exists client-side, so the portal target can't be created during the
  // server render without a hydration mismatch.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => setMounted(true), []);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    let cancelled = false;
    getGameLogSeason(year)
      .then((season) => {
        if (cancelled) return;
        setRows(season?.byTeam[team] ?? []);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => { cancelled = true; };
  }, [year, team]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const games = useMemo(() => {
    if (!rows) return [];
    return rows
      .filter((g) => g.week >= startWeek && g.week <= endWeek)
      .sort((a, b) => a.week - b.week);
  }, [rows, startWeek, endWeek]);

  const totals = useMemo(() => {
    let ownNum = 0;
    let ownDen = 0;
    games.forEach((g) => {
      ownNum += sumField(g.own, column.num);
      ownDen += sumField(g.own, column.den);
    });
    return { ownNum, ownDen, value: rate(ownNum, ownDen) };
  }, [games, column]);

  if (!mounted) return null;

  const hasOpponentContext = !!(column.opponentNum && column.opponentDen);

  return createPortal(
    <div className="game-log-backdrop" role="presentation" onClick={onClose}>
      <div
        className="game-log-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="gameLogTitle"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="game-log-modal__header">
          <div className="game-log-modal__title-stack">
            <span className="game-log-modal__eyebrow">Game log</span>
            <h2 id="gameLogTitle">
              <TeamLink team={team} teamId={teamId} slug={slug} /> &middot; {column.label}
            </h2>
          </div>
          <button type="button" className="game-log-modal__close" aria-label="Close" onClick={onClose}>
            &times;
          </button>
        </div>

        <p className="game-log-modal__note">
          Every game in the selected week range ({weekLabel(startWeek, true)}
          {endWeek !== startWeek ? ` – ${weekLabel(endWeek, true)}` : ""}), with what {team} actually did that game next
          to {hasOpponentContext ? "what that opponent had allowed coming in (season-to-date, before this game)." : "—no opponent baseline is defined for this stat."}
        </p>

        {error ? (
          <p className="game-log-modal__empty">Couldn&apos;t load the game log for {year}.</p>
        ) : rows === null ? (
          <p className="game-log-modal__empty">Loading…</p>
        ) : games.length === 0 ? (
          <p className="game-log-modal__empty">No games in this range yet.</p>
        ) : (
          <div className="game-log-modal__table-wrap">
            <table className="game-log-modal__table">
              <thead>
                <tr>
                  <th>Wk</th>
                  <th>Opponent</th>
                  <th>Result</th>
                  <th>{team} this game</th>
                  <th>{hasOpponentContext ? "Opponent coming in" : "—"}</th>
                </tr>
              </thead>
              <tbody>
                {games.map((g) => {
                  const ownNum = sumField(g.own, column.num);
                  const ownDen = sumField(g.own, column.den);
                  const ownValue = rate(ownNum, ownDen);
                  const oppValue = hasOpponentContext && g.opponentContext
                    ? rate(sumField(g.opponentContext, column.opponentNum), sumField(g.opponentContext, column.opponentDen))
                    : null;
                  const diff = ownValue !== null && oppValue !== null ? ownValue - oppValue : null;
                  const diffGood = diff === null ? null : column.lowerBetter ? diff < 0 : diff > 0;
                  return (
                    <tr key={g.gameId}>
                      <td className="num">{weekLabel(g.week)}</td>
                      <td className="game-log-modal__opponent">
                        {g.opponentTeamId ? (
                          <TeamLink team={g.opponent} teamId={g.opponentTeamId} slug={g.opponentSlug ?? ""} />
                        ) : (
                          <span>{g.opponent}</span>
                        )}
                        <span className="game-log-modal__homeaway">{g.homeAway === "home" ? "vs" : "@"}</span>
                      </td>
                      <td className={`num game-log-modal__result${g.win ? " win" : " loss"}`}>
                        {g.win ? "W" : "L"} {g.pointsFor}-{g.pointsAgainst}
                      </td>
                      <td className="num">{format(ownValue)}</td>
                      <td className="num">
                        {oppValue === null ? (
                          <span className="game-log-modal__dash">
                            {hasOpponentContext ? "no prior games" : "—"}
                          </span>
                        ) : (
                          <>
                            {format(oppValue)}
                            {diff !== null ? (
                              <span className={`game-log-modal__diff${diffGood ? " good" : " bad"}`}>
                                {diff >= 0 ? "+" : ""}
                                {diff.toFixed(diff < 1 && diff > -1 && diff !== 0 ? 3 : 1)}
                              </span>
                            ) : null}
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3}>Total across shown games</td>
                  <td className="num">{format(totals.value)}</td>
                  <td className="num">—</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}
