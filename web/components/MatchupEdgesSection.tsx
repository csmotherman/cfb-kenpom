"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { MatchupEdge, MatchupEdgesGame } from "@/lib/types";

type LoadState =
  | { key: string; status: "loading" }
  | { key: string; status: "none" }
  | { key: string; status: "locked" }
  | { key: string; status: "ready"; game: MatchupEdgesGame };

// "Edge" should mean a real strength-vs-weakness collision, not merely two
// good units with a modest ranking gap. With ~130-140 FBS teams, these bounds
// require one side to be clearly strong and the paired opponent tendency to be
// clearly weak before we surface the matchup as an advantage.
const EDGE_STRONG_RANK_MAX = 40;
const EDGE_WEAK_RANK_MIN = 95;
const EDGE_MIN_RANK_GAP = 55;

function rankText(rank: number | null): string {
  return rank === null ? "unranked" : `No. ${rank}`;
}

function rateText(edge: MatchupEdge, value: number): string {
  return edge.unit === "epa" ? `${value >= 0 ? "+" : ""}${value.toFixed(3)} EPA/play` : `${(value * 100).toFixed(1)}%`;
}

function isTrueMismatch(edge: MatchupEdge): boolean {
  if (edge.style || !edge.advantageTeam) return false;
  if (edge.offenseRank === null || edge.defenseRank === null) return false;

  const strongRank = Math.min(edge.offenseRank, edge.defenseRank);
  const weakRank = Math.max(edge.offenseRank, edge.defenseRank);
  return (
    strongRank <= EDGE_STRONG_RANK_MAX &&
    weakRank >= EDGE_WEAK_RANK_MIN &&
    weakRank - strongRank >= EDGE_MIN_RANK_GAP
  );
}

// Guarded, non-causal phrasing throughout: pregame tendencies "lean toward"
// or "line up against" one side, they never "predict," "cause," or
// "guarantee" an outcome -- these are situational profiles, not a pick.
function edgeSentence(edge: MatchupEdge): string {
  const offenseBit = `${edge.offenseTeam}'s ${edge.offenseLabel} (${rankText(edge.offenseRank)}, ${rateText(edge, edge.offenseRate)})`;
  const defenseBit = `${edge.defenseTeam}'s ${edge.defenseLabel} (${rankText(edge.defenseRank)}, ${rateText(edge, edge.defenseRate)})`;
  return `${offenseBit} lines up against ${defenseBit} — the strong-vs-weak ranking split creates a clear matchup edge for ${edge.advantageTeam}.`;
}

function EdgeCard({ edge }: { edge: MatchupEdge }) {
  return (
    <article className="matchup-edge-card">
      <div className="matchup-edge-card__head">
        <span className="matchup-edge-card__eyebrow">{edge.title}</span>
        <span className="matchup-edge-card__advantage">{edge.advantageTeam} edge</span>
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

export default function MatchupEdgesSection({ season, gameId, onReady }: { season: number; gameId: string; onReady?: (key: string) => void }) {
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

  useEffect(() => {
    if (state.key === routeKey && state.status !== "loading") onReady?.(routeKey);
  }, [state.key, state.status, routeKey, onReady]);

  if (state.key !== routeKey) return null;
  if (state.status === "loading" || state.status === "none") return null;

  if (state.status === "locked") {
    return (
      <section className="matchup-edges matchup-edges--locked" aria-label="PRIME matchup edges locked">
        <div className="matchup-edges__head">
          <h2>Matchup Edges</h2>
          <span className="matchup-edges__badge">Research</span>
        </div>
        <p>See where one team&apos;s clear statistical strength runs into a specific weakness on the other side — true strength-vs-weakness mismatches, not simply two highly ranked units.</p>
        <Link href="/upgrade?feature=exploratory" className="matchup-edges__cta">Unlock matchup edges →</Link>
      </section>
    );
  }

  const { game } = state;

  if (game.status === "limited") {
    return (
      <section className="matchup-edges matchup-edges--empty" aria-label="PRIME matchup edges">
        <div className="matchup-edges__head">
          <h2>Matchup Edges</h2>
          <span className="matchup-edges__badge">Research</span>
        </div>
        <p className="matchup-edges__note">Limited sample — not enough of the season has been played yet to calibrate matchup edges for this game.</p>
      </section>
    );
  }

  const edges = game.edges.filter(isTrueMismatch);

  if (edges.length === 0) {
    return (
      <section className="matchup-edges matchup-edges--empty" aria-label="PRIME matchup edges">
        <div className="matchup-edges__head">
          <h2>Matchup Edges</h2>
          <span className="matchup-edges__badge">Research</span>
        </div>
        <p className="matchup-edges__note">No clear strength-vs-weakness mismatch. An edge only appears when one side ranks among the stronger units nationally and the opponent ranks clearly weak in the corresponding area.</p>
      </section>
    );
  }

  return (
    <section className="matchup-edges" aria-label="PRIME matchup edges">
      <div className="matchup-edges__head">
        <h2>Matchup Edges</h2>
        <span className="matchup-edges__badge">Research</span>
      </div>
      <p className="matchup-edges__intro">Only clear strength-vs-weakness mismatches are shown: one side must rank highly in the paired metric while the opponent ranks near the bottom nationally. Two good units are not labeled an edge.</p>
      <div className="matchup-edges__grid">
        {edges.map((edge: MatchupEdge) => (
          <EdgeCard key={`${edge.pairing}-${edge.offenseTeam}`} edge={edge} />
        ))}
      </div>
    </section>
  );
}
