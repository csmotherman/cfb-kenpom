import { noIndexMetadata } from "@/lib/seo";
import ExploratoryClient from "./ExploratoryClient";

export const metadata = noIndexMetadata(
  "College Football Advanced Stats: Exploratory",
  "Exploratory offense-versus-defense matchup research from PRIME.",
);

export default function ExploratoryPage() {
  return <ExploratoryClient />;
}
