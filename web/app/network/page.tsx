import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import NetworkClient from "./NetworkClient";

const DESCRIPTION =
  "How connected is the college football schedule? PRIME's schedule network shows why opponent-adjusted ratings are less certain early in the season.";

export const metadata = pageMetadata({
  title: "College Football Schedule Network",
  description: DESCRIPTION,
  path: "/network",
});

export default function NetworkPage() {
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/network", name: "College Football Schedule Network", description: DESCRIPTION }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Schedule network", path: "/network" }]),
      ]} />
      <NetworkClient />
    </>
  );
}
