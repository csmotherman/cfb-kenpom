import type { Metadata } from "next";
import { TooltipProvider } from "@/components/Tooltip";
import "@/styles/theme.css";
import "@/styles/ratings.css";
import "@/styles/advanced.css";
import "@/styles/team.css";
import "@/styles/mobile-tables.css";
import "@/styles/mockup-light.css";
import "./additions.css";

export const metadata: Metadata = {
  title: "CollegeFootballFocus",
  description:
    "College football opponent-adjusted team ratings, offense and defense rankings, strength of schedule, weekly movement, and historical seasons.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta name="theme-color" content="#ffffff" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- this is the
            root layout, so (unlike the Pages-Router page this rule targets) it
            already wraps every route; styles/theme.css references these Google
            Font family names literally, matching the original static site */}
        <link
          href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Public+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
