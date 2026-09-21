import JsonLd from "@/components/JsonLd";
import { DEFAULT_DESCRIPTION, DEFAULT_TITLE, organizationJsonLd, pageMetadata, websiteJsonLd } from "@/lib/seo";
import { HomeSeoContent } from "@/components/seo/SectionSeo";
import { getHomeInitial } from "@/lib/initialData";
import HomeClient from "./HomeClient";

export const metadata = pageMetadata({
  title: DEFAULT_TITLE,
  absoluteTitle: DEFAULT_TITLE,
  description: DEFAULT_DESCRIPTION,
  path: "/",
  image: { params: {}, alt: "PRIME College Football Analytics: ratings, rankings and predictions" },
});

export default async function HomePage() {
  const initial = await getHomeInitial();
  return (
    <>
      <JsonLd data={[websiteJsonLd(), organizationJsonLd()]} />
      <HomeClient seo={<HomeSeoContent />} initial={initial} />
    </>
  );
}
