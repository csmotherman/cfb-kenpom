"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { logoUrl } from "@/lib/teamCode";
import { getMeta, getPredictionsWeek, getRankingsSeason } from "@/lib/data";
import type { PredictionGame } from "@/lib/types";

const LAUNCH_WEEK = 4;

function signedMargin(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(1);
}

export default function PredictionsPage() {
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [status, setStatus] = useState<"loading" | "before-launch" | "no-data" | "ready">("loading");
  const [season, setSeason] = useState<number | null>(null);
  const [week, setWeek] = useState<number | null>(null);
  const [games, setGames] = useState<PredictionGame[]>([]);
  const [predictionAccess, setPredictionAccess] = useState<"limited" | "full">("full");
  const [totalGames, setTotalGames] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const meta = await getMeta();
      const latestSeason = meta.rankingsYears[meta.rankingsYears.length - 1];
      const seasonData = await getRankingsSeason(latestSeason);
      const currentWeek = seasonData.weeks[seasonData.weeks.length - 1];
      if (cancelled) return;
      setSeason(latestSeason);
      setWeek(currentWeek);

      if (currentWeek < LAUNCH_WEEK) {
        setStatus("before-launch");
        return;
      }
      const predictions = await getPredictionsWeek(latestSeason, currentWeek);
      if (cancelled) return;
      if (!predictions || predictions.games.length === 0) {
        setStatus("no-data");
      } else {
        setGames(predictions.games);
        setPredictionAccess(predictions.access ?? "full");
        setTotalGames(predictions.totalGames ?? predictions.games.length);
        setStatus("ready");
      }
    })().catch((error: Error) => { if (!cancelled) setLoadError(error); });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) throw loadError;

  return (
    <>
      <a className="skip-link" href="#predictionsContent">Skip to predictions</a>
      <SiteHeader tagline="Weekly Game Predictions" />
      <SiteNav />

      <nav className="breadcrumbs" aria-label="Breadcrumb">
        <Link href="/">Ratings</Link>
        <span className="crumb-sep">/</span>
        <span className="crumb-current">Predictions</span>
      </nav>

      <section className="advanced-intro">
        <div className="advanced-intro__copy">
          <div className="advanced-intro__eyebrow">
            <span className="eyebrow">Weekly Predictions</span>
            <span className="advanced-intro__badge">Beta</span>
          </div>
          <h1>This week&rsquo;s game-by-game picks</h1>
          <p>
            Model-projected winners and margins for published FBS matchups, available starting in Week 4.
          </p>
        </div>
      </section>

      <main id="predictionsContent" className="container predictions-main">
        {status === "loading" ? (
          <div className="predictions-state">Loading predictions…</div>
        ) : status === "before-launch" ? (
          <div className="predictions-state predictions-state--launch">
            <h2>Predictions launch in Week {LAUNCH_WEEK}</h2>
            <p>
              The {season} season is currently through Week {week}. Weekly Predictions need a few weeks of real
              season data to be worth publishing, so they start in Week {LAUNCH_WEEK}. Check back once the season
              gets there.
            </p>
          </div>
        ) : status === "no-data" ? (
          <div className="predictions-state">
            <h2>No predictions published yet for Week {week}</h2>
            <p>Check back once this week&rsquo;s predictions have been generated.</p>
          </div>
        ) : (
          <div className="predictions-list">
            {games.map((g) => (
              <PredictionRow key={g.gameId} game={g} />
            ))}
            {predictionAccess === "limited" && totalGames > games.length ? (
              <div className="predictions-cta">
                <span>
                  GRID Pro includes {games.length} of {totalGames} published predictions this week.
                </span>
                <Link className="auth-button" href="/account">Unlock all with Pro+</Link>
              </div>
            ) : null}
          </div>
        )}
      </main>

      <SiteFooter note="Weekly Predictions are model-generated projections, not betting advice. Margins and win probabilities reflect the site's SOAR model as of publish time." />
    </>
  );
}

function PredictionRow({ game }: { game: PredictionGame }) {
  return (
    <div className="predictions-row">
      <div className="predictions-row__matchup">
        <TeamChip team={game.awayTeam} teamId={game.awayTeamId} />
        <span className="predictions-row__at">@</span>
        <TeamChip team={game.homeTeam} teamId={game.homeTeamId} />
      </div>

      <div className="predictions-row__pick">
        <strong>{game.predictedWinner}</strong>
        <span className="mono">{signedMargin(game.predictedMargin)}</span>
      </div>
    </div>
  );
}

function TeamChip({ team, teamId }: { team: string; teamId: number }) {
  return (
    <span className="predictions-row__team">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={logoUrl(teamId)} alt="" loading="lazy" decoding="async" />
      {team}
    </span>
  );
}
