"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Ratings" },
  { href: "/this-week", label: "This Week" },
  { href: "/advanced", label: "Advanced", pro: true },
];

export default function SiteNav() {
  const pathname = usePathname();
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
              data-pro={link.pro || undefined}
            >
              {link.label}
              {link.pro ? <span className="nav-pro-badge">PRO</span> : null}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
