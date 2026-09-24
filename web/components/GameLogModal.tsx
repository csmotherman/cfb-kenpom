"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import TeamLink from "@/components/TeamLink";
import { getGameLogSeason } from "@/lib/data";
import { logoUrl } from "@/lib/teamCode";
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
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
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

  const rangeText = endWeek !== startWeek
    ? `${weekLabel(startWeek, true)} – ${weekLabel(endWeek, true)}`
    : weekLabel(startWeek, true);

  return createPortal(
    <div className="game-log-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        className="game-log-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="gameLogTitle"
      >
        <header className="game-log-modal__header">
          <div className="game-log-modal__identity">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img className="game-log-modal__team-logo" src={logoUrl(teamId, 128)} alt="" />
            <div className="game-log-modal__title-stack">
              <span className="game-log-modal__eyebrow">Game-by-game breakdown</span>
              <h2 id="gameLogTitle">{team}</h2>
              <p>{column.label} · {rangeText}</p>
            </div>
          </div>
          <button type="button" className="game-log-modal__close" aria-label="Close game breakdown" onClick={onClose}>
            &times;
          </button>
        </header>

        <div className="game-log-modal__summary">
          <div>
            <span>Games shown</span>
            <strong>{games.length || "—"}</strong>
          </div>
          <div>
            <span>Sample value</span>
            <strong>{games.length ? format(totals.value) : "—"}</strong>
          </div>
          <div className="game-log-modal__summary-context">
            <span>Opponent comparison</span>
            <strong>{hasOpponentContext ? "Entering game" : "Not available"}</strong>
          </div>
        </div>

        <p className="game-log-modal__note">
          <strong>How to read this:</strong> “This game” is {team}&apos;s actual performance.
          {hasOpponentContext
            ? " “Opponent entering” shows what that opponent had allowed before the game; the small +/- is the difference."
            : " This metric does not have an opponent baseline."}
        </p>

        {error ? (
          <p className="game-log-modal__empty">Couldn&apos;t load the game log for {year}.</p>
        ) : rows === null ? (
          <p className="game-log-modal__empty">Loading game breakdown…</p>
        ) : games.length === 0 ? (
          <p className="game-log-modal__empty">No games in this selected range yet.</p>
        ) : (
          <div className="game-log-modal__table-wrap">
            <table className="game-log-modal__table">
              <thead>
                <tr>
                  <th>Week</th>
                  <th>Opponent</th>
                  <th>Result</th>
                  <th>{team} this game</th>
                  <th>{hasOpponentContext ? "Opponent entering" : "Baseline"}</th>
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
                  const venue = g.homeAway === "home" ? "vs" : g.homeAway === "away" ? "@" : "N";
                  const score = g.pointsFor === null || g.pointsAgainst === null
                    ? ""
                    : ` ${g.pointsFor}-${g.pointsAgainst}`;
                  return (
                    <tr key={g.gameId}>
                      <td className="num game-log-modal__week" data-label="Week">{weekLabel(g.week)}</td>
                      <td className="game-log-modal__opponent" data-label="Opponent">
                        <span className="game-log-modal__venue">{venue}</span>
                        {g.opponentTeamId && g.opponentSlug ? (
                          <TeamLink team={g.opponent} teamId={g.opponentTeamId} slug={g.opponentSlug} />
                        ) : (
                          <span className="game-log-modal__opponent-name">{g.opponent}</span>
                        )}
                      </td>
                      <td className={`num game-log-modal__result${g.win ? " win" : " loss"}`} data-label="Result">
                        <strong>{g.win ? "W" : "L"}</strong>{score}
                      </td>
                      <td className="num game-log-modal__actual" data-label="This game">
                        <strong>{format(ownValue)}</strong>
                      </td>
                      <td className="num game-log-modal__baseline" data-label="Opponent entering">
                        {oppValue === null ? (
                          <span className="game-log-modal__dash">
                            {hasOpponentContext ? "No prior games" : "—"}
                          </span>
                        ) : (
                          <>
                            <strong>{format(oppValue)}</strong>
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
                  <td colSpan={3}>Selected sample</td>
                  <td className="num"><strong>{format(totals.value)}</strong></td>
                  <td className="num">{games.length} games</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        <footer className="game-log-modal__footer">
          <span>{column.label} · {year}</span>
          <button type="button" onClick={onClose}>Close</button>
        </footer>
      </section>
    </div>,
    document.body
  );
}
