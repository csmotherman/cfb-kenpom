"use client";

import { useEffect } from "react";

function normalizeLeilaTitle() {
  let nextTitle = document.title
    .replaceAll("ARA | Adjusted Ratings & Analytics", "LEILA Ratings | College Football Analytics")
    .replaceAll("Adjusted Ratings & Analytics", "College Football Analytics")
    .replaceAll("CollegeFootballFocus", "LEILA Ratings")
    .replaceAll("College Football Focus", "LEILA Ratings")
    .replaceAll("ARA", "LEILA Ratings");

  nextTitle = nextTitle.replace(/^(\d{4}) College Football Ratings\s*[—-]\s*LEILA Ratings$/, "$1 AdjNet Ratings | LEILA Ratings");
  nextTitle = nextTitle.replace(/^(.+) Football Ratings\s*[—-]\s*LEILA Ratings$/, "$1 AdjNet | LEILA Ratings");

  if (nextTitle !== document.title) document.title = nextTitle;
}

export default function BrandTitleGuard() {
  useEffect(() => {
    normalizeLeilaTitle();

    const title = document.querySelector("title");
    if (!title) return;

    const observer = new MutationObserver(normalizeLeilaTitle);
    observer.observe(title, { childList: true, subtree: true, characterData: true });

    return () => observer.disconnect();
  }, []);

  return null;
}
