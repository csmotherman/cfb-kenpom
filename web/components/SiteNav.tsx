"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isEarlyBetaActive } from "@/lib/earlyBeta";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/ratings", label: "Ratings" },
  { href: "/rankings", label: "Rankings" },
  { href: "/predictions", label: "Weekly Predictions", premium: true },
  { href: "/advanced", label: "Advanced Stats", premium: true },
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
