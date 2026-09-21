import Link from "next/link";
import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import SiteFooter from "@/components/SiteFooter";

export const metadata = pageMetadata({
  title: "Learn How PRIME College Football Ratings Work",
  description: "How PRIME's ratings and predictions work, how they are graded, and how much to trust them each week of the season.",
  path: "/learn",
  // A three-link hub with no content of its own; the pages it links to are the ones worth indexing.
  noindex: true,
  follow: true,
});

const ITEMS = [
  { href: "/methodology", title: "Methodology", text: "What APR, SOS, SOR and the advanced metrics mean, and how they are built." },
  { href: "/predictions/performance", title: "Model performance", text: "Every published pick graded, including the misses." },
  { href: "/network", title: "Schedule network", text: "How connected the season's schedule is, and why early ratings are less certain." },
];

export default function LearnPage() {
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/learn", name: "Learn How PRIME College Football Ratings Work", description: "How PRIME's ratings and predictions work, how they are graded, and how much to trust them each week of the season.", type: "CollectionPage" }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Learn", path: "/learn" }]),
      ]} />
      <a className="skip-link" href="#learnContent">Skip to content</a>
      <SiteHeader tagline="Transparent College Football Analytics" />
      <SiteNav />
      <main id="learnContent" className="container site-index">
        <header>
          <span className="eyebrow">Learn</span>
          <h1>Understand the numbers</h1>
          <p>Definitions, grading and the reasoning behind PRIME&rsquo;s ratings and predictions.</p>
        </header>
        <div className="site-index__cards">
          {ITEMS.map((item) => (
            <Link key={item.href} href={item.href} className="site-index__card">
              <strong>{item.title}</strong>
              <span>{item.text}</span>
            </Link>
          ))}
        </div>
      </main>
      <SiteFooter note="PRIME Football favors explicit definitions over invented completeness." />
    </>
  );
}
