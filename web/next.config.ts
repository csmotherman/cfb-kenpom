import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  poweredByHeader: false,

  // The protected API routes read the published JSON from disk after checking
  // the signed-in user's Supabase entitlement. Include those files in the
  // serverless bundles even though their filenames are selected dynamically.
  outputFileTracingIncludes: {
    "/api/premium/advanced/*": ["./public/data/advanced/**/*.json"],
    "/api/premium/predictions/*": ["./public/data/predictions/**/*.json"],
  },

  async headers() {
    return [
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
