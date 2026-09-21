"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isEarlyBetaActive } from "@/lib/earlyBeta";

const LINKS = [
  { href: "/", label: "Ratings" },
  { href: "/predictions", label: "Predictions", premium: true },
  { href: "/game-history", label: "Game History" },
  { href: "/advanced", label: "Advanced", premium: true },
  { href: "/teams", label: "Teams" },
  { href: "/learn", label: "Learn" },
];

export default function SiteNav() {
  const pathname = usePathname();
  const earlyBetaActive = isEarlyBetaActive();

  return (
    <nav className="site-nav" aria-label="Primary navigation">
      <div className="container">
        {LINKS.map((link) => {
          const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
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
    </nav>
  );
}
