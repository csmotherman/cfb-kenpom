import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import { getDataTimestamp } from "@/lib/seoData";
import { PerformanceSeoIntro } from "@/components/seo/SectionSeo";
import PerformanceClient from "./PerformanceClient";

const DESCRIPTION =
  "How accurate are PRIME's college football predictions? Every frozen pick graded against final scores, with winner accuracy, margin error, calibration and a comparison with the betting market.";

export const metadata = pageMetadata({
  title: "How Accurate Are PRIME's College Football Predictions?",
  description: DESCRIPTION,
  path: "/predictions/performance",
  image: { params: { kind: "predictions" }, alt: "PRIME prediction model performance" },
});

export default async function PredictionPerformancePage() {
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/predictions/performance", name: "How Accurate Are PRIME's College Football Predictions?", description: DESCRIPTION, dateModified: await getDataTimestamp() }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Predictions", path: "/predictions" }, { name: "Model performance", path: "/predictions/performance" }]),
      ]} />
      <PerformanceClient seoLede={<PerformanceSeoIntro />} />
    </>
  );
}
