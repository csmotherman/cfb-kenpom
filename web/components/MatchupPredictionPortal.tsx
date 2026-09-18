"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createPortal } from "react-dom";
import MarketOddsCard from "@/components/MarketOddsCard";
import { getMarketLinesSeason } from "@/lib/data";
import type { MarketGame, PredictionGame } from "@/lib/types";

type PredictionState =
  | { key: string; status: "none" | "locked" }
  | { key: string; status: "ready"; game: PredictionGame };

function confidence(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export default function MatchupPredictionPortal() {
  const pathname = usePathname();
  const route = useMemo(() => {
    const match = pathname.match(/^\/matchup\/(\d{4})\/([^/]+)$/);
    if (!match) return null;
    return { season: match[1], gameId: decodeURIComponent(match[2]) };
  }, [pathname]);
  const routeKey = route ? `${route.season}/${route.gameId}` : "";

  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [prediction, setPrediction] = useState<PredictionState>({ key: "", status: "none" });
  const [market, setMarket] = useState<{ key: string; game: MarketGame | null }>({ key: "", game: null });

  useEffect(() => {
    if (!route) return;

    let cancelled = false;
    let frame = 0;
    let attempts = 0;

    const findTarget = () => {
      if (cancelled) return;
      const node = document.querySelector<HTMLElement>(".matchup-v2-center");
      if (node) {
        setTarget(node);
        return;
      }
      attempts += 1;
      if (attempts < 60) frame = requestAnimationFrame(findTarget);
    };

    findTarget();
    return () => {
      cancelled = true;
      if (frame) cancelAnimationFrame(frame);
    };
  }, [route]);

  useEffect(() => {
    if (!route) return;
    let cancelled = false;
    const key = `${route.season}/${route.gameId}`;
    getMarketLinesSeason(route.season)
      .then((season) => {
        if (!cancelled) setMarket({ key, game: season?.games?.[route.gameId] ?? null });
      })
      .catch(() => {
        if (!cancelled) setMarket({ key, game: null });
      });
    return () => {
      cancelled = true;
    };
  }, [route]);

  useEffect(() => {
    if (!route) return;

    let cancelled = false;
    const controller = new AbortController();
    const key = `${route.season}/${route.gameId}`;

    fetch(`/api/matchup-prediction/${route.season}/${encodeURIComponent(route.gameId)}`, {
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (cancelled) return;
        if (response.status === 404) {
          setPrediction({ key, status: "none" });
          return;
        }
        if (response.status === 401 || response.status === 403) {
          setPrediction({ key, status: "locked" });
          return;
        }
        if (!response.ok) {
          setPrediction({ key, status: "none" });
          return;
        }
        const game = (await response.json()) as PredictionGame;
        if (!cancelled) setPrediction({ key, status: "ready", game });
      })
      .catch((error: unknown) => {
        if (cancelled || (error instanceof DOMException && error.name === "AbortError")) return;
        setPrediction({ key, status: "none" });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [route]);

  if (!route || !target) return null;
  const predictionReady = prediction.key === routeKey && prediction.status !== "none";
  const marketReady = market.key === routeKey && market.game !== null;
  if (!predictionReady && !marketReady) return null;

  return createPortal(
    <section className="matchup-prediction-shell" aria-label="Prediction and market context">
      {predictionReady ? (
        prediction.status === "ready" ? (
          <section className="matchup-prediction matchup-prediction--revealed" aria-label="PRIME premium prediction">
            <div className="matchup-prediction__eyebrow">
              <span>PRIME Prediction</span>
              <em>Advanced + Predictions</em>
            </div>
            <strong className="matchup-prediction__pick">{prediction.game.predictedWinner} is PRIME&apos;s pick</strong>
            <div className="matchup-prediction__result-grid">
              <span>
                <small>Win probability</small>
                <strong>{confidence(prediction.game.confidence)}</strong>
              </span>
              <span>
                <small>Model margin</small>
                <strong>{Math.abs(prediction.game.predictedMargin).toFixed(1)} pts</strong>
              </span>
            </div>
            <small className="matchup-prediction__fineprint">Model projection, not betting advice.</small>
          </section>
        ) : (
          <section className="matchup-prediction matchup-prediction--locked" aria-label="PRIME prediction locked">
            <div className="matchup-prediction__eyebrow">
              <span>PRIME Prediction</span>
              <em>Advanced + Predictions</em>
            </div>
            <strong className="matchup-prediction__hook">The rankings tell one story. What does the model see?</strong>
            <p>Reveal PRIME&apos;s projected winner, win probability and model margin for this matchup.</p>
            <Link href="/upgrade?feature=predictions" className="matchup-prediction__cta">Reveal PRIME&apos;s pick →</Link>
          </section>
        )
      ) : null}
      {marketReady ? <MarketOddsCard market={market.game} /> : null}
    </section>,
    target,
  );
}
