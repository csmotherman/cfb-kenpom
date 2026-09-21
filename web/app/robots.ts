import type { MetadataRoute } from "next";
import { SITE_URL, absoluteUrl, isProductionDeployment } from "@/lib/seo";

// Public content is fully crawlable. Only account/auth/API/internal routes are excluded. /data/ is deliberately NOT
// blocked: the client-rendered pages load their public JSON from it, and search engines need it to render them.
export default function robots(): MetadataRoute.Robots {
  if (!isProductionDeployment()) {
    return { rules: [{ userAgent: "*", disallow: "/" }] };
  }
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/auth/", "/account", "/login", "/signup", "/template/"],
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
    host: SITE_URL,
  };
}
