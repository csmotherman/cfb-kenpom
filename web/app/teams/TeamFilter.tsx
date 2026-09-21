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
    <>
      <label className="sr-only" htmlFor="teamSearch">Search teams</label>
      <input id="teamSearch" className="site-index__search" type="search" placeholder="Search team" autoComplete="off" value={value} onChange={(e) => apply(e.target.value)} />
    </>
  );
}
