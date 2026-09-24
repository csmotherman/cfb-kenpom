import ScrollToTop from "@/components/ScrollToTop";
import { IBM_Plex_Mono, Public_Sans } from "next/font/google";
import localFont from "next/font/local";
import type { Metadata, Viewport } from "next";
import { DEFAULT_DESCRIPTION, DEFAULT_TITLE, SITE_NAME, SITE_URL, THEME_COLOR, TITLE_TEMPLATE, isProductionDeployment, ogImageUrl } from "@/lib/seo";
import Script from "next/script";
import { TooltipProvider } from "@/components/Tooltip";
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
import "@/styles/prime-brand.css";
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
import "@/styles/custom-sample.css";
import "@/styles/game-history.css";
import "@/styles/article.css";
import "@/styles/upgrade.css";
import "@/styles/table-identity-polish.css";
import "@/styles/table-freshness.css";
import "@/styles/ratings-table-polish.css";
import "@/styles/ratings-page-shell.css";
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
/* Final iOS width stabilization: filtered prediction slates must keep every
   matchup card stretched to the viewport instead of shrink-wrapping rows. */
import "@/styles/predictions-mobile-width-fix.css";
/* Exact model-method explainer for the Predictions route. */
import "@/styles/predictions-model.css";
import "@/styles/predictions-performance.css";
import "@/styles/market-odds.css";
import "@/styles/predictions-showcase.css";
import "@/styles/loading-state.css";
import "@/styles/trust-state.css";
import "@/styles/home-rankings.css";
import "@/styles/rankings-prime25.css";
import "@/styles/site-chrome.css";
import "@/styles/seo-content.css";
import "@/styles/teams-directory.css";
import "@/styles/card-template.css";
/* Approved Weekly Predictions reference layer loads last to win the route-specific cascade. */
import "@/styles/predictions-reference.css";

export const viewport: Viewport = {
  themeColor: THEME_COLOR,
};

const production = isProductionDeployment();
const googleVerification = process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION;
const bingVerification = process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: DEFAULT_TITLE, template: TITLE_TEMPLATE },
  description: DEFAULT_DESCRIPTION,
  applicationName: SITE_NAME,
  authors: [{ name: SITE_NAME, url: SITE_URL }],
  creator: SITE_NAME,
  publisher: SITE_NAME,
  category: "sports",
  referrer: "strict-origin-when-cross-origin",
  formatDetection: { email: false, address: false, telephone: false },
  manifest: "/site.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icons/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "en_US",
    url: SITE_URL,
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
    images: [{ url: ogImageUrl(), width: 1200, height: 630, alt: SITE_NAME }],
  },
  twitter: {
    card: "summary_large_image",
    title: DEFAULT_TITLE,
    description: DEFAULT_DESCRIPTION,
    images: [{ url: ogImageUrl(), alt: SITE_NAME }],
  },
  // Only production deployments are indexable; previews and local builds are never crawled into search results.
  robots: production
    ? { index: true, follow: true, googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1, "max-video-preview": -1 } }
    : { index: false, follow: false },
  verification: {
    ...(googleVerification ? { google: googleVerification } : {}),
    ...(bingVerification ? { other: { "msvalidate.01": bingVerification } } : {}),
  },
};

// Self-hosted through next/font: no render-blocking request to Google Fonts, and each face gets a size-adjusted local
// fallback so the swap to the real font does not move text (the family names are wired into --font-* in styles/theme.css).
// Big Shoulders Display is no longer in next/font/google's catalog, so its Latin variable file (700-800, OFL) is bundled locally.
const displayFont = localFont({ src: "./fonts/BigShouldersDisplay-latin.woff2", weight: "700 800", display: "swap", variable: "--font-display-loaded", adjustFontFallback: "Arial" });
const bodyFont = Public_Sans({ subsets: ["latin"], display: "swap", variable: "--font-body-loaded" });
const monoFont = IBM_Plex_Mono({ subsets: ["latin"], weight: ["500", "600", "700"], display: "swap", variable: "--font-mono-loaded" });

const analyticsInit = `window.va=window.va||function(){(window.vaq=window.vaq||[]).push(arguments);};`;
const speedInsightsInit = `window.si=window.si||function(){(window.siq=window.siq||[]).push(arguments);};`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${displayFont.variable} ${bodyFont.variable} ${monoFont.variable}`}>
      <body>
        <ScrollToTop />
        <ExploratoryStickyTableHeader />
        <AdvancedAllColumnsPolicy />
        <TableFreshnessStamp />
        <TooltipProvider>{children}</TooltipProvider>
        <MatchupPredictionPortal />
        <Script id="vercel-analytics-init" strategy="afterInteractive" dangerouslySetInnerHTML={{ __html: analyticsInit }} />
        <Script src="/_vercel/insights/script.js" strategy="afterInteractive" />
        <Script id="vercel-speed-insights-init" strategy="afterInteractive" dangerouslySetInnerHTML={{ __html: speedInsightsInit }} />
        <Script src="/_vercel/speed-insights/script.js" strategy="afterInteractive" />
      </body>
    </html>
  );
}
