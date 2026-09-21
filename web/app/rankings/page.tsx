import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, datasetJsonLd, itemListJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getLatestYear, getPrimeRankingsServer } from "@/lib/seoData";
import { fullTeamName } from "@/lib/teamMascots";
import { RankingsSeoContent } from "@/components/seo/SectionSeo";
import RankingsClient from "./RankingsClient";

const DESCRIPTION =
  "The PRIME 25 ranks the teams that have earned it through current-season performance, résumé strength and strength of record, updated weekly.";

export const metadata = pageMetadata({
  title: "The PRIME 25 College Football Rankings",
  description: DESCRIPTION,
  path: "/rankings",
  image: { params: { kind: "rankings" }, alt: "The PRIME 25 college football rankings" },
});

export default async function RankingsPage() {
  const year = await getLatestYear();
  const snapshot = year ? await getPrimeRankingsServer(year) : null;
  const items = (snapshot?.teams ?? []).map((team) => ({ name: fullTeamName(team.team), path: `/team/${team.slug}` }));
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/rankings", name: "The PRIME 25 College Football Rankings", description: DESCRIPTION, dateModified: snapshot?.releasedAt }),
        ...(items.length ? [itemListJsonLd({ name: `The PRIME 25, ${snapshot!.season} through Week ${snapshot!.throughWeek}`, path: "/rankings", items })] : []),
        datasetJsonLd({
          path: "/rankings",
          name: "The PRIME 25 college football rankings",
          description: "Weekly top-25 college football rankings from PRIME, combining opponent-adjusted performance with strength of record.",
          dateModified: snapshot?.releasedAt,
          temporalCoverage: snapshot ? String(snapshot.season) : undefined,
          keywords: ["college football rankings", "top 25", "strength of record"],
        }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "The PRIME 25", path: "/rankings" }]),
      ]} />
      <RankingsClient seo={<RankingsSeoContent />} />
    </>
  );
}
