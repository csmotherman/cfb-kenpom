"use client";

import { useEffect } from "react";

const META_PATH = "/data/meta.json";
const POLL_MS = 60_000;
const EASTERN_TIME_ZONE = "America/New_York";

type FreshnessMeta = {
  dataVersion?: string;
  generatedAt?: string;
};

function formatEasternTimestamp(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: EASTERN_TIME_ZONE,
    timeZoneName: "short",
  }).format(date);
}

function syncVisibleTimestamp(generatedAt: string | null) {
  if (!generatedAt) return;
  const formatted = formatEasternTimestamp(generatedAt);
  if (!formatted) return;

  document.querySelectorAll<HTMLTimeElement>("time.data-updated").forEach((element) => {
    const nextText = `Data updated ${formatted}`;
    if (element.textContent !== nextText) element.textContent = nextText;
    if (element.dateTime !== generatedAt) element.dateTime = generatedAt;
  });
}

/**
 * Keeps already-open tabs on the newest published dataset and normalizes the
 * visible data timestamp to U.S. Eastern time. Most pages render the timestamp
 * declaratively; the DOM sync also covers legacy page renderers so every table
 * shows the same refresh time while they are migrated to the shared format.
 */
export default function TableFreshnessStamp() {
  useEffect(() => {
    let stopped = false;
    let checking = false;
    let initialized = false;
    let baselineVersion: string | null = null;
    let latestGeneratedAt: string | null = null;

    const observer = new MutationObserver(() => {
      if (!stopped) syncVisibleTimestamp(latestGeneratedAt);
    });
    observer.observe(document.body, { childList: true, subtree: true });

    const checkFreshness = async () => {
      if (stopped || checking) return;
      checking = true;

      try {
        const response = await fetch(META_PATH, { cache: "no-store" });
        if (!response.ok) return;

        const meta = (await response.json()) as FreshnessMeta;
        if (stopped) return;

        latestGeneratedAt =
          typeof meta.generatedAt === "string" && meta.generatedAt
            ? meta.generatedAt
            : null;
        syncVisibleTimestamp(latestGeneratedAt);

        const nextVersion =
          typeof meta.dataVersion === "string" && meta.dataVersion
            ? meta.dataVersion
            : null;

        if (!initialized) {
          initialized = true;
          baselineVersion = nextVersion;
          return;
        }

        if (baselineVersion && nextVersion && nextVersion !== baselineVersion) {
          window.location.reload();
          return;
        }

        if (!baselineVersion && nextVersion) baselineVersion = nextVersion;
      } catch {
        // Supplemental freshness checks must never interrupt normal page data
        // loading during a transient network or hosting failure.
      } finally {
        checking = false;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void checkFreshness();
    };
    const onFocus = () => void checkFreshness();

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    const interval = window.setInterval(() => void checkFreshness(), POLL_MS);
    void checkFreshness();

    return () => {
      stopped = true;
      observer.disconnect();
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return null;
}
