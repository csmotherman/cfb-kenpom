"use client";

import { useEffect } from "react";

function applyAraTitle() {
  const nextTitle = document.title
    .replaceAll("CollegeFootballFocus", "ARA")
    .replaceAll("College Football Focus", "ARA");

  if (nextTitle !== document.title) document.title = nextTitle;
}

export default function BrandTitleGuard() {
  useEffect(() => {
    applyAraTitle();

    const title = document.querySelector("title");
    if (!title) return;

    const observer = new MutationObserver(applyAraTitle);
    observer.observe(title, { childList: true, subtree: true, characterData: true });

    return () => observer.disconnect();
  }, []);

  return null;
}
