import JsonLd from "@/components/JsonLd";
import { breadcrumbJsonLd, pageMetadata, webPageJsonLd } from "@/lib/seo";
import GameHistoryClient from "./GameHistoryClient";

const DESCRIPTION = "Search a decade of college football results and head-to-head series between any two FBS teams.";

export const metadata = pageMetadata({
  title: "College Football Game History & Head-to-Head Series",
  description: DESCRIPTION,
  path: "/game-history",
});

export default function GameHistoryPage() {
  return (
    <>
      <JsonLd data={[
        webPageJsonLd({ path: "/game-history", name: "College Football Game History", description: DESCRIPTION }),
        breadcrumbJsonLd([{ name: "Home", path: "/" }, { name: "Game history", path: "/game-history" }]),
      ]} />
      <GameHistoryClient />
    </>
  );
}
