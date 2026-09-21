"use client";

import { useEffect, useLayoutEffect } from "react";
import { usePathname } from "next/navigation";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * Every page starts at the top. Next only scrolls to the top of a new page in some cases (it skips it when the top of
 * the page is already in view, and the nav links opt out with scroll={false}), and the browser otherwise restores an old
 * scroll offset, so navigating from a long page to a shorter one used to land partway down or at the bottom.
 * This resets the scroll on every route change and on a hard load, instantly (the site's smooth-scroll CSS would
 * otherwise animate it), and leaves in-page #anchor jumps alone.
 */
export default function ScrollToTop() {
  const pathname = usePathname();

  useEffect(() => {
    if ("scrollRestoration" in window.history) window.history.scrollRestoration = "manual";
  }, []);

  useIsoLayoutEffect(() => {
    if (window.location.hash) return;
    const top = () => window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
    top();
    // For a moment after the route changes, undo any scroll the visitor did not ask for (Next scrolling a later
    // segment into view, the browser restoring an old offset, late-mounting content). Real input ends the guard.
    let guarding = true;
    const stop = () => { guarding = false; };
    const onScroll = () => { if (guarding && window.scrollY !== 0) top(); };
    const inputs = ["wheel", "touchstart", "keydown", "mousedown"] as const;
    inputs.forEach((name) => window.addEventListener(name, stop, { passive: true, once: true }));
    window.addEventListener("scroll", onScroll, { passive: true });
    const timer = window.setTimeout(stop, 1500);
    return () => {
      guarding = false;
      window.clearTimeout(timer);
      window.removeEventListener("scroll", onScroll);
      inputs.forEach((name) => window.removeEventListener(name, stop));
    };
  }, [pathname]);

  return null;
}
