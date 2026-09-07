"use client";

import { useEffect } from "react";

function applyGridTitle() {
  let nextTitle = document.title
    .replaceAll("ARA | Adjusted Ratings & Analytics", "GRID | College Football Analytics")
    .replaceAll("Adjusted Ratings & Analytics", "College Football Analytics")
    .replaceAll("CollegeFootballFocus", "GRID")
    .replaceAll("College Football Focus", "GRID")
    .replaceAll("ARA", "GRID");

  nextTitle = nextTitle.replace(/^(\d{4}) College Football Ratings\s*[—-]\s*GRID$/, "$1 RPI Ratings | GRID");
  nextTitle = nextTitle.replace(/^(.+) Football Ratings\s*[—-]\s*GRID$/, "$1 RPI | GRID");

  if (nextTitle !== document.title) document.title = nextTitle;
}

export default function BrandTitleGuard() {
  useEffect(() => {
    applyGridTitle();

    const title = document.querySelector("title");
    if (!title) return;

    const observer = new MutationObserver(applyGridTitle);
    observer.observe(title, { childList: true, subtree: true, characterData: true });

    return () => observer.disconnect();
  }, []);

  return null;
}
