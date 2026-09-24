"use client";

import Link from "next/link";
import { useState } from "react";
import type { TeamCardData, TeamCardMetric } from "@/lib/teamCardData";

function MetricRow({ metric }: { metric: TeamCardMetric }) {
  return (
    <div className="ct-metric-row">
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <b>{metric.rank ? "#" + metric.rank : "—"}</b>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function TeamCardClient({ data }: { data: TeamCardData }) {
  const [status, setStatus] = useState<string>("");
  const [working, setWorking] = useState(false);
  const imageUrl = "/team/" + data.slug + "/card/image";
  const filename = "prime-" + data.slug + "-" + data.year + "-team-card.png";

  async function copyPng() {
    if (working) return;
    setWorking(true);
    setStatus("");
    try {
      const response = await fetch(imageUrl, { cache: "no-store" });
      if (!response.ok) throw new Error("Image generation failed.");
      const blob = await response.blob();

      if (navigator.clipboard?.write && typeof ClipboardItem !== "undefined") {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        setStatus("Copied PNG to clipboard.");
      } else {
        downloadBlob(blob, filename);
        setStatus("PNG downloaded — image clipboard is not supported in this browser.");
      }
    } catch {
      setStatus("Could not copy the PNG. Try Download PNG instead.");
    } finally {
      setWorking(false);
    }
  }

  async function downloadPng() {
    if (working) return;
    setWorking(true);
    setStatus("");
    try {
      const response = await fetch(imageUrl, { cache: "no-store" });
      if (!response.ok) throw new Error("Image generation failed.");
      downloadBlob(await response.blob(), filename);
      setStatus("PNG downloaded.");
    } catch {
      setStatus("Could not generate the PNG.");
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="ct-page ct-team-card-page">
      <div className="ct-actions">
        <Link href={"/team/" + data.slug}>← Team Profile</Link>
        <div>
          <button type="button" onClick={downloadPng} disabled={working}>Download PNG</button>
          <button className="primary" type="button" onClick={copyPng} disabled={working}>
            {working ? "Generating…" : "Copy PNG"}
          </button>
        </div>
        {status ? <p role="status">{status}</p> : null}
      </div>

      <article className="ct-card" aria-label={data.team + " " + data.year + " PRIME team profile"}>
        <header className="ct-topbar">
          <img src="/brand/prime-header.png" alt="PRIME" />
          <div>
            <strong>{data.year} TEAM PROFILE</strong>
            <span>PRIMECFB.COM</span>
          </div>
        </header>

        <section className="ct-team">
          <img className="ct-team-logo" src={data.logo} alt={data.team + " logo"} />
          <div className="ct-team-copy">
            <h1>{data.team}</h1>
            <p>{data.nickname}</p>
            <span>{data.record} · {data.conference} · Through Week {data.week}</span>
          </div>
          <div className="ct-prime-rank">
            <span>PRIME 25</span>
            <strong>{data.primeRank ? "#" + data.primeRank : "—"}</strong>
          </div>
        </section>

        <section className="ct-ratings">
          <div><span>NET RATING</span><strong>{data.net.value}</strong><b>{data.net.rank ? "#" + data.net.rank : "—"}</b></div>
          <div><span>OFF RATING</span><strong>{data.offenseRating.value}</strong><b>{data.offenseRating.rank ? "#" + data.offenseRating.rank : "—"}</b></div>
          <div><span>DEF RATING</span><strong>{data.defenseRating.value}</strong><b>{data.defenseRating.rank ? "#" + data.defenseRating.rank : "—"}</b></div>
        </section>

        <section className="ct-context">
          <div><span>STRENGTH OF RECORD</span><b>{data.strengthOfRecordRank ? "#" + data.strengthOfRecordRank : "—"}</b></div>
          <div><span>STRENGTH OF SCHEDULE</span><b>{data.strengthOfScheduleRank ? "#" + data.strengthOfScheduleRank : "—"}</b></div>
          <div>
            <span>ADJ. SCORING MARGIN</span>
            <strong>{data.adjustedScoringMargin.value}</strong>
            <b>{data.adjustedScoringMargin.rank ? "#" + data.adjustedScoringMargin.rank : "—"}</b>
          </div>
        </section>

        <div className="ct-adjusted-note">ALL ADVANCED METRICS OPPONENT-ADJUSTED</div>

        <section className="ct-splits">
          <div className="ct-split">
            <div className="ct-split-head"><h2>OFFENSE</h2><span>VALUE · RANK</span></div>
            {data.offense.map((item) => <MetricRow key={item.label} metric={item} />)}
          </div>
          <div className="ct-split">
            <div className="ct-split-head"><h2>DEFENSE</h2><span>VALUE · RANK</span></div>
            {data.defense.map((item) => <MetricRow key={item.label} metric={item} />)}
          </div>
        </section>

        <footer className="ct-footer">
          <img src="/brand/prime-header.png" alt="" />
          <strong>PRIMECFB.COM</strong>
        </footer>
      </article>
    </main>
  );
}
