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

type PageProps = { searchParams: Promise<{ week?: string | string[] }> };

export default async function PredictionsPage({ searchParams }: PageProps) {
  const rawWeek = (await searchParams).week;
  const requestedWeek = Array.isArray(rawWeek) ? rawWeek[0] : rawWeek;
  const parsedWeek = requestedWeek && /^\d{1,2}$/.test(requestedWeek) ? Number.parseInt(requestedWeek, 10) : null;
  const initial = parsedWeek === null
    ? await getPredictionsInitial()
    : await getPredictionsInitial((schedule) => schedule.weeks.includes(parsedWeek) ? parsedWeek : schedule.currentWeek);
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
