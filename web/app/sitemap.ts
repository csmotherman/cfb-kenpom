import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/seo";
import { getDataTimestamp, getLatestYear, getScheduleServer, getTeamDirectory } from "@/lib/seoData";

type Entry = MetadataRoute.Sitemap[number];

// Public, canonical, indexable URLs only. Excluded on purpose: /advanced and /advanced/exploratory (sign-in required,
// they redirect crawlers to /upgrade), account/auth/login/signup, hidden articles, the design template, API and
// data routes, and every filter/sort/query-string variant.
//
// lastModified comes from the dataset's real generatedAt timestamp (data-driven pages) and is omitted for
// hand-written pages, where no real modification time is available at build time.
//
// The sitemap is assembled from section builders so it can be split with generateSitemaps() and a sitemap index
// if the URL count ever approaches the 50,000-URL limit.
async function staticEntries(lastModified: string | undefined): Promise<Entry[]> {
  const dataPages: [string, Entry["changeFrequency"], number][] = [
    ["/", "daily", 1.0],
    ["/ratings", "daily", 0.9],
    ["/rankings", "daily", 0.9],
    ["/predictions", "daily", 0.8],
    ["/predictions/performance", "weekly", 0.6],
    ["/teams", "weekly", 0.7],
    ["/network", "weekly", 0.4],
    ["/game-history", "monthly", 0.4],
  ];
  const docPages: [string, Entry["changeFrequency"], number][] = [
    ["/methodology", "monthly", 0.6],
    ["/learn", "monthly", 0.5],
    ["/upgrade", "monthly", 0.4],
  ];
  return [
    ...dataPages.map(([path, changeFrequency, priority]) => ({ url: absoluteUrl(path), changeFrequency, priority, ...(lastModified ? { lastModified } : {}) })),
    ...docPages.map(([path, changeFrequency, priority]) => ({ url: absoluteUrl(path), changeFrequency, priority })),
  ];
}

async function teamEntries(lastModified: string | undefined): Promise<Entry[]> {
  const teams = await getTeamDirectory();
  return teams.map((team) => ({
    url: absoluteUrl(`/team/${team.slug}`),
    changeFrequency: "weekly" as const,
    priority: 0.7,
    ...(lastModified ? { lastModified } : {}),
  }));
}

async function matchupEntries(lastModified: string | undefined): Promise<Entry[]> {
  const year = await getLatestYear();
  const schedule = year ? await getScheduleServer(year) : null;
  if (!year || !schedule) return [];
  return Object.values(schedule.byWeek)
    .flat()
    .map((game) => ({
      url: absoluteUrl(`/matchup/${year}/${game.gameId}`),
      changeFrequency: game.completed ? ("yearly" as const) : ("daily" as const),
      priority: game.completed ? 0.3 : 0.6,
      ...(lastModified ? { lastModified } : {}),
    }));
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const lastModified = (await getDataTimestamp()) ?? undefined;
  const sections = await Promise.all([staticEntries(lastModified), teamEntries(lastModified), matchupEntries(lastModified)]);
  return sections.flat();
}
