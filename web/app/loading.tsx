import MatchupLoading from "@/components/MatchupLoading";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";

export default function Loading() {
  return (
    <>
      <SiteHeader tagline="PRIME" />
      <SiteNav />
      <MatchupLoading detail="Loading PRIME data" />
    </>
  );
}
