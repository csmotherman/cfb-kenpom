"use client";

import { useEffect } from "react";

const META_PATH = "/data/meta.json";
const POLL_MS = 60_000;

type FreshnessMeta = {
  dataVersion?: string;
};

/**
 * Watches the public data version without mutating React-owned DOM.
 *
 * Already-loaded seasons are cached in memory for fast navigation. If a newer
 * validated dataset is published while a tab is still open, reload once so all
 * cached public data moves to the same version. The visible "data updated"
 * timestamp is rendered declaratively by each page instead of being injected
 * into the DOM from here.
 */
export default function TableFreshnessStamp() {
  useEffect(() => {
    let stopped = false;
    let checking = false;
    let initialized = false;
    let baselineVersion: string | null = null;

    const checkFreshness = async () => {
      if (stopped || checking) return;
      checking = true;

      try {
        const response = await fetch(META_PATH, { cache: "no-store" });
        if (!response.ok) return;

        const meta = (await response.json()) as FreshnessMeta;
        if (stopped) return;

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
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  return null;
}
