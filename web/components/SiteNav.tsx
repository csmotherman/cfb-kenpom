"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import AuthLink from "@/components/AuthLink";
import { getSearchIndex } from "@/lib/data";
import { isEarlyBetaActive } from "@/lib/earlyBeta";
import { logoUrl, teamCode } from "@/lib/teamCode";
import type { SearchIndexEntry } from "@/lib/types";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/ratings", label: "Ratings" },
  { href: "/rankings", label: "Rankings" },
  { href: "/predictions", label: "Weekly Predictions", premium: true },
  { href: "/advanced", label: "Advanced Stats", premium: true },
];

export default function SiteNav() {
  const pathname = usePathname();
  const router = useRouter();
  const earlyBetaActive = isEarlyBetaActive();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<SearchIndexEntry[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getSearchIndex().then(setIndex).catch(() => {});
  }, []);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setOpen(false);
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

  function onNavClick(e: React.MouseEvent<HTMLAnchorElement>) {
    // Disable Next's automatic route scroll targeting. The sticky navigation
    // should remain at the very top of every primary page after navigation.
    if (
      e.button !== 0 ||
      e.metaKey ||
      e.ctrlKey ||
      e.shiftKey ||
      e.altKey
    ) {
      return;
    }
    window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
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
    <>
      <nav className="site-nav site-nav--unified" aria-label="Primary navigation">
      <div className="container site-nav__inner">
        <Link
          href="/"
          scroll={false}
          onClick={onNavClick}
          className="site-nav__brand"
          aria-label="PRIME Football home"
        >
          <Image src="/brand/prime-header.png" alt="PRIME" width={2172} height={724} priority />
        </Link>

        <div className="site-nav__links">
          {LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                scroll={false}
                onClick={onNavClick}
                className={active ? "active" : undefined}
                aria-current={active ? "page" : undefined}
                data-pro={link.premium || undefined}
                data-beta={link.premium && earlyBetaActive ? "true" : undefined}
              >
                {link.label}
              </Link>
            );
          })}
        </div>

        <div className="site-nav__actions">
          <AuthLink />
          <div className={"site-search" + (open ? " site-search--open" : "")} ref={searchRef}>
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
              <svg className="site-search__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
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
                  <span className="site-search__result-conf">{teamCode(t.team)} · {t.conf}</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      </div>
      </nav>
      <div className="site-nav__mobile-spacer" aria-hidden="true" />
    </>
  );
}
