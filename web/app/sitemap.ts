import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/seo";
import { CONFERENCE_CODES, conferenceSlug } from "@/lib/teamMascots";
import { gameModified } from "@/lib/seoPages";
import { getDataTimestamp, getLatestSnapshot, getLatestYear, getPrimeRankingsServer, getScheduleServer, getTeamDirectory, getTrackRecordTimestamp } from "@/lib/seoData";

type Entry = MetadataRoute.Sitemap[number];

// Public, canonical, indexable URLs only. Excluded on purpose: /advanced and /advanced/exploratory (sign-in required,
// they redirect crawlers to /upgrade), account/auth/login/signup, hidden articles, the design template, API and
// data routes, /learn and /game-history (noindex: link hub / query tool with no content of its own), teams with no published
// rating this season (noindex), every filter/sort/query-string variant, and FBS-vs-FCS matchups (the FCS side has no rating or profile,
// so those pages are noindex and would be near-duplicate thin results).
//
// lastModified is only emitted when a real timestamp exists for that page's content:
//   * team pages, /ratings, /predictions, /network: the ratings dataset's generatedAt (every refit changes them all)
//   * /rankings: the PRIME 25 release time
//   * /predictions/performance: the prediction track record's generatedAt
//   * upcoming matchups: the ratings dataset's generatedAt; completed matchups: kickoff time (their content is final)
//   * /teams, /game-history and hand-written pages: omitted, no reliable modification time exists
//
// The sitemap is assembled from section builders so it can be split with generateSitemaps() and a sitemap index
// if the URL count ever approaches the 50,000-URL limit.
type Stamp = string | undefined;
const later = (a: Stamp, b: Stamp) => (a && b ? (new Date(a) > new Date(b) ? a : b) : a ?? b);
async function staticEntries(generated: Stamp, year: number | null): Promise<Entry[]> {
  const prime = year ? await getPrimeRankingsServer(year) : null;
  const trackRecord = year ? await getTrackRecordTimestamp(year) : null;
  const pages: [string, Entry["changeFrequency"], number, Stamp][] = [
    ["/", "daily", 1.0, later(generated, prime?.releasedAt)],
    ["/ratings", "daily", 0.9, generated],
    ["/rankings", "daily", 0.9, prime?.releasedAt ?? generated],
    ["/top25ratings", "daily", 0.9, generated],
    ["/predictions", "daily", 0.8, generated],
    ["/predictions/performance", "weekly", 0.6, trackRecord ?? generated],
    ["/teams", "weekly", 0.7, undefined],
    ["/network", "weekly", 0.4, generated],
    ["/methodology", "monthly", 0.6, undefined],
    ["/upgrade", "monthly", 0.4, undefined],
  ];
  return pages.map(([path, changeFrequency, priority, lastModified]) => ({ url: absoluteUrl(path), changeFrequency, priority, ...(lastModified ? { lastModified } : {}) }));
}

async function hubEntries(generated: Stamp): Promise<Entry[]> {
  // Week browsing now lives inside /predictions?week=N. Those query variants
  // canonicalize to /predictions and are intentionally excluded from the
  // sitemap. Conference hubs remain standalone because they expose unique
  // conference-level aggregates.
  return CONFERENCE_CODES.map((code): Entry => ({
    url: absoluteUrl(`/conference/${conferenceSlug(code)}`),
    changeFrequency: "weekly",
    priority: 0.6,
    ...(generated ? { lastModified: generated } : {}),
  }));
}

async function teamEntries(lastModified: Stamp, year: number | null): Promise<Entry[]> {
  const [directory, { rows }] = await Promise.all([getTeamDirectory(), year ? getLatestSnapshot(year) : { rows: [] }]);
  const rated = new Set(rows.filter((row) => row.rank !== null).map((row) => row.slug));
  const teams = directory.filter((team) => rated.has(team.slug));
  return teams.map((team) => ({
    url: absoluteUrl(`/team/${team.slug}`),
    changeFrequency: "weekly" as const,
    priority: 0.7,
    ...(lastModified ? { lastModified } : {}),
  }));
}

async function matchupEntries(generated: Stamp, year: number | null): Promise<Entry[]> {
  const schedule = year ? await getScheduleServer(year) : null;
  if (!year || !schedule) return [];
  const [directory, { rows }] = await Promise.all([getTeamDirectory(), getLatestSnapshot(year)]);
  const profiles = new Set(directory.map((team) => team.slug));
  const rated = new Set(rows.filter((row) => row.rank !== null).map((row) => row.slug));
  const indexable = (slug: string) => profiles.has(slug) && rated.has(slug);
  return Object.values(schedule.byWeek)
    .flat()
    .filter((game) => indexable(game.homeSlug) && indexable(game.awaySlug))
    .map((game) => {
      const lastModified = gameModified(game, generated) ?? undefined;
      return {
        url: absoluteUrl(`/matchup/${year}/${game.gameId}`),
        changeFrequency: game.completed ? ("yearly" as const) : ("daily" as const),
        priority: game.completed ? 0.3 : 0.6,
        ...(lastModified ? { lastModified } : {}),
      };
    });
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [generated, year] = await Promise.all([getDataTimestamp().then((v) => v ?? undefined), getLatestYear()]);
  const sections = await Promise.all([staticEntries(generated, year), hubEntries(generated), teamEntries(generated, year), matchupEntries(generated, year)]);
  return sections.flat();
}
