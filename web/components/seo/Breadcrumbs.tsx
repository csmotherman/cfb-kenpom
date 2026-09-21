import Link from "next/link";

export type Crumb = { name: string; path: string };

/** Visible breadcrumb trail. Pass the same items to breadcrumbJsonLd() so markup and structured data always match. */
export default function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="seo-crumbs" aria-label="Breadcrumb">
      <ol>
        {items.map((item, i) => (
          <li key={item.path}>
            {i === items.length - 1 ? <span aria-current="page">{item.name}</span> : <Link href={item.path}>{item.name}</Link>}
          </li>
        ))}
      </ol>
    </nav>
  );
}
