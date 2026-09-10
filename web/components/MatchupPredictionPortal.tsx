"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createPortal } from "react-dom";
import type { PredictionGame } from "@/lib/types";

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

  if (!route || !target || prediction.key !== routeKey || prediction.status === "none") {
    return null;
  }

  return createPortal(
    prediction.status === "ready" ? (
      <section className="matchup-prediction matchup-prediction--revealed" aria-label="LEILA Pro+ prediction">
        <div className="matchup-prediction__eyebrow">
          <span>LEILA Prediction</span>
          <em>Pro+</em>
        </div>
        <strong className="matchup-prediction__pick">{prediction.game.predictedWinner} is LEILA&apos;s pick</strong>
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
      <section className="matchup-prediction matchup-prediction--locked" aria-label="LEILA Pro+ prediction locked">
        <div className="matchup-prediction__eyebrow">
          <span>LEILA Prediction</span>
          <em>Pro+</em>
        </div>
        <strong className="matchup-prediction__hook">The rankings tell one story. What does the model see?</strong>
        <p>Reveal LEILA&apos;s projected winner, win probability and model margin for this matchup.</p>
        <Link href="/account" className="matchup-prediction__cta">Reveal LEILA&apos;s pick →</Link>
      </section>
    ),
    target,
  );
}
