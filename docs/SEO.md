# PRIME SEO & Metadata

Canonical origin: **https://primecfb.com** (apex). `www.primecfb.com` 308-redirects to the apex (`web/next.config.ts`). Make sure the apex is the primary domain in Vercel and `www` is attached to the same project so the redirect can run.

## Architecture

| Concern | Location |
| --- | --- |
| Site constants, title template (`%s \| PRIME`), `pageMetadata()`, `noIndexMetadata()`, JSON-LD builders | `web/lib/seo.ts` |
| Server-side reads of public data (`public/data/*.json`) | `web/lib/seoData.ts` |
| Team / matchup titles, descriptions, JSON-LD | `web/lib/seoPages.ts`, `web/lib/teamMascots.ts` |
| Root metadata, viewport, verification | `web/app/layout.tsx` |
| robots / sitemap / social images | `web/app/robots.ts`, `web/app/sitemap.ts`, `web/app/og/route.tsx` |
| Icons, manifest | `web/public/favicon.ico`, `web/public/icons/*`, `web/public/site.webmanifest` |
| Crawler-visible intros (H1 + internal links) | `web/components/seo/*` |

Interactive pages are a server `page.tsx` (metadata + JSON-LD) wrapping a colocated `*Client.tsx`. Never set `document.title` in client code; the title template appends "| PRIME" once, so page titles must not include the brand.

## Rules

- Metadata and JSON-LD use only public data (team names, records, ratings ranks, schedule, final scores). Never put predicted margins, win probabilities or other premium values in metadata, JSON-LD or OG images.
- JSON-LD is added only where matching content is visible on the page.
- Team pages exist for every team in the search index; matchup pages are statically generated for the current season. Unknown teams/games return 404.
- Hidden pages (login, signup, account, the two articles, template, `/advanced*`) are `noindex` and excluded from the sitemap.

## Indexing by environment

Production is `VERCEL_ENV=production` or `SITE_ENV=production`. Everything else (previews, local builds) gets `noindex`, `X-Robots-Tag: noindex, nofollow`, and `Disallow: /` in robots.txt. Canonicals always point to primecfb.com. `/data/*` JSON is served with `X-Robots-Tag: noindex` but is not blocked in robots.txt so it stays fetchable.

## Sitemap

`/sitemap.xml`: static public pages, every team, every current-season matchup (no query URLs). `lastModified` comes from `meta.generatedAt` only for data-driven pages; static pages carry none.

## Social images

`/og?kind=default|ratings|rankings|predictions|team&slug=…|matchup&season=…&game=…` renders 1200x630 navy/gold/cream cards from public data, with `Cache-Control: public, s-maxage`. The circular PRIME icon is used for favicons/apple-touch; the wordmark is used in OG cards.

## Environment variables

- `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` – Google Search Console token (meta verification).
- `NEXT_PUBLIC_BING_SITE_VERIFICATION` – Bing Webmaster token.
- `SITE_ENV=production` – force production indexing outside Vercel.

## Manual steps

1. Vercel: set the production domain to `primecfb.com`; keep `www` redirecting to it.
2. Add the property in Google Search Console and Bing Webmaster Tools; put the tokens in the env vars above and redeploy (or verify by DNS).
3. Submit `https://primecfb.com/sitemap.xml` in both.
4. Confirm preview deployments show `noindex` (view-source or response headers).
5. If a brand X/Twitter account exists, set `TWITTER_HANDLE` in `web/lib/seo.ts`.
6. Test share cards with the platform debuggers after deploy.

## Verification

`npm run build && VERCEL_ENV=production npm run start`, then `npm run seo:audit` (checks titles, canonicals, OG/Twitter tags, JSON-LD, sitemap URLs return 200, robots, manifest, icons, noindex pages, 404s, OG images).
