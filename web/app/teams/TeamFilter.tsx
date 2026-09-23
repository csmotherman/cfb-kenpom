"use client";

import { useState } from "react";

/** Progressive enhancement: filters the server-rendered team links in place. Without JS the full list is still there. */
export default function TeamFilter() {
  const [value, setValue] = useState("");

  function apply(next: string) {
    setValue(next);
    const needle = next.trim().toLowerCase();

    document.querySelectorAll<HTMLElement>("[data-team-name]").forEach((el) => {
      el.hidden = Boolean(needle) && !(el.dataset.teamName ?? "").includes(needle);
    });

    document.querySelectorAll<HTMLElement>("[data-team-group]").forEach((group) => {
      group.hidden = group.querySelectorAll("[data-team-name]:not([hidden])").length === 0;
    });
  }

  return (
    <div className="prime-team-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <label className="sr-only" htmlFor="teamSearch">Search teams</label>
      <input
        id="teamSearch"
        type="search"
        placeholder="Search all FBS teams…"
        autoComplete="off"
        value={value}
        onChange={(e) => apply(e.target.value)}
      />
      {value ? (
        <button type="button" aria-label="Clear team search" onClick={() => apply("")}>
          ×
        </button>
      ) : (
        <span>Search</span>
      )}
    </div>
  );
}
