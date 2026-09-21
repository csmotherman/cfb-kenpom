// Central SEO configuration and helpers. Every page's metadata, canonical URL, social tags and structured data
// comes from here so branding, URLs and title rules live in exactly one place.
import type { Metadata } from "next";

/** The one canonical production origin. Never derived from the request, so previews cannot leak into canonicals. */
export const SITE_URL = "https://primecfb.com";
export const SITE_NAME = "PRIME College Football Analytics";
export const BRAND_SHORT = "PRIME";
export const DEFAULT_TITLE = "PRIME College Football Analytics | Ratings, Rankings & Predictions";
export const DEFAULT_DESCRIPTION =
  "Opponent-adjusted college football ratings, The PRIME 25 rankings, weekly predictions, matchup previews and advanced team analytics.";
export const TITLE_SUFFIX = " | PRIME";
export const TITLE_TEMPLATE = `%s${TITLE_SUFFIX}`;
export const THEME_COLOR = "#142742";
/** Official X/Twitter handle, if one exists. Left null on purpose: nothing in the repo confirms an account. */
export const TWITTER_HANDLE: string | null = null;

export function absoluteUrl(path = "/"): string {
  return `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

/** Production deployments index; previews and local builds never do. Set SITE_ENV=production for non-Vercel hosting. */
export function isProductionDeployment(): boolean {
  return process.env.VERCEL_ENV === "production" || process.env.SITE_ENV === "production";
}

/** Removes a trailing " | PRIME ..." so the root title template never produces "X | PRIME | PRIME". */
export function stripBrandSuffix(title: string): string {
  return title.replace(/\s*[|—-]\s*PRIME( Football| College Football Analytics)?\s*$/i, "").trim();
}

export function fullTitle(title: string): string {
  return `${stripBrandSuffix(title)}${TITLE_SUFFIX}`;
}

export function clampDescription(text: string, max = 160): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max - 1);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 100 ? lastSpace : cut.length).replace(/[,;:\s]+$/, "")}…`;
}

export function ogImageUrl(params: Record<string, string | number> = {}): string {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const qs = query.toString();
  return `${SITE_URL}/og${qs ? `?${qs}` : ""}`;
}

type PageMetaInput = {
  /** Page title WITHOUT the brand suffix; the root template appends " | PRIME". */
  title: string;
  description: string;
  /** Canonical path, e.g. "/ratings". Query strings are never part of it. */
  path: string;
  image?: { params: Record<string, string | number>; alt: string };
  type?: "website" | "article";
  noindex?: boolean;
  /** Use when the title must not receive the template (the homepage). */
  absoluteTitle?: string;
};

export function pageMetadata(input: PageMetaInput): Metadata {
  const title = input.absoluteTitle ?? stripBrandSuffix(input.title);
  const shareTitle = input.absoluteTitle ?? fullTitle(input.title);
  const description = clampDescription(input.description);
  const canonical = absoluteUrl(input.path);
  const image = input.image ?? { params: {}, alt: `${SITE_NAME}` };
  const imageUrl = ogImageUrl(image.params);
  return {
    title: input.absoluteTitle ? { absolute: input.absoluteTitle } : title,
    description,
    alternates: { canonical },
    openGraph: {
      type: input.type ?? "website",
      siteName: SITE_NAME,
      locale: "en_US",
      url: canonical,
      title: shareTitle,
      description,
      images: [{ url: imageUrl, width: 1200, height: 630, alt: image.alt }],
    },
    twitter: {
      card: "summary_large_image",
      title: shareTitle,
      description,
      images: [{ url: imageUrl, alt: image.alt }],
      ...(TWITTER_HANDLE ? { site: TWITTER_HANDLE, creator: TWITTER_HANDLE } : {}),
    },
    ...(input.noindex ? { robots: { index: false, follow: false } } : {}),
  };
}

/** Pages that must stay out of search results (account, auth, internal). */
export function noIndexMetadata(title: string, description: string): Metadata {
  return { title: stripBrandSuffix(title), description: clampDescription(description), robots: { index: false, follow: false } };
}

/* ------------------------------ JSON-LD builders ------------------------------ */

export type JsonLd = Record<string, unknown>;

const ORG_ID = `${SITE_URL}/#organization`;
const WEBSITE_ID = `${SITE_URL}/#website`;

export function organizationJsonLd(): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": ORG_ID,
    name: SITE_NAME,
    alternateName: "PRIME CFB",
    url: SITE_URL,
    logo: absoluteUrl("/icons/icon-512.png"),
  };
}

export function websiteJsonLd(): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": WEBSITE_ID,
    name: SITE_NAME,
    alternateName: "PRIME CFB",
    url: SITE_URL,
    description: DEFAULT_DESCRIPTION,
    inLanguage: "en-US",
    publisher: { "@id": ORG_ID },
  };
}

export function webPageJsonLd(input: { path: string; name: string; description: string; dateModified?: string | null; type?: string }): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": input.type ?? "WebPage",
    "@id": `${absoluteUrl(input.path)}#webpage`,
    url: absoluteUrl(input.path),
    name: input.name,
    description: clampDescription(input.description),
    inLanguage: "en-US",
    isPartOf: { "@id": WEBSITE_ID },
    publisher: { "@id": ORG_ID },
    ...(input.dateModified ? { dateModified: input.dateModified } : {}),
  };
}

export function breadcrumbJsonLd(items: { name: string; path: string }[]): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}

export function itemListJsonLd(input: { name: string; path: string; items: { name: string; path: string }[] }): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: input.name,
    url: absoluteUrl(input.path),
    numberOfItems: input.items.length,
    itemListOrder: "https://schema.org/ItemListOrderAscending",
    itemListElement: input.items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      url: absoluteUrl(item.path),
    })),
  };
}

export function datasetJsonLd(input: {
  path: string;
  name: string;
  description: string;
  dateModified?: string | null;
  temporalCoverage?: string;
  keywords?: string[];
}): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "@id": `${absoluteUrl(input.path)}#dataset`,
    name: input.name,
    description: clampDescription(input.description, 300),
    url: absoluteUrl(input.path),
    creator: { "@id": ORG_ID },
    publisher: { "@id": ORG_ID },
    isAccessibleForFree: true,
    inLanguage: "en-US",
    ...(input.dateModified ? { dateModified: input.dateModified } : {}),
    ...(input.temporalCoverage ? { temporalCoverage: input.temporalCoverage } : {}),
    ...(input.keywords?.length ? { keywords: input.keywords } : {}),
  };
}

export function sportsTeamJsonLd(input: { name: string; path: string; conference?: string | null; logo?: string | null }): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "SportsTeam",
    name: input.name,
    sport: "American football",
    url: absoluteUrl(input.path),
    ...(input.logo ? { logo: input.logo } : {}),
    ...(input.conference ? { memberOf: { "@type": "SportsOrganization", name: input.conference } } : {}),
  };
}

export function sportsEventJsonLd(input: {
  path: string;
  name: string;
  startDate?: string | null;
  homeTeam: string;
  awayTeam: string;
  venue?: string | null;
  description: string;
}): JsonLd {
  return {
    "@context": "https://schema.org",
    "@type": "SportsEvent",
    name: input.name,
    url: absoluteUrl(input.path),
    sport: "American football",
    description: clampDescription(input.description),
    ...(input.startDate ? { startDate: input.startDate } : {}),
    ...(input.venue ? { location: { "@type": "Place", name: input.venue } } : {}),
    homeTeam: { "@type": "SportsTeam", name: input.homeTeam },
    awayTeam: { "@type": "SportsTeam", name: input.awayTeam },
  };
}
