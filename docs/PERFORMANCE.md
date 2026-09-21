# PRIME performance: architecture, budgets and measurements

## Server-first data

The public data files (`web/public/data/*.json`) change only when a new build ships, so the interactive pages read them on the server and hand the current-season slice to their client component as `initial` props (`web/lib/initialData.ts`). The client renders that data on the first pass, so the first HTML already contains the table or cards, and it seeds the shared cache in `web/lib/data.ts` (`seedMeta`, `seedRankingsSeason`, `seedProjectionSeason`, `seedCfpResultsSeason`) so nothing is fetched twice. Seeding is client-only and never overwrites cached data. Other seasons and weeks still load on demand.

| Page | Server provides | Client still does |
| --- | --- | --- |
| `/ratings` | current season (all weeks, schedule week applied), trimmed projection, CFP result | sorting, filtering, season/week switching, other seasons |
| `/rankings` | PRIME 25 snapshot | nothing to fetch |
| `/` | precomputed card data (top 5, featured game, best offense/defense/SOS, riser, PRIME 25) | nothing to fetch |
| `/predictions` | current week's games, its pregame ratings, its market lines, the performance strip | gated pick columns (`/api/premium/...`), preseason-power table; loads the full season the first time the week picker is used |

Premium values (picks, margins, win probabilities) are never read on the server. The predictions page still asks `/api/premium/predictions/...` from the browser and shows the unlock state as before. Pages stay statically generated; freshness comes from a new deployment (and the existing `TableFreshnessStamp` poll).

## Layout stability

Root causes found with `npm run cwv` (attribution of each shift to a DOM node):

- `/rankings` (0.68 mobile): `section.prime25-rest` and `section.prime25-full-rankings` were empty until a client fetch filled them (about 380 px of content inserted above the footer). Fixed by rendering the snapshot on the server.
- `/` (0.20 mobile): `article.prime-home-matchup` and the rankings panel changed height when ratings, schedule and PRIME 25 JSON arrived (0.16), plus a font-swap shift in the hero (0.04). Fixed with server-rendered card data and self-hosted fonts with size-adjusted fallbacks.
- `/predictions` (0.19 mobile): the "Prediction Performance" strip appeared above the toolbar after a fetch (about 210 px), then the toolbar and table swapped in. Fixed by computing the strip and the current week on the server.
- `/ratings` (0.11 mobile): the Projection column and its values arrived after the table (geometry change). Fixed by including projection in the initial data.

No blanket `min-height` is used anywhere; the reserve rules added earlier were removed once the data was server-rendered. Team logos (`cdn.collegefootballdata.com/logos/*`) get `aspect-ratio: 1 / 1` globally in `styles/theme.css`, so their box exists before the image loads. Fonts moved from a render-blocking Google Fonts stylesheet to `next/font` (Public Sans and IBM Plex Mono from `next/font/google`; Big Shoulders Display bundled as a local woff2 because it is no longer in the Google catalog), each with a size-adjusted fallback. Typography is unchanged.

## Budgets

Lab, production build, Chrome, median of 3. Not a guarantee for field data.

| | Desktop | Mobile (390 px, 4x CPU) |
| --- | --- | --- |
| LCP | < 1.5 s | < 2.5 s |
| CLS | < 0.05 | < 0.10 |
| Data/API requests before first paint | 0 blocking | 0 blocking |

Run `npm run build && npm run start`, then `node scripts/cwv.mjs [--paths=/ratings] [--verbose]` (prints LCP element, CLS, the DOM nodes behind each shift with before/after rects, and the data requests). Run `npm run seo:audit` and `npm run seo:links` after any structural change.

## Measurements (before, after)

Mobile: `/` LCP 1.24 s to 1.1-1.5 s (noisy, no real change), CLS 0.199 to 0.000; `/ratings` LCP 2.91 s to 0.90 s, CLS 0.114 to 0.000; `/rankings` LCP 1.13 s to 1.1-1.4 s (noisy), CLS 0.683 to 0.000; `/predictions` LCP 0.97 s to 1.2 s (within noise), CLS 0.194 to 0.017.
Desktop: `/` LCP 0.75 s to 0.65-1.0 s, CLS 0.031 to 0.000; `/ratings` 0.56 s to 0.50 s, CLS 0.042 to 0.000; `/rankings` 0.87 s to 0.54 s, CLS 0.055 to 0.000; `/predictions` 0.74 s to 0.42 s, CLS 0.062 to 0.000.
Data/API requests on load: `/` 6 to 2 (search index and freshness check), `/ratings` 7 to 2, `/rankings` 3 to 2, `/predictions` 9 to 4 (the other three load only when the week picker is used).
HTML: `/` 29 KB to 66 KB, `/ratings` 49 KB to 409 KB (52 KB gzip), `/rankings` 35 KB to 147 KB, `/predictions` 37 KB to 257 KB (33 KB gzip). The ratings HTML now includes the 138-row table and the serialized season; the browser previously downloaded 103 KB of rankings, 378 KB of schedule and 57 KB of projection JSON as separate requests. Remaining opportunity: `/team/[slug]` makes about 30 data requests on load (not in scope here).
