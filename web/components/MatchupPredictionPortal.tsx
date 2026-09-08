"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createPortal } from "react-dom";
import type { PredictionGame } from "@/lib/types";

type PredictionState =
  | { status: "idle" | "loading" | "none" }
  | { status: "locked" }
  | { status: "ready"; game: PredictionGame };

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

  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [prediction, setPrediction] = useState<PredictionState>({ status: "idle" });

  useEffect(() => {
    if (!route) {
      setTarget(null);
      return;
    }

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
    if (!route) {
      setPrediction({ status: "idle" });
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setPrediction({ status: "loading" });

    fetch(`/api/matchup-prediction/${route.season}/${encodeURIComponent(route.gameId)}`, {
      cache: "no-store",
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        if (cancelled) return;
        if (response.status === 404) {
          setPrediction({ status: "none" });
          return;
        }
        if (response.status === 401 || response.status === 403) {
          setPrediction({ status: "locked" });
          return;
        }
        if (!response.ok) {
          setPrediction({ status: "none" });
          return;
        }
        const game = (await response.json()) as PredictionGame;
        if (!cancelled) setPrediction({ status: "ready", game });
      })
      .catch((error: unknown) => {
        if (cancelled || (error instanceof DOMException && error.name === "AbortError")) return;
        setPrediction({ status: "none" });
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [route]);

  if (!target || prediction.status === "idle" || prediction.status === "loading" || prediction.status === "none") {
    return null;
  }

  return createPortal(
    prediction.status === "ready" ? (
      <section className="matchup-prediction matchup-prediction--revealed" aria-label="GRID Pro+ prediction">
        <div className="matchup-prediction__eyebrow">
          <span>GRID Prediction</span>
          <em>Pro+</em>
        </div>
        <strong className="matchup-prediction__pick">{prediction.game.predictedWinner} is GRID&apos;s pick</strong>
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
      <section className="matchup-prediction matchup-prediction--locked" aria-label="GRID Pro+ prediction locked">
        <div className="matchup-prediction__eyebrow">
          <span>GRID Prediction</span>
          <em>Pro+</em>
        </div>
        <strong className="matchup-prediction__hook">The rankings tell one story. What does the model see?</strong>
        <p>Reveal GRID&apos;s projected winner, win probability and model margin for this matchup.</p>
        <Link href="/account" className="matchup-prediction__cta">Reveal GRID&apos;s pick →</Link>
      </section>
    ),
    target,
  );
}
