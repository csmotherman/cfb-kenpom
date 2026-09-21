import JsonLd from "@/components/JsonLd";
import { DEFAULT_DESCRIPTION, DEFAULT_TITLE, organizationJsonLd, pageMetadata, websiteJsonLd } from "@/lib/seo";
import HomeClient from "./HomeClient";

export const metadata = pageMetadata({
  title: DEFAULT_TITLE,
  absoluteTitle: DEFAULT_TITLE,
  description: DEFAULT_DESCRIPTION,
  path: "/",
  image: { params: {}, alt: "PRIME College Football Analytics: ratings, rankings and predictions" },
});

export default function HomePage() {
  return (
    <>
      <JsonLd data={[websiteJsonLd(), organizationJsonLd()]} />
      <HomeClient />
    </>
  );
}
