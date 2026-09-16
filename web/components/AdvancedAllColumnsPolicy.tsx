"use client";

import { useEffect } from "react";

/**
 * Advanced analytics is intentionally an all-columns table now. The page still
 * owns a legacy showAllColumns state because its tab/perspective logic is large
 * and tightly coupled to the analytics definitions. Until that state is removed
 * at the source, keep it pinned to the expanded state immediately after mount
 * and after any tab change. The visual toggle is hidden by table-behavior-fixes.css.
 *
 * MutationObserver callbacks run before the next paint; requestAnimationFrame
 * batches React's DOM changes so users do not see the collapsed intermediate
 * state when switching tabs.
 */
export default function AdvancedAllColumnsPolicy() {
  useEffect(() => {
    let frame = 0;

    const enforceExpandedColumns = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const toggle = document.querySelector<HTMLButtonElement>(
          "#advancedTable .show-all-columns-toggle"
        );
        if (!toggle) return;

        const label = (toggle.textContent ?? "").trim().toLowerCase();
        if (label.startsWith("show all columns")) toggle.click();
      });
    };

    enforceExpandedColumns();

    const observer = new MutationObserver(enforceExpandedColumns);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return null;
}
