"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { logoUrl } from "@/lib/teamCode";
import type { SampleGame, TeamSampleData } from "@/lib/custom-sample";

export type SampleStatus = "loading" | "ready" | "unavailable" | "stale" | "error";

type Props = {
  team: string;
  teamId: number;
  year: string;
  status: SampleStatus;
  data: TeamSampleData | null;
  /** Game ids the user has dropped from this team's sample. */
  excluded: string[];
  /** Custom samples only apply to the full season-to-date range. */
  rangeEnabled: boolean;
  weekLabel: (week: number) => string;
  onChange: (excluded: string[]) => void;
  onShowFullRange: () => void;
  onClose: () => void;
};

const SITE_LABEL: Record<SampleGame["ha"], string> = { H: "vs", A: "at", N: "neutral" };

function resultText(game: SampleGame): string {
  if (game.pf === null || game.pa === null) return "—";
  return `${game.win ? "W" : "L"} ${game.pf}–${game.pa}`;
}

function OpponentMark({ game }: { game: SampleGame }) {
  if (game.oi) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img className="cs-game__logo" src={logoUrl(game.oi, 64)} alt="" width={32} height={32} loading="lazy" />;
  }
  return <span className="cs-game__logo cs-game__logo--blank" aria-hidden="true">{(game.o ?? "?").slice(0, 2).toUpperCase()}</span>;
}

/**
 * "Customize Games" sheet: bottom sheet on phones, centered dialog on desktop.
 * Every game is a big touch target; nothing here changes official PRIME numbers.
 */
export default function GameSampleSheet({ team, teamId, year, status, data, excluded, rangeEnabled, weekLabel, onChange, onShowFullRange, onClose }: Props) {
  const [mounted, setMounted] = useState(false);
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => setMounted(true), []);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    function onKey(event: KeyboardEvent) { if (event.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = previous; };
  }, [onClose]);

  const games = useMemo(() => (data ? [...data.team.games].sort((a, b) => a.w - b.w || a.g.localeCompare(b.g)) : []), [data]);
  const excludedSet = useMemo(() => new Set(excluded), [excluded]);
  const includedCount = games.filter((game) => !excludedSet.has(game.g)).length;
  const isCustom = games.length > 0 && includedCount < games.length;

  function toggle(gameId: string) {
    onChange(excludedSet.has(gameId) ? excluded.filter((id) => id !== gameId) : [...excluded, gameId]);
  }

  if (!mounted) return null;

  const body = (() => {
    if (status === "loading") return <p className="cs-sheet__message">Loading {team}&apos;s games…</p>;
    if (status === "unavailable") return <p className="cs-sheet__message">Custom game samples aren&apos;t published for {team} in {year} yet.</p>;
    if (status === "stale") return <p className="cs-sheet__message">The custom-sample data is refreshing and doesn&apos;t match today&apos;s official numbers yet. Check back shortly.</p>;
    if (status === "error" || !data) return <p className="cs-sheet__message">Couldn&apos;t load {team}&apos;s games. Try again in a moment.</p>;
    if (!rangeEnabled) {
      return (
        <div className="cs-sheet__message">
          <p>Custom samples use the full season to date. Your week range is narrowed right now.</p>
          <button type="button" className="cs-btn cs-btn--primary" onClick={onShowFullRange}>Show the full season</button>
        </div>
      );
    }
    return (
      <>
        <div className="cs-sheet__tools" role="group" aria-label="Sample shortcuts">
          <button type="button" className="cs-btn" onClick={() => onChange([])} disabled={!isCustom}>Select all</button>
          <button type="button" className="cs-btn" onClick={() => onChange(games.map((game) => game.g))} disabled={includedCount === 0}>Clear all</button>
        </div>
        <ul className="cs-games" aria-label={`${team} games`}>
          {games.map((game) => {
            const on = !excludedSet.has(game.g);
            return (
              <li key={game.g}>
                <button type="button" role="checkbox" aria-checked={on} className={`cs-game${on ? " is-on" : ""}`} onClick={() => toggle(game.g)}>
                  <span className="cs-game__check" aria-hidden="true">{on ? "✓" : ""}</span>
                  <span className="cs-game__week">{weekLabel(game.w)}</span>
                  <OpponentMark game={game} />
                  <span className="cs-game__main">
                    <span className="cs-game__opp">{game.o ?? "Opponent"}</span>
                    <span className="cs-game__meta">
                      <span>{SITE_LABEL[game.ha]}</span>
                      {game.fbs ? null : <span className="cs-tag" title="Not part of the opponent-adjusted fit; changes raw stats only">non-FBS</span>}
                    </span>
                  </span>
                  <span className={`cs-game__result${game.win ? " is-win" : " is-loss"}`}>{resultText(game)}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {includedCount === 0 ? <p className="cs-sheet__warning" role="status">No games selected — stats can&apos;t be calculated. Pick at least one game.</p> : null}
        <p className="cs-sheet__note">
          Only {team}&apos;s row changes. Opponent-adjusted stats keep every opponent&apos;s official rating. PRIME Ratings, rankings, and predictions always use the full official sample.
        </p>
      </>
    );
  })();

  return createPortal(
    <div className="cs-backdrop" role="presentation" onClick={onClose}>
      <div className="cs-sheet" role="dialog" aria-modal="true" aria-labelledby={`cs-title-${teamId}`} onClick={(event) => event.stopPropagation()}>
        <div className="cs-sheet__grab" aria-hidden="true" />
        <header className="cs-sheet__header">
          <div>
            <span className="cs-eyebrow">Custom sample</span>
            <h2 id={`cs-title-${teamId}`}>{team}</h2>
            <p className="cs-sheet__count">
              {data && rangeEnabled && status === "ready" ? (
                <>
                  <strong>{includedCount} of {games.length}</strong> games included
                  {isCustom ? <span className="cs-badge">Custom · {includedCount}/{games.length}</span> : null}
                </>
              ) : "Choose which games count"}
            </p>
          </div>
          <button type="button" className="cs-close" aria-label="Close" onClick={onClose}>&times;</button>
        </header>
        <div className="cs-sheet__body">{body}</div>
        <footer className="cs-sheet__footer">
          <button type="button" className="cs-btn" onClick={() => onChange([])} disabled={!isCustom}>Reset to all games</button>
          <button type="button" className="cs-btn cs-btn--primary" onClick={onClose}>Done</button>
        </footer>
      </div>
    </div>,
    document.body,
  );
}
