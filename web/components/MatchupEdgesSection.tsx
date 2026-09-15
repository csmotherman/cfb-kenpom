"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { MatchupEdge, MatchupEdgesGame } from "@/lib/types";

type LoadState =
  | { key: string; status: "loading" }
  | { key: string; status: "none" }
  | { key: string; status: "locked" }
  | { key: string; status: "ready"; game: MatchupEdgesGame };

function rankText(rank: number | null): string {
  return rank === null ? "unranked" : `No. ${rank}`;
}

function rateText(edge: MatchupEdge, value: number): string {
  return edge.unit === "epa" ? `${value >= 0 ? "+" : ""}${value.toFixed(3)} EPA/play` : `${(value * 100).toFixed(1)}%`;
}

// Guarded, non-causal phrasing throughout: pregame tendencies "lean toward"
// or "line up against" one side, they never "predict," "cause," or
// "guarantee" an outcome -- these are situational profiles, not a pick.
function edgeSentence(edge: MatchupEdge): string {
  const offenseBit = `${edge.offenseTeam}'s ${edge.offenseLabel} (${rankText(edge.offenseRank)}, ${rateText(edge, edge.offenseRate)})`;
  const defenseBit = `${edge.defenseTeam}'s ${edge.defenseLabel} (${rankText(edge.defenseRank)}, ${rateText(edge, edge.defenseRate)})`;
  if (edge.style) {
    return `${offenseBit} lines up against ${defenseBit}. A big-play matchup worth watching, not a strength or weakness by itself.`;
  }
  if (!edge.advantageTeam) {
    return `${offenseBit} lines up against ${defenseBit} — pregame tendencies are close to even here.`;
  }
  return `${offenseBit} lines up against ${defenseBit} — pregame tendencies lean toward ${edge.advantageTeam} in this specific matchup.`;
}

function EdgeCard({ edge }: { edge: MatchupEdge }) {
  return (
    <article className={`matchup-edge-card${edge.style ? " matchup-edge-card--style" : ""}`}>
      <div className="matchup-edge-card__head">
        <span className="matchup-edge-card__eyebrow">{edge.title}</span>
        {edge.advantageTeam && (
          <span className="matchup-edge-card__advantage">{edge.advantageTeam} edge</span>
        )}
        {edge.style && <span className="matchup-edge-card__advantage matchup-edge-card__advantage--style">Big-play matchup</span>}
      </div>
      <div className="matchup-edge-card__stats">
        <div className="matchup-edge-card__stat">
          <strong>{edge.offenseTeam}</strong>
          <span>{edge.offenseLabel}</span>
          <em>{rateText(edge, edge.offenseRate)} · {rankText(edge.offenseRank)}</em>
        </div>
        <div className="matchup-edge-card__stat">
          <strong>{edge.defenseTeam}</strong>
          <span>{edge.defenseLabel}</span>
          <em>{rateText(edge, edge.defenseRate)} · {rankText(edge.defenseRank)}</em>
        </div>
      </div>
      <p className="matchup-edge-card__sentence">{edgeSentence(edge)}</p>
      <p className="matchup-edge-card__definition">{edge.definition}</p>
    </article>
  );
}

export default function MatchupEdgesSection({ season, gameId }: { season: number; gameId: string }) {
  const routeKey = `${season}/${gameId}`;
  const [state, setState] = useState<LoadState>({ key: "", status: "loading" });

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    fetch(`/api/matchup-exploratory/${season}/${encodeURIComponent(gameId)}`, {
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (cancelled) return;
        if (response.status === 404) {
          setState({ key: routeKey, status: "none" });
          return;
        }
        if (response.status === 401 || response.status === 403) {
          setState({ key: routeKey, status: "locked" });
          return;
        }
        if (!response.ok) {
          setState({ key: routeKey, status: "none" });
          return;
        }
        const game = (await response.json()) as MatchupEdgesGame;
        if (!cancelled) setState({ key: routeKey, status: "ready", game });
      })
      .catch((error: unknown) => {
        if (cancelled || (error instanceof DOMException && error.name === "AbortError")) return;
        setState({ key: routeKey, status: "none" });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [season, gameId, routeKey]);

  if (state.key !== routeKey) return null;
  if (state.status === "loading" || state.status === "none") return null;

  if (state.status === "locked") {
    return (
      <section className="matchup-edges matchup-edges--locked" aria-label="LEILA matchup edges locked">
        <div className="matchup-edges__head">
          <h2>Matchup Edges</h2>
          <span className="matchup-edges__badge">Research</span>
        </div>
        <p>See where each team&apos;s season-long tendencies line up against this specific opponent — sustaining drives, recovering from bad downs, staying on schedule, and more.</p>
        <Link href="/upgrade?feature=exploratory" className="matchup-edges__cta">Unlock matchup edges →</Link>
      </section>
    );
  }

  const { game } = state;

  if (game.status === "limited") {
    return (
      <section className="matchup-edges matchup-edges--empty" aria-label="LEILA matchup edges">
        <div className="matchup-edges__head">
          <h2>Matchup Edges</h2>
          <span className="matchup-edges__badge">Research</span>
        </div>
        <p className="matchup-edges__note">Limited sample — not enough of the season has been played yet to calibrate matchup edges for this game.</p>
      </section>
    );
  }

  if (game.status === "even" || game.edges.length === 0) {
    return (
      <section className="matchup-edges matchup-edges--empty" aria-label="LEILA matchup edges">
        <div className="matchup-edges__head">
          <h2>Matchup Edges</h2>
          <span className="matchup-edges__badge">Research</span>
        </div>
        <p className="matchup-edges__note">Even matchup — no situational tendency stands out enough above the usual noise for either team in this game.</p>
      </section>
    );
  }

  return (
    <section className="matchup-edges" aria-label="LEILA matchup edges">
      <div className="matchup-edges__head">
        <h2>Matchup Edges</h2>
        <span className="matchup-edges__badge">Research</span>
      </div>
      <p className="matchup-edges__intro">Situational tendencies pulled from each team&apos;s season to date, evaluated only against what this specific opponent has shown. Descriptive, not a prediction.</p>
      <div className="matchup-edges__grid">
        {game.edges.map((edge: MatchupEdge) => (
          <EdgeCard key={`${edge.pairing}-${edge.offenseTeam}`} edge={edge} />
        ))}
      </div>
    </section>
  );
}
