import type { Metadata } from "next";
import { TooltipProvider } from "@/components/Tooltip";
import BrandTitleGuard from "@/components/BrandTitleGuard";
import GridTerminologyGuard from "@/components/GridTerminologyGuard";
import MatchupPredictionPortal from "@/components/MatchupPredictionPortal";
import "@/styles/theme.css";
import "@/styles/ratings.css";
import "@/styles/advanced.css";
import "@/styles/team.css";
import "@/styles/mobile-tables.css";
import "./additions.css";
import "@/styles/mobile-fit.css";
import "@/styles/dense-ratings.css";
import "@/styles/ara-polish.css";
import "@/styles/advanced-table-polish.css";
import "@/styles/grid-brand.css";
import "@/styles/team-logo-align.css";
import "@/styles/auth.css";
import "@/styles/billing.css";
import "@/styles/this-week.css";
import "@/styles/matchup-v2.css";
import "@/styles/matchup-scouting.css";
import "@/styles/matchup-prediction.css";
import "@/styles/team-profile-public.css";
import "@/styles/team-profile-v2.css";
import "@/styles/methodology.css";
import "@/styles/upgrade.css";

export const metadata: Metadata = {
  title: "GRID | College Football Analytics",
  description:
    "GRID provides opponent-adjusted college football RPI ratings, weekly matchup analysis, offensive and defensive analytics, strength of schedule, weekly movement, and historical seasons.",
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
        <GridTerminologyGuard />
        <TooltipProvider>{children}</TooltipProvider>
        <MatchupPredictionPortal />
      </body>
    </html>
  );
}
