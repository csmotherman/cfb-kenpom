import type { Metadata } from "next";
import { TooltipProvider } from "@/components/Tooltip";
import BrandTitleGuard from "@/components/BrandTitleGuard";
import MatchupPredictionPortal from "@/components/MatchupPredictionPortal";
import ExploratoryStickyTableHeader from "@/components/ExploratoryStickyTableHeader";
import AdvancedAllColumnsPolicy from "@/components/AdvancedAllColumnsPolicy";
import TableFreshnessStamp from "@/components/TableFreshnessStamp";
import "@/styles/theme.css";
import "@/styles/ratings.css";
import "@/styles/advanced.css";
import "@/styles/team.css";
import "./additions.css";
import "@/styles/dense-ratings.css";
import "@/styles/ara-polish.css";
import "@/styles/advanced-table-polish.css";
import "@/styles/leila-brand.css";
import "@/styles/team-logo-align.css";
import "@/styles/auth.css";
import "@/styles/billing.css";
import "@/styles/this-week.css";
import "@/styles/matchup-v2.css";
import "@/styles/matchup-scouting.css";
import "@/styles/matchup-prediction.css";
import "@/styles/matchup-edges.css";
import "@/styles/team-profile-public.css";
import "@/styles/team-profile-v2.css";
import "@/styles/methodology.css";
import "@/styles/network.css";
import "@/styles/game-log.css";
import "@/styles/article.css";
import "@/styles/upgrade.css";
import "@/styles/table-identity-polish.css";
import "@/styles/table-freshness.css";
import "@/styles/ratings-table-polish.css";
import "@/styles/exploratory.css";
import "@/styles/exploratory-desktop-table.css";
import "@/styles/exploratory-modal-wide.css";
import "@/styles/cfp-badge.css";
/* Canonical mobile table rules intentionally load last so page-specific
   responsive CSS cannot override the native sticky identity rails. */
import "@/styles/mobile-table-native-sticky.css";
/* Final table-policy overrides load after the canonical sticky system. */
import "@/styles/table-behavior-fixes.css";
/* Predictions intentionally loads last because its mobile card layout replaces
   the generic horizontally-scrolling table treatment on this route only. */
import "@/styles/predictions-v2.css";
import "@/styles/predictions-mobile-reset.css";

export const metadata: Metadata = {
  title: "LEILA Ratings | College Football Analytics",
  description:
    "LEILA Ratings provides opponent-adjusted college football ratings, weekly matchup analysis, offensive and defensive analytics, strength of schedule, weekly movement, and historical seasons.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="theme-color" content="#142742" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- this is the
            root layout, so (unlike the Pages-Router page this rule targets) it
            already wraps every route; styles/theme.css references these Google
            Font family names literally, matching the existing design system */}
        <link
          href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Public+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <BrandTitleGuard />
        <ExploratoryStickyTableHeader />
        <AdvancedAllColumnsPolicy />
        <TableFreshnessStamp />
        <TooltipProvider>{children}</TooltipProvider>
        <MatchupPredictionPortal />
      </body>
    </html>
  );
}
