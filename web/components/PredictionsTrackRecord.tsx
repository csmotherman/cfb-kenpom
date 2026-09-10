"use client";

import { useEffect, useState } from "react";
import { getMeta, getPredictionsTrackRecord } from "@/lib/data";
import type { PredictionsTrackRecord as TrackRecord } from "@/lib/types";

function pct(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function margin(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)} pts`;
}

/** Public, ungated proof-of-work for the Predictions paywall: how the frozen
 * model has actually done straight-up, graded only against final scores.
 * Shown on /upgrade so a visitor can see real accuracy before paying for
 * picks -- never a fabricated number, and never 0% for a week that just
 * hasn't been played yet (see PredictionWeekRecord in lib/types.ts). */
export default function PredictionsTrackRecord() {
  const [status, setStatus] = useState<"loading" | "unavailable" | "ready">("loading");
  const [record, setRecord] = useState<TrackRecord | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const meta = await getMeta();
      const year = meta.rankingsYears[meta.rankingsYears.length - 1];
      const trackRecord = await getPredictionsTrackRecord(year);
      if (cancelled) return;
      if (!trackRecord || trackRecord.overall.graded === 0) {
        setStatus("unavailable");
      } else {
        setRecord(trackRecord);
        setStatus("ready");
      }
    })().catch(() => {
      if (!cancelled) setStatus("unavailable");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") return null;

  if (status === "unavailable") {
    return (
      <section className="track-record" aria-labelledby="trackRecordTitle">
        <div className="upgrade-section-heading upgrade-section-heading--compact">
          <div>
            <span className="eyebrow">Model Accuracy</span>
            <h2 id="trackRecordTitle">Track record</h2>
          </div>
        </div>
        <p className="track-record__empty">
          The model publishes a track record once enough games this season have final scores to grade against.
          Nothing is shown here until then.
        </p>
      </section>
    );
  }

  const trackRecord = record as TrackRecord;

  return (
    <section className="track-record" aria-labelledby="trackRecordTitle">
      <div className="upgrade-section-heading upgrade-section-heading--compact">
        <div>
          <span className="eyebrow">Model Accuracy &middot; {trackRecord.season}</span>
          <h2 id="trackRecordTitle">Track record</h2>
        </div>
      </div>

      <div className="track-record__overall">
        <div className="track-record__stat">
          <strong>{pct(trackRecord.overall.accuracySU)}</strong>
          <span>Straight-up, {trackRecord.overall.correct}-{trackRecord.overall.graded - trackRecord.overall.correct}</span>
        </div>
        <div className="track-record__stat">
          <strong>{margin(trackRecord.overall.avgAbsMarginError)}</strong>
          <span>Avg. margin error</span>
        </div>
        <div className="track-record__stat">
          <strong>{trackRecord.overall.graded}</strong>
          <span>Graded games</span>
        </div>
      </div>

      <table className="track-record__table">
        <thead>
          <tr>
            <th scope="col">Week</th>
            <th scope="col">Record</th>
            <th scope="col">SU%</th>
            <th scope="col">Avg. error</th>
          </tr>
        </thead>
        <tbody>
          {trackRecord.weeks.map((week) => (
            <tr key={week.week}>
              <td>{week.week}</td>
              <td>
                {week.graded > 0
                  ? `${week.correct}-${week.graded - week.correct}`
                  : week.games > 0
                    ? "Not played yet"
                    : "—"}
              </td>
              <td>{pct(week.accuracySU)}</td>
              <td>{margin(week.avgAbsMarginError)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="track-record__note">
        Straight-up (winner only), graded against final scores LEILA Ratings has published. Not betting advice, not against a spread.
      </p>
    </section>
  );
}
