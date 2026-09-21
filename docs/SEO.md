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

## Internal link graph (`npm run seo:links`)

`scripts/link-graph.mjs` crawls the server-rendered HTML (no JavaScript) from `/` and reports inbound links, click depth, orphans, dead ends, link-heavy pages and query-string links. Run it against a production build.

| Measure (sitemap URLs) | Before hub pages | After |
| --- | --- | --- |
| Orphans / deeper than 3 clicks | 0 / 0 | 0 / 0 |
| Team pages, inbound links (min/median/max) | 22 / 24 / 28 | 23 / 25 / 29 |
| Matchup pages, inbound links (min/median/max) | 2 / 2 / 4 | 3 / 3 / 6 |
| Matchups at depth 2 (Home > hub > game) | 61 | 105 |
| URLs with two or fewer inbound links | 751 | 1 (`/network`) |

Authority tiers: Tier 1 (`/`, `/ratings`, `/rankings`, `/predictions`, `/teams`) is linked from the nav and footer on every page. Tier 2 (top-ranked teams, current-week matchups) is linked from Home, `/predictions`, `/rankings`, week hubs and conference hubs. Tier 3 (completed and lower-interest matchups) is linked from both teams' schedule tables, the week hub for its week, and the game's own recent-form context; it is never dumped on one page. The busiest outbound page is `/teams` (about 160 links, one per team, which is the directory's job). Every page has a real next step; there are no dead ends.

## Hub pages

- **`/week/[n]`** (current season, weeks with at least 10 rated FBS-vs-FBS games; smaller weeks are `noindex, follow` and not in the sitemap). One URL per week, never per filter, so there is no crawl space. It lists the week's games ordered by PRIME rating, kickoff times or final scores, and links every game. Justification: it is the only crawlable archive of all games in a week, it gives upcoming and completed matchups a second, shallower inbound link, and it answers "college football schedule week N" with PRIME ranks attached, which `/predictions` (client-rendered, one week at a time) does not.
- **`/conference/[slug]`** (SEC, Big Ten, ACC, Big 12, Sun Belt, American Athletic, Mid-American, Mountain West, Conference USA, Pac-12; independents excluded). Unique data beyond a `/ratings` filter: conference average rating and its rank among conferences, non-conference record against rated FBS teams, best offense and defense in the conference, and the next slate of conference games. It also replaces the client-only `/ratings?conf=` state with a crawlable URL. `/teams#conf-*` anchors remain as the directory grouping.
- Breadcrumbs are visible (Home > Teams > Team, Home > Predictions > Matchup, Home > Predictions > Week, Home > Teams > Conference) and generated from the same array as the BreadcrumbList JSON-LD; `seo:audit` fails if they drift. Top-level pages (`/ratings`, `/rankings`) keep their hero designs and rely on JSON-LD only.
- Rejected: per-season archives beyond the current season (older matchups stay reachable through team pages and are not in the sitemap), team-by-team archives, and any filter URLs.

## Crawl-trap audit

No internal link generates a query string except the auth flows (`/login`, `/signup`, `/upgrade?...`, disallowed or noindex). Table state (sort, filter, week, season, conference) lives in React state; `/ratings` reads `?q=` and `?conf=` on the client only and nothing links to them. Every page canonicalizes to its clean path, so `?week=`, `?season=`, `?sort=`, `?utm_*` all return 200 with the clean canonical (verified). Trailing-slash URLs 308 to the clean URL in one hop; `www` 308s to the apex in one hop. `/team/[slug]` uses `dynamicParams = false`, so unknown slugs (and wrong-case slugs) are true 404s. Unknown matchups, other seasons' unknown games and `/week/99` are 404s; `/advanced` is an intentional 307 to `/upgrade` and is not in the sitemap. No redirect chains were found.

## Search-intent map

| Intent | Page | Status |
| --- | --- | --- |
| college football ratings | `/ratings` | satisfied (server intro, leaders, glossary, back to 2014) |
| college football rankings / top 25 | `/rankings` | satisfied (résumé-based, no preseason bias) |
| college football predictions | `/predictions` | satisfied (interactive; slate and week links in HTML) |
| {team} football analytics / stats / ranking | `/team/{slug}` | satisfied for all rated teams |
| {A} vs {B} prediction / preview | `/matchup/{season}/{id}` | satisfied for FBS-vs-FBS games |
| college football schedule week N | `/week/{n}` | satisfied |
| {conference} football rankings / ratings | `/conference/{slug}` | satisfied |
| strength of schedule / strength of record | `/ratings` (columns), team and conference pages | partial: no standalone ranked view |
| offensive / defensive efficiency rankings | `/ratings` (Off/Def columns), conference leaders | partial |
| how accurate are college football predictions | `/predictions/performance` | satisfied |
| how PRIME ratings work | `/methodology` | satisfied |
| head-to-head history | `/game-history` (noindex) | tool only |
| most improved / biggest movers | none | gap |

## Content gaps (recommend only with unique data)

- **Strength-of-schedule and strength-of-record leaderboards**: worth a page only as analysis ("Who has played the hardest schedule?") published weekly with the movement and the reason, not as a re-sort of `/ratings`.
- **Weekly movers**: `rankChange` is published per team per week, so a "Biggest movers" view is real data PRIME has and `/ratings` does not foreground. Best as a recurring dated post (see `docs/SEO-GROWTH.md`), not an evergreen URL.
- **Rating vs résumé gap ("overrated / underrated")**: PRIME uniquely has both a performance rating and SOR; the gap between them is a distinct, linkable data product. Best as a recurring dated post.
- **Team trends over the season**: the data exists per week; needs a chart component and a server-rendered summary before it is worth a page.
- Do not create pages for offensive/defensive efficiency or SOS/SOR as evergreen URLs: they would be filters of `/ratings`.

## Link-worthy data (why each is distinct)

- **PRIME Ratings**: one simultaneous, opponent-adjusted solve for offense and defense per week, built from field-position-adjusted possession efficiency plus play-level success rate and explosiveness, with garbage-time plays excluded and no preseason or prior-season team strength in the 2026 ratings. Weekly history back to 2014 (2020 not published).
- **The PRIME 25**: equal-weighted standardized rating and strength of record; no preseason poll, brand or voter input. That makes it a genuine résumé-vs-performance contrast with the AP Poll.
- **Strength of record / schedule**: SOR is wins above an average FBS team on the same schedule and locations; SOS is average opponent rating. Both are published with national ranks for every team every week.
- **Public prediction track record**: picks are frozen before kickoff and graded in public, including the market benchmark. The published walk-forward backtest (2,481 games) has PRIME slightly behind closing lines, and saying so is what makes the data credible and citable.
- **Team and matchup pages**: stable URLs with ratings, ranks and results in the initial HTML, so they can be cited or embedded in a thread without a login.

## Shareability

Every page has a stable canonical URL and a 1200x630 card (`/og`): team and matchup cards show ratings, ranks and the matchup; hubs reuse the ratings/predictions card. Page titles read as complete headlines when pasted. No share buttons or popups were added; the highest-leverage next step is a "copy this ranking as an image" export on The PRIME 25, tracked in `docs/SEO-GROWTH.md`.

## Titles and descriptions (CTR review)

Titles lead with the search intent and keep the brand only as the `| PRIME` suffix: "College Football Rankings: The PRIME 25", "College Football Ratings: Opponent-Adjusted Team Ratings", "How Accurate Are PRIME's College Football Predictions?", "{Team} Football Analytics", "{Away} vs {Home} Prediction & Analytics", "Week N College Football Schedule & Matchup Analytics", "{Conference} Football Ratings & Team Analytics". Titles never contain changing ranks; numbers live in descriptions. All are unique and under the audit's length limit.

## Feeds (decision: not now)

An Atom feed is only worthwhile if entries are stable, dated, and accumulate. PRIME publishes one PRIME 25 file that is overwritten weekly and no archived releases, so a feed would carry a single constantly-changing entry with no history and no way to give each week a stable ID. Ratings and predictions change continuously, which feeds handle poorly. Revisit if weekly PRIME 25 releases are archived, or when dated analysis posts exist (each post gets an entry).

## IndexNow (decision: supported as an opt-in script)

IndexNow is honored by Bing, Yandex, Naver and Seznam (not Google). PRIME's ratings, rankings, predictions and upcoming-game pages change every week, so push notification is useful for Bing. `npm run indexnow` diffs the live sitemap's `lastmod` values against a local `.indexnow-state.json` and submits only new or newer canonical URLs; the first run refuses to submit the whole site without `--initial`, and `--dry-run` shows the list. It is deliberately not wired into the deploy so it cannot fire on every deployment. Setup: create a key, add `web/public/<key>.txt` containing the key, set `INDEXNOW_KEY`, run after a data refresh once the deploy is live. A weekly refit legitimately changes every team page, so a weekly run of a few hundred URLs is expected.

## Core Web Vitals check (lab, Chrome, 4x CPU throttle for mobile)

Compared with the pre-SEO build (`f0d4a87`): server sections do not change the LCP element on desktop (LCP 0.4-1.0 s) and add 6-45 KB of HTML per page. The new sections sit below the loading state, so they started to cause layout shift when tables filled in; this is fixed by reserving viewport height while data loads (`.seo-reserve` and friends). Mobile CLS: `/ratings` 0.79 (before) to 0.11, `/predictions` 0.23-0.30 to 0.19; `/` (0.20) and `/rankings` (0.68) are unchanged and were already high before any SEO work, caused by client-loaded content in their own layouts. Mobile throttled LCP on `/ratings` measures about 3 s because the largest element is now the real table arriving from a client fetch (before, an early placeholder counted). Recommended follow-up, not done here: fetch the ratings and rankings JSON in the server component and pass it as initial props so the table is in the initial HTML (best LCP and SEO gain, larger refactor). No OG or extra image assets render on pages.

## Indexing-mode verification (re-run)

Built and checked under three configurations: production (`VERCEL_ENV=production`) gives `index, follow`, no `X-Robots-Tag`, robots.txt with `Allow: /` and the sitemap; preview (`VERCEL_ENV=preview`) and local (no env) give `noindex, nofollow`, `X-Robots-Tag: noindex, nofollow` and `Disallow: /`. Canonicals are `https://primecfb.com/...` in all three, and `www` redirects to the apex in one hop.

## Google Search Console launch checklist (manual)

1. Add the **Domain** property `primecfb.com` and verify with the DNS TXT record (covers www and http/https). If using a URL-prefix property instead, set `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION` and redeploy.
2. Sitemaps > submit `https://primecfb.com/sitemap.xml`; confirm status "Success" and the discovered-URL count matches `npm run seo:audit`'s sitemap count.
3. URL Inspection > inspect `/`, `/ratings`, `/rankings`, `/predictions`, `/teams`, one team, one matchup, one week hub, one conference hub. Use "Test live URL" > "View tested page" to confirm the rendered HTML has the summary text and that Google-selected canonical equals the user-declared one. Request indexing for the five Tier 1 URLs only.
4. Pages (page indexing) report: review "Not indexed" reasons. Expected: `noindex` for login/signup/account, FCS matchups, unrated teams, `/learn`, `/game-history`. Investigate "Discovered - currently not indexed" and "Crawled - currently not indexed" on team and matchup pages.
5. Core Web Vitals report: expect no data for a few weeks; check field data afterwards for `/ratings`, `/rankings`, `/`.
6. Settings > Crawl stats: confirm 200s dominate and no spike of 404s or redirects.

## Bing Webmaster Tools checklist (manual)

1. Add the site (import from Search Console, or verify with `NEXT_PUBLIC_BING_SITE_VERIFICATION` or DNS).
2. Sitemaps > submit `https://primecfb.com/sitemap.xml`.
3. URL Inspection on the same nine URLs as above; submit the Tier 1 URLs.
4. Enable IndexNow (see above) and check Site Explorer for excluded URLs.

## Indexing monitoring plan

Record these in a sheet at each checkpoint (from Search Console Pages and Sitemaps reports, Bing Site Explorer, and the Performance report): discovered URLs, crawled URLs, indexed URLs, excluded URLs by reason, impressions, clicks, queries, and which page types (home, ratings, rankings, teams, matchups, week and conference hubs) receive impressions. No target counts are assumed; the trend and the reasons for exclusion are the signal.

| Checkpoint | Check |
| --- | --- |
| 24 hours | Sitemap read successfully; Tier 1 URLs inspected and indexable; no robots or noindex surprises |
| 3 days | Crawl stats show Googlebot fetching team and week/conference hubs; first "Discovered" counts by type |
| 7 days | Indexed count for hubs and Tier 1; first impressions; compare live-inspected canonical vs declared |
| 14 days | Team pages: indexed vs "crawled, not indexed"; if many matchups are excluded as low value, review with `seo:links` and page content, not more pages |
| 30 days | Queries and pages with impressions; which intents in the intent map actually surface; decide on new formats from `docs/SEO-GROWTH.md` |

Re-run `npm run seo:audit` and `npm run seo:links` after every structural change and after each new season starts.
