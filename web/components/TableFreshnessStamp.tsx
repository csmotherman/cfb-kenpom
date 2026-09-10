"use client";

import { useEffect } from "react";
import { getMeta } from "@/lib/data";

const TARGETS = [
  "#mainContent.table-main > .table-scroll",
  "#advancedTable.table-main > .advanced-table-shell",
];

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
 * tables. The timestamp comes from public data/meta.json, so it advances only
 * when the validated data export actually runs.
 */
export default function TableFreshnessStamp() {
  useEffect(() => {
    let stopped = false;
    let generatedAt: string | null = null;

    const install = () => {
      if (stopped || !generatedAt) return;

      TARGETS.forEach((selector) => {
        const target = document.querySelector<HTMLElement>(selector);
        if (!target || target.previousElementSibling?.classList.contains("table-updated-at")) return;

        const stamp = document.createElement("div");
        stamp.className = "table-updated-at";

        const label = document.createElement("span");
        label.textContent = "Updated at";

        const time = document.createElement("time");
        time.dateTime = generatedAt!;
        time.textContent = formatUpdatedAt(generatedAt!);

        stamp.append(label, time);
        target.parentElement?.insertBefore(stamp, target);
      });
    };

    getMeta()
      .then((meta) => {
        if (stopped) return;
        generatedAt = meta.generatedAt ?? null;
        install();
      })
      .catch(() => {
        // Freshness text is supplemental; page data loading owns error UI.
      });

    const observer = new MutationObserver(install);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      stopped = true;
      observer.disconnect();
    };
  }, []);

  return null;
}
