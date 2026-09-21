import type { NextConfig } from "next";
import { SITE_URL, isProductionDeployment } from "./lib/seo";

const nextConfig: NextConfig = {
  poweredByHeader: false,

  async redirects() {
    return [
      // One canonical host: www -> apex (also enforce at the DNS/Vercel domain level).
      {
        source: "/:path*",
        has: [{ type: "host" as const, value: `www.${new URL(SITE_URL).host}` }],
        destination: `${SITE_URL}/:path*`,
        permanent: true,
      },
      {
        source: "/this-week",
        destination: "/predictions",
        permanent: true,
      },
    ];
  },

  async headers() {
    return [
      // Previews and local builds must never become indexed copies of the site.
      ...(isProductionDeployment() ? [] : [{ source: "/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }] }]),
      // The JSON under /data is fetched by the pages themselves (and must stay crawlable so they can render),
      // but it should not appear in search results as a document.
      { source: "/data/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex" }] },
      {
        source: "/data/meta.json",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
      {
        source: "/data/search-index.json",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
      {
        source: "/data/rankings/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
      {
        source: "/data/advanced/:path*",
        headers: [
          { key: "Cache-Control", value: "private, no-store, max-age=0" },
          { key: "Vary", value: "Cookie" },
        ],
      },
      {
        source: "/data/predictions/:path*",
        headers: [
          { key: "Cache-Control", value: "private, no-store, max-age=0" },
          { key: "Vary", value: "Cookie" },
        ],
      },
      {
        source: "/api/premium/:path*",
        headers: [
          { key: "Cache-Control", value: "private, no-store, max-age=0" },
          { key: "Vary", value: "Cookie" },
        ],
      },
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
