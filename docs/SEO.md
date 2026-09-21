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
| Server-rendered page content (team, matchup, section pages) | `web/components/seo/*` |
| Deterministic copy generators (team/matchup summaries, comparison rows) | `web/lib/seoContent.ts` |

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

## Server-rendered content strategy

The interactive pages are client components that fetch JSON after hydration. Crawlers and no-JS readers get the important content from server components instead: the `page.tsx` wrapper builds a `seo` prop (React elements) from the same public JSON in `public/data` and hands it to the client component, which renders it in a fixed slot. The server layer supplies the content shell; the client keeps tables, filters, auth and premium gating.

- Before hydration the client's loading branch renders the server content, so the raw HTML contains the H1, summary text, comparison data and links.
- After hydration the client renders its own interactive view and the same server slot content persists (summary above/below, schedule and links below). Content is never duplicated or hidden: each block renders exactly once per state and every block is visible to users.
- Data readers are React `cache()`d and read files from disk at build time; pages are statically generated.

## Content generation rules

- All copy is generated deterministically in `lib/seoContent.ts` from ratings, schedule and PRIME 25 data. No runtime model calls.
- A sentence is omitted when its data is missing (e.g. no offense rank, no venue). Nothing is invented.
- Variation comes from the data: which unit (offense/defense) is stronger, résumé vs rating gaps, rank movement, conference position, next/last game, and which comparison edges exceed a meaningful rank gap. A test in `seo:audit` fails if two pages share a summary.
- Records and ratings count completed FBS-vs-FBS games only; copy says so ("against FBS opponents", "Record (vs FBS)").
- Public data only. Predicted margins, win probabilities and other premium model output never appear in server HTML, metadata, JSON-LD or OG images.
- Dates and kickoff times are formatted in Eastern Time.

## Team page structure (`/team/[slug]`)

H1 "{Full name} Football Analytics" (visible, in the masthead) > rating strip > "{Team} at a Glance" summary (2 paragraphs) > interactive tabs > "{Team} {year} Schedule and Results" table (each row links to the matchup page, opponents link to their profiles) > "Explore {Team} Analytics" links (Ratings, PRIME 25, Predictions, next matchup, conference section of /teams, methodology). Teams with no published rating this season are `noindex, follow` and left out of the sitemap.

## Matchup page structure (`/matchup/[season]/[gameId]`)

Visible H1 ("Prediction & Analytics" for upcoming games, "Game Analytics & Result" for completed) + one summary paragraph (teams, week, date, kickoff, venue/neutral site, final score, ratings context, meaningful edges) > interactive view > server "Team Comparison" table (record, ranks, overall/offense/defense rating, SOR, SOS) > recent form > links to both profiles, Predictions, Ratings, Rankings. Ratings are the pregame snapshot when both teams had one; otherwise the latest snapshot, and the table note says which. FBS-vs-FCS games (no rating or profile for the FCS side) are `noindex, follow` and not in the sitemap.

## Thin-page policy

Index only pages with unique, useful, server-rendered content. If a page is thin, first add real data-derived content; if there is nothing honest to add, use `noindex, follow` and drop it from the sitemap rather than padding. Current decisions: `/learn` (three-link hub) and `/game-history` (query tool with no crawlable series) are noindex; FCS matchups and unrated teams are noindex. Old-season matchups are not in the sitemap. Matchups are not noindexed because of volume: every FBS-vs-FBS game has a distinct comparison.

## Sitemap inclusion and lastmod

Included: home, ratings, rankings, predictions, predictions/performance, teams, network, methodology, upgrade, every rated team, every current-season FBS-vs-FBS matchup. Excluded: advanced, account/auth, articles, template, learn, game-history, FCS matchups, unrated teams, query URLs.

`lastmod` is real or omitted: ratings/predictions/network/team/upcoming matchup pages use the dataset `generatedAt` (each refit changes them); `/rankings` uses the PRIME 25 release time; the performance page uses the track record's `generatedAt`; completed matchups use kickoff time (content is final); `/teams` and static pages omit it.

## Evergreen landing pages

Not created: `/college-football-ratings`, `-strength-of-schedule`, `-strength-of-record`, `-offensive-efficiency`, `-defensive-efficiency`, `-predictions`. Each would duplicate `/ratings` (sortable SOS/SOR/offense/defense columns) or `/predictions`, and aliases/doorways are not allowed. Instead `/ratings` carries a server-rendered explanation plus leader lists for overall, offense, defense, SOR and SOS, and `/predictions` carries the week's featured matchups. Revisit a dedicated page only if it can hold unique data (e.g. a season-long SOS analysis) that `/ratings` does not.

## Social images

`/og` is cached `public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800`. Data ships with each deployment, so the CDN cache is replaced on deploy; cards contain only public data. Platforms cache images by URL on their own schedule.
