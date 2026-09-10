"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isEarlyBetaActive } from "@/lib/earlyBeta";

const LINKS = [
  { href: "/", label: "Ratings" },
  { href: "/this-week", label: "This Week" },
  { href: "/advanced", label: "Advanced", premium: true },
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
            >
              {link.label}
              {link.premium ? (
                <span className="nav-pro-badge">{earlyBetaActive ? "BETA" : "PAID"}</span>
              ) : null}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
