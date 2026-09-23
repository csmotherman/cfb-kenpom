import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getDataTimestamp } from "@/lib/seoData";
import { PredictionsSeoContent, PredictionsSeoIntro } from "@/components/seo/SectionSeo";
import { getPredictionsInitial } from "@/lib/initialData";
import PredictionsClient from "./PredictionsClient";

const DESCRIPTION =
  "Weekly college football predictions, projected margins, matchup analytics and data-driven game previews from PRIME, with every pick graded in public.";

export const metadata = pageMetadata({
  title: "College Football Predictions & Matchup Analytics",
  description: DESCRIPTION,
  path: "/predictions",
  image: { params: { kind: "predictions" }, alt: "PRIME weekly college football predictions" },
});

export default async function PredictionsPage() {
  // Weekly Predictions intentionally exposes only the current/upcoming slate.
  // Historical/future weeks are not selectable and ?week= deep links are ignored.
  const initial = await getPredictionsInitial();
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/predictions", name: "College Football Predictions & Matchup Analytics", description: DESCRIPTION, dateModified: await getDataTimestamp() }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Predictions", path: "/predictions" }]),
      ]} />
      <PredictionsClient seo={{ lede: <PredictionsSeoIntro />, content: <PredictionsSeoContent /> }} initial={initial} />
    </>
  );
}
