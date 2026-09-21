import { noIndexMetadata } from "@/lib/seo";
import AdvancedClient from "./AdvancedClient";

// Members-only: signed-out visitors are redirected to /upgrade, so this route is kept out of search results and the sitemap.
export const metadata = noIndexMetadata(
  "College Football Advanced Stats",
  "Advanced college football team statistics including efficiency, success rate, explosiveness and opponent-adjusted performance.",
);

export default function AdvancedPage() {
  return <AdvancedClient />;
}
