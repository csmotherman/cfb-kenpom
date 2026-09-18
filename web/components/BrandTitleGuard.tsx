"use client";

import { useEffect } from "react";

function normalizePrimeTitle() {
  let nextTitle = document.title
    .replaceAll("ARA | Adjusted Ratings & Analytics", "PRIME Football | College Football Analytics")
    .replaceAll("Adjusted Ratings & Analytics", "College Football Analytics")
    .replaceAll("CollegeFootballFocus", "PRIME Football")
    .replaceAll("College Football Focus", "PRIME Football")
    .replaceAll("ARA", "PRIME Football");

  nextTitle = nextTitle.replace(/^(\d{4}) College Football Ratings\s*[—-]\s*PRIME Football$/, "$1 Adj. Net Ratings | PRIME Football");
  nextTitle = nextTitle.replace(/^(.+) Football Ratings\s*[—-]\s*PRIME Football$/, "$1 Adj. Net | PRIME Football");

  if (nextTitle !== document.title) document.title = nextTitle;
}

export default function BrandTitleGuard() {
  useEffect(() => {
    normalizePrimeTitle();

    const title = document.querySelector("title");
    if (!title) return;

    const observer = new MutationObserver(normalizePrimeTitle);
    observer.observe(title, { childList: true, subtree: true, characterData: true });

    return () => observer.disconnect();
  }, []);

  return null;
}
