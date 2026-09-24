import MatchupLoading from "@/components/MatchupLoading";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";

export default function Loading() {
  return (
    <>
      <SiteHeader tagline="College Football Team Analytics" />
      <SiteNav />
      <MatchupLoading detail="Loading team profile" />
    </>
  );
}
