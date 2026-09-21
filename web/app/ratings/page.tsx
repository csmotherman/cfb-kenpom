import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, datasetJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getDataTimestamp, getSiteMeta } from "@/lib/seoData";
import { RatingsSeoContent } from "@/components/seo/SectionSeo";
import { getRatingsInitial } from "@/lib/initialData";
import RatingsClient from "./RatingsClient";

const DESCRIPTION =
  "Opponent-adjusted college football team ratings with overall, offensive and defensive performance, strength of schedule and strength of record for the current season and back to 2014.";

export const metadata = pageMetadata({
  title: "College Football Ratings: Opponent-Adjusted Team Ratings",
  description: DESCRIPTION,
  path: "/ratings",
  image: { params: { kind: "ratings" }, alt: "PRIME college football team ratings" },
});

export default async function RatingsPage() {
  const [modified, meta, initial] = await Promise.all([getDataTimestamp(), getSiteMeta(), getRatingsInitial()]);
  const years = meta?.rankingsYears ?? [];
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/ratings", name: "College Football Ratings: Opponent-Adjusted Team Ratings", description: DESCRIPTION, dateModified: modified }),
        datasetJsonLd({
          path: "/ratings",
          name: "PRIME opponent-adjusted college football team ratings",
          description: "Weekly opponent-adjusted offensive, defensive and overall team ratings for FBS college football, with strength of schedule and strength of record, published by PRIME.",
          dateModified: modified,
          temporalCoverage: years.length ? `${Math.min(...years)}/${Math.max(...years)}` : undefined,
          keywords: ["college football ratings", "opponent-adjusted ratings", "strength of schedule", "strength of record"],
        }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Ratings", path: "/ratings" }]),
      ]} />
      <RatingsClient seo={<RatingsSeoContent />} initial={initial} />
    </>
  );
}
