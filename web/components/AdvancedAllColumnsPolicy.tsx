"use client";

import { useLayoutEffect } from "react";

/**
 * Advanced analytics is intentionally an all-columns table now. The page still
 * owns a legacy showAllColumns state because its tab/perspective logic is large
 * and tightly coupled to the analytics definitions. Until that state is removed
 * at the source, keep it pinned to the expanded state immediately after mount
 * and after any tab change. The visual toggle is hidden by table-behavior-fixes.css.
 *
 * The first enforcement runs in a layout effect so the collapsed table is not
 * painted on initial load. MutationObserver + requestAnimationFrame then batches
 * subsequent tab changes before the next visual frame.
 */
export default function AdvancedAllColumnsPolicy() {
  useLayoutEffect(() => {
    let frame = 0;

    const expandIfNeeded = () => {
      const toggle = document.querySelector<HTMLButtonElement>(
        "#advancedTable .show-all-columns-toggle"
      );
      if (!toggle) return;

      const label = (toggle.textContent ?? "").trim().toLowerCase();
      if (label.startsWith("show all columns")) toggle.click();
    };

    const scheduleEnforcement = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(expandIfNeeded);
    };

    expandIfNeeded();

    const observer = new MutationObserver(scheduleEnforcement);
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
