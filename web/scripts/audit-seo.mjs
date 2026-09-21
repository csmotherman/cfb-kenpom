// Audits the rendered SEO output of a running PRIME site (default http://localhost:3111; build/start it with
// VERCEL_ENV=production to check production behaviour). Usage: npm run seo:audit [-- http://localhost:3111]
const ORIGIN = process.argv[2] || "http://localhost:3111";
const PROD = "https://primecfb.com";
const failures = [];
const notes = [];
const fail = (page, msg) => failures.push(`${page}: ${msg}`);

const get = async (path) => {
  const res = await fetch(ORIGIN + path, { redirect: "manual" });
  return { status: res.status, headers: res.headers, text: await res.text() };
};
const attr = (html, re) => (html.match(re) || [])[1];
const metaContent = (html, key, by = "name") =>
  attr(html, new RegExp(`<meta[^>]*${by}="${key}"[^>]*content="([^"]*)"`, "i")) || attr(html, new RegExp(`<meta[^>]*content="([^"]*)"[^>]*${by}="${key}"`, "i"));
const decode = (s) => (s || "").replace(/&amp;/g, "&").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">");

// [path, expected canonical path, must be indexable]
const PAGES = [
  ["/", "/", true],
  ["/ratings", "/ratings", true],
  ["/rankings", "/rankings", true],
  ["/predictions", "/predictions", true],
  ["/predictions/performance", "/predictions/performance", true],
  ["/teams", "/teams", true],
  ["/methodology", "/methodology", true],
  ["/learn", "/learn", true],
  ["/network", "/network", true],
  ["/game-history", "/game-history", true],
  ["/upgrade", "/upgrade", true],
  ["/upgrade?feature=advanced&plan=x", "/upgrade", true],
  ["/team/michigan", "/team/michigan", true],
  ["/team/notre-dame", "/team/notre-dame", true],
];

const titles = new Map();
for (const [path, canonicalPath, indexable] of PAGES) {
  const { status, text } = await get(path);
  if (status !== 200) { fail(path, `status ${status}`); continue; }
  const title = decode(attr(text, /<title>([^<]*)<\/title>/));
  const desc = decode(metaContent(text, "description"));
  const canonical = attr(text, /<link[^>]*rel="canonical"[^>]*href="([^"]*)"/);
  const sameUrl = (a, b) => a.replace(/\/$/, "") === b.replace(/\/$/, "");
  const robots = metaContent(text, "robots") || "";
  if (!title) fail(path, "missing <title>");
  if (/\|\s*PRIME.*\|\s*PRIME/.test(title)) fail(path, `duplicated brand in title: ${title}`);
  if (title.length > 75) fail(path, `title too long (${title.length}): ${title}`);
  if (!desc || desc.length < 60 || desc.length > 165) fail(path, `description length ${desc?.length}: ${desc}`);
  if (!sameUrl(canonical || "", PROD + canonicalPath)) fail(path, `canonical ${canonical} != ${PROD + canonicalPath}`);
  if (/localhost|vercel\.app|127\.0\.0\.1/.test(text.replace(/<script[\s\S]*?<\/script>/g, (m) => (m.includes("ld+json") ? m : "")))) {
    // only flag metadata/head occurrences
    const head = text.split("</head>")[0] || "";
    if (/localhost|vercel\.app|127\.0\.0\.1/.test(head)) fail(path, "head contains a non-production hostname");
  }
  if (indexable && /noindex/i.test(robots)) notes.push(`${path}: noindex (expected only for non-production builds)`);
  for (const key of ["og:title", "og:description", "og:url", "og:image", "og:site_name", "og:type", "og:locale"]) if (!metaContent(text, key, "property")) fail(path, `missing ${key}`);
  if (metaContent(text, "twitter:card") !== "summary_large_image") fail(path, "twitter:card is not summary_large_image");
  for (const key of ["twitter:title", "twitter:description", "twitter:image"]) if (!metaContent(text, key)) fail(path, `missing ${key}`);
  const ogUrl = metaContent(text, "og:url", "property");
  if (!sameUrl(ogUrl || "", PROD + canonicalPath)) fail(path, `og:url ${ogUrl} != canonical`);
  const ld = [...text.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map((m) => m[1]);
  if (!ld.length) fail(path, "no JSON-LD");
  for (const raw of ld) {
    try {
      const parsed = JSON.parse(raw);
      for (const obj of Array.isArray(parsed) ? parsed : [parsed]) {
        if (obj["@context"] !== "https://schema.org") fail(path, "JSON-LD without schema.org @context");
        const urls = JSON.stringify(obj).match(/"(?:url|item|@id)":"([^"]+)"/g) || [];
        for (const u of urls) if (!/"https:\/\/(primecfb\.com|cdn\.collegefootballdata\.com)/.test(u)) fail(path, `JSON-LD non-absolute/non-production URL ${u}`);
      }
    } catch (e) { fail(path, `invalid JSON-LD: ${e.message}`); }
  }
  if (!/rel="icon"/.test(text) || !/rel="apple-touch-icon"/.test(text) || !/rel="manifest"/.test(text)) fail(path, "missing icon/apple-touch-icon/manifest links");
  if (titles.has(title) && !path.includes("?")) fail(path, `duplicate title with ${titles.get(title)}: ${title}`);
  if (!path.includes("?")) titles.set(title, path);
  const h1s = (text.match(/<h1[\s>]/g) || []).length;
  if (h1s !== 1) notes.push(`${path}: ${h1s} <h1> in server HTML`);
  console.log(`ok  ${path.padEnd(34)} ${title}`);
}

// Dynamic pages: unique, sensible titles; matchup metadata must not leak premium prediction data.
const matchup = "/matchup/2026/401858225";
{
  const { status, text } = await get(matchup);
  const title = decode(attr(text, /<title>([^<]*)<\/title>/));
  const desc = decode(metaContent(text, "description"));
  if (status !== 200) fail(matchup, `status ${status}`);
  if (!/ vs .* \| PRIME$/.test(title)) fail(matchup, `unexpected matchup title: ${title}`);
  if (/predicted|win probability|margin of/i.test(desc)) fail(matchup, `description may expose prediction data: ${desc}`);
  if (attr(text, /<link[^>]*rel="canonical"[^>]*href="([^"]*)"/) !== PROD + matchup) fail(matchup, "bad canonical");
  if (!/"@type":"SportsEvent"/.test(text)) fail(matchup, "no SportsEvent JSON-LD");
  const teamLinks = (text.match(/href="\/team\//g) || []).length;
  if (teamLinks < 2) fail(matchup, `expected links to both team pages in server HTML, found ${teamLinks}`);
  console.log(`ok  ${matchup.padEnd(34)} ${title}`);
}

// Status codes
for (const [path, want] of [["/team/not-a-team", 404], ["/matchup/2026/1", 404], ["/nope", 404], ["/advanced", 307], ["/this-week", 308]]) {
  const { status } = await get(path);
  if (status !== want) fail(path, `expected ${want}, got ${status}`);
}

// Noindex surfaces
for (const path of ["/login", "/signup", "/article/waitingonranks", "/template/game-results"]) {
  const { text } = await get(path);
  if (!/noindex/i.test(metaContent(text, "robots") || "")) fail(path, "should be noindex");
}

// robots.txt / manifest / sitemap
const robots = await get("/robots.txt");
if (!/Sitemap: https:\/\/primecfb\.com\/sitemap\.xml/.test(robots.text)) fail("/robots.txt", "missing production sitemap line (build with VERCEL_ENV=production)");
if (/Disallow: \/\s*$/m.test(robots.text)) notes.push("/robots.txt disallows everything (expected only for non-production builds)");
for (const path of ["/api/", "/auth/", "/account"]) if (!robots.text.includes(`Disallow: ${path}`)) fail("/robots.txt", `does not disallow ${path}`);
if (/Disallow: \/(data|_next)/.test(robots.text)) fail("/robots.txt", "must not block /data or /_next");
const manifest = await get("/site.webmanifest");
try { const m = JSON.parse(manifest.text); if (m.short_name !== "PRIME" || !m.icons?.length) fail("/site.webmanifest", "incomplete"); } catch { fail("/site.webmanifest", "invalid JSON"); }
for (const icon of ["/favicon.ico", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png", "/icons/favicon-32x32.png"]) {
  const r = await fetch(ORIGIN + icon); if (!r.ok) fail(icon, `status ${r.status}`);
}

const sitemap = await get("/sitemap.xml");
const locs = [...sitemap.text.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
if (new Set(locs).size !== locs.length) fail("/sitemap.xml", "duplicate URLs");
if (locs.some((u) => !u.startsWith(PROD + "/") || /[?#]/.test(u))) fail("/sitemap.xml", "non-canonical URL in sitemap");
if (locs.some((u) => /\/(advanced|account|login|signup|api|auth|article|template)/.test(u))) fail("/sitemap.xml", "contains a non-indexable route");
console.log(`sitemap: ${locs.length} URLs`);
let bad = 0;
for (let i = 0; i < locs.length; i += 25) {
  await Promise.all(locs.slice(i, i + 25).map(async (u) => {
    const r = await fetch(ORIGIN + u.slice(PROD.length), { redirect: "manual" });
    if (r.status !== 200) { bad++; if (bad <= 10) fail(u, `sitemap URL returned ${r.status}`); }
  }));
}
console.log(`sitemap URLs returning 200: ${locs.length - bad}/${locs.length}`);

// OG image endpoint
for (const q of ["", "?kind=ratings", "?kind=rankings", "?kind=predictions", "?kind=team&slug=michigan", "?kind=matchup&season=2026&game=401858225"]) {
  const r = await fetch(`${ORIGIN}/og${q}`);
  const type = r.headers.get("content-type");
  const size = (await r.arrayBuffer()).byteLength;
  if (!r.ok || !/image\/png/.test(type || "") || size < 5000 || size > 400000) fail(`/og${q}`, `status ${r.status} ${type} ${size}B`);
  else console.log(`ok  /og${q.padEnd(44)} ${type} ${Math.round(size / 1024)} KB`);
}

notes.forEach((n) => console.log(`note: ${n}`));
if (failures.length) { console.error(`\n${failures.length} SEO audit failure(s):`); failures.forEach((f) => console.error(" - " + f)); process.exit(1); }
console.log("\nSEO audit passed");
