"use client";

import { useEffect } from "react";

const TARGETS = [
  "#mainContent.table-main > .table-scroll",
  "#advancedTable.table-main > .advanced-table-shell",
];
const META_PATH = "/data/meta.json";
const POLL_MS = 60_000;

type FreshnessMeta = {
  generatedAt?: string;
  dataVersion?: string;
};

function formatUpdatedAt(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Detroit",
    timeZoneName: "short",
  }).format(new Date(value));
}

/**
 * Adds one small freshness stamp immediately above the Ratings and Advanced
 * tables and watches the public data version for a newer validated publish.
 *
 * The app intentionally keeps already-loaded seasons in memory for instant
 * navigation. Without this global check, a tab left open through a Saturday
 * refresh could keep serving the old in-memory snapshot indefinitely. A new
 * dataVersion therefore reloads the tab once so every cached dataset moves to
 * the same newly published version.
 */
export default function TableFreshnessStamp() {
  useEffect(() => {
    let stopped = false;
    let checking = false;
    let initialized = false;
    let baselineVersion: string | null = null;
    let generatedAt: string | null = null;

    const installOrUpdate = () => {
      const timestamp = generatedAt;
      if (stopped || !timestamp) return;

      TARGETS.forEach((selector) => {
        const target = document.querySelector<HTMLElement>(selector);
        if (!target) return;

        let stamp = target.previousElementSibling as HTMLElement | null;
        if (!stamp?.classList.contains("table-updated-at")) {
          stamp = document.createElement("div");
          stamp.className = "table-updated-at";

          const label = document.createElement("span");
          label.textContent = "Updated at";

          const time = document.createElement("time");
          stamp.append(label, time);
          target.parentElement?.insertBefore(stamp, target);
        }

        const time = stamp.querySelector("time");
        if (time) {
          time.dateTime = timestamp;
          time.textContent = formatUpdatedAt(timestamp);
        }
      });
    };

    const checkFreshness = async () => {
      if (stopped || checking) return;
      checking = true;
      try {
        const response = await fetch(META_PATH, { cache: "no-store" });
        if (!response.ok) return;
        const meta = (await response.json()) as FreshnessMeta;
        if (stopped) return;

        const nextVersion = typeof meta.dataVersion === "string" && meta.dataVersion ? meta.dataVersion : null;
        const nextGeneratedAt = typeof meta.generatedAt === "string" && meta.generatedAt ? meta.generatedAt : null;

        if (!initialized) {
          initialized = true;
          baselineVersion = nextVersion;
          generatedAt = nextGeneratedAt;
          installOrUpdate();
          return;
        }

        if (baselineVersion && nextVersion && nextVersion !== baselineVersion) {
          window.location.reload();
          return;
        }

        // A generated timestamp can advance even if a future exporter decides
        // not to change the version hash. Keep the supplemental stamp honest.
        if (nextGeneratedAt && nextGeneratedAt !== generatedAt) {
          generatedAt = nextGeneratedAt;
          installOrUpdate();
        }
        if (!baselineVersion && nextVersion) baselineVersion = nextVersion;
      } catch {
        // Freshness polling is supplemental; normal page data/error handling
        // remains authoritative during a transient network failure.
      } finally {
        checking = false;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") void checkFreshness();
    };
    const onFocus = () => void checkFreshness();

    const observer = new MutationObserver(installOrUpdate);
    observer.observe(document.body, { childList: true, subtree: true });
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
