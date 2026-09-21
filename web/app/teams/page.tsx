"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";
import { getMeta, useRankingsSeason } from "@/lib/data";

export default function TeamsPage() {
  const [year, setYear] = useState<string | null>(null);
  const [needle, setNeedle] = useState("");

  useEffect(() => {
    getMeta().then((meta) => setYear(String(meta.rankingsYears[meta.rankingsYears.length - 1])));
  }, []);

  const season = useRankingsSeason(year);
  const rows = useMemo(() => {
    if (!season) return [];
    const last = season.weeks[season.weeks.length - 1];
    return season.byWeek[String(last)] ?? [];
  }, [season]);

  const groups = useMemo(() => {
    const q = needle.trim().toLowerCase();
    const by = new Map<string, typeof rows>();
    rows
      .filter((t) => !q || t.team.toLowerCase().includes(q))
      .forEach((t) => by.set(t.conf || "Independent", [...(by.get(t.conf || "Independent") ?? []), t]));
    return Array.from(by.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [rows, needle]);

  return (
    <>
      <a className="skip-link" href="#teamsContent">Skip to teams</a>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />
      <main id="teamsContent" className="container site-index">
        <header>
          <span className="eyebrow">{year ? `${year} season` : "Teams"}</span>
          <h1>Teams</h1>
          <p>Every FBS team&rsquo;s profile: ratings, game log, and advanced breakdown.</p>
        </header>
        <label className="sr-only" htmlFor="teamSearch">Search teams</label>
        <input id="teamSearch" className="site-index__search" type="search" placeholder="Search team" autoComplete="off" value={needle} onChange={(e) => setNeedle(e.target.value)} />
        {groups.map(([conf, teams]) => (
          <section key={conf} aria-label={conf}>
            <h2>{conf}</h2>
            <div className="site-index__grid">
              {teams.slice().sort((a, b) => a.team.localeCompare(b.team)).map((t) => (
                <Link key={t.slug} href={`/team/${t.slug}`}>{t.team}</Link>
              ))}
            </div>
          </section>
        ))}
        {season && groups.length === 0 ? <p>No team matches &ldquo;{needle}&rdquo;.</p> : null}
      </main>
      <SiteFooter note="Team pages use the same current-season methodology as the Ratings page." />
    </>
  );
}
