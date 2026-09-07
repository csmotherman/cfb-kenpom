"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getSearchIndex } from "@/lib/data";
import { logoUrl, teamCode } from "@/lib/teamCode";
import type { SearchIndexEntry } from "@/lib/types";

export default function SiteHeader({ tagline }: { tagline: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<SearchIndexEntry[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getSearchIndex().then(setIndex).catch(() => {});
  }, []);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const q = query.trim().toLowerCase();
  const matches = q
    ? index
        .filter(
          (t) =>
            t.team.toLowerCase().includes(q) ||
            t.conf.toLowerCase().includes(q) ||
            teamCode(t.team).toLowerCase().includes(q)
        )
        .slice(0, 8)
    : [];

  function goToTeam(t: SearchIndexEntry) {
    setOpen(false);
    setQuery("");
    router.push(`/team/${encodeURIComponent(t.slug)}`);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!matches.length) return;
      setActiveIndex((i) => Math.min(i + 1, matches.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (!matches.length) return;
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = matches[activeIndex >= 0 ? activeIndex : 0];
      if (target) goToTeam(target);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <header className="site-header">
      <div className="site-header__inner">
        <Link href="/" className="logotype" aria-label="GRID — College Football Analytics home">
          <Image
            className="logotype__logo"
            src="/brand/grid-logo.png"
            alt="GRID"
            width={600}
            height={192}
            priority
          />
          <span className="logotype__divider" aria-hidden="true" />
          <span className="logotype__name">College Football Analytics</span>
        </Link>
        <div className="site-header__right">
          <span className="eyebrow site-header__tagline">{tagline}</span>
          <div className={"site-search" + (open ? " site-search--open" : "")} ref={rootRef}>
            <button
              type="button"
              className="site-search__toggle"
              aria-label="Search teams"
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </button>
            <div className="site-search__box">
              <input
                ref={inputRef}
                type="search"
                className="site-search__input"
                placeholder="Search teams…"
                autoComplete="off"
                aria-label="Search teams"
                value={query}
                onFocus={() => setOpen(true)}
                onChange={(e) => {
                  setOpen(true);
                  setQuery(e.target.value);
                  setActiveIndex(-1);
                }}
                onKeyDown={onKeyDown}
              />
              <button type="button" className="site-search__close" aria-label="Close search" onClick={() => setOpen(false)}>
                &times;
              </button>
            </div>
            <div className="site-search__results" hidden={!open || matches.length === 0}>
              {matches.map((t, i) => (
                <a
                  key={t.slug}
                  className={"site-search__result" + (i === activeIndex ? " active" : "")}
                  href={`/team/${encodeURIComponent(t.slug)}`}
                  onClick={(e) => {
                    e.preventDefault();
                    goToTeam(t);
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={logoUrl(t.teamId, 64)} alt="" loading="lazy" decoding="async" />
                  <span className="site-search__result-name">{t.team}</span>
                  <span className="site-search__result-conf">
                    {teamCode(t.team)} · {t.conf}
                  </span>
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
