"use client";

import { useEffect } from "react";

const SCROLL_WRAPPERS = [
  ".table-scroll",
  ".history-table-scroll",
  ".network-detail__table-wrap",
  ".game-log-modal__table-wrap",
].join(",");

/**
 * iOS/WebKit has been inconsistent with horizontally-sticky <td> elements
 * inside overflowed semantic tables. Keep the tables semantic and let the
 * scroll container publish its exact horizontal offset as a CSS variable.
 * mobile-tables.css uses that value to translate only the frozen identity
 * cells, so RK + Team remain visually fixed while the metrics move beneath.
 */
export default function MobileTableFreeze() {
  useEffect(() => {
    const attached = new Set<HTMLElement>();

    const sync = (element: HTMLElement) => {
      element.style.setProperty("--table-scroll-x", `${element.scrollLeft}px`);
    };

    const attach = (element: HTMLElement) => {
      if (attached.has(element)) return;
      attached.add(element);
      sync(element);
      element.addEventListener("scroll", onScroll, { passive: true });
    };

    function onScroll(event: Event) {
      sync(event.currentTarget as HTMLElement);
    }

    const scan = () => {
      document.querySelectorAll<HTMLElement>(SCROLL_WRAPPERS).forEach(attach);
    };

    scan();

    const observer = new MutationObserver(scan);
    observer.observe(document.body, { childList: true, subtree: true });

    const onResize = () => attached.forEach(sync);
    window.addEventListener("resize", onResize, { passive: true });

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", onResize);
      attached.forEach((element) => {
        element.removeEventListener("scroll", onScroll);
        element.style.removeProperty("--table-scroll-x");
      });
    };
  }, []);

  return null;
}
