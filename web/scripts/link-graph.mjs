// Crawls the server-rendered HTML of a running PRIME build (no JavaScript) and reports the internal link graph:
// inbound links per URL, click depth from the homepage, orphans, dead ends and link-heavy pages.
// Usage: npm run seo:links [-- http://localhost:3111]
const ORIGIN = process.argv[2] || "http://localhost:3111";
const PROD = "https://primecfb.com";
const get = async (path) => { const r = await fetch(ORIGIN + path, { redirect: "manual" }); return { status: r.status, text: (await r.text()).replace(/<!-- -->/g, "") }; };
const norm = (href) => {
  if (!href || /^(mailto:|tel:|javascript:|#)/.test(href)) return null;
  let url;
  try { url = new URL(href, PROD + "/"); } catch { return null; }
  if (url.origin !== PROD) return null;
  const path = url.pathname.replace(/\/$/, "") || "/";
  return { path, query: url.search };
};
const sitemap = (await get("/sitemap.xml")).text;
const sitemapPaths = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => norm(m[1]).path);
const pages = new Map(); // path -> {out:Set, status, queryLinks:[]}
const queue = ["/"];
const seen = new Set(queue);
const depth = new Map([["/", 0]]);
while (queue.length) {
  const batch = queue.splice(0, 20);
  await Promise.all(batch.map(async (path) => {
    const { status, text } = await get(path);
    const body = text.split("<body")[1] || "";
    const main = body.replace(/<script[\s\S]*?<\/script>/g, "");
    const out = new Set();
    const queryLinks = [];
    for (const m of main.matchAll(/<a [^>]*href="([^"]+)"/g)) {
      const link = norm(m[1].replace(/&amp;/g, "&"));
      if (!link) continue;
      if (link.query) queryLinks.push(link.path + link.query);
      out.add(link.path);
    }
    out.delete(path);
    pages.set(path, { status, out, queryLinks, rawCount: [...main.matchAll(/<a [^>]*href=/g)].length });
    if (status !== 200) return;
    for (const l of out) {
      if (!seen.has(l) && !/^\/(api|auth|_next|data|og)/.test(l)) { seen.add(l); depth.set(l, depth.get(path) + 1); queue.push(l); }
    }
  }));
}
const inbound = new Map();
for (const p of pages.values()) for (const l of p.out) inbound.set(l, (inbound.get(l) || 0) + 1);
const kind = (p) => (p.startsWith("/team/") ? "team" : p.startsWith("/matchup/") ? "matchup" : "other");
const summarize = (label, paths) => {
  if (!paths.length) return;
  const counts = paths.map((p) => inbound.get(p) || 0).sort((a, b) => a - b);
  const depths = paths.map((p) => depth.get(p) ?? Infinity);
  const dist = {};
  for (const d of depths) dist[d] = (dist[d] || 0) + 1;
  console.log(`${label.padEnd(14)} n=${paths.length} inbound min/median/max=${counts[0]}/${counts[Math.floor(counts.length / 2)]}/${counts[counts.length - 1]} depth=${JSON.stringify(dist)}`);
};
console.log(`crawled ${pages.size} URLs by following server-rendered links from /`);
for (const k of ["team", "matchup", "other"]) summarize(k, sitemapPaths.filter((p) => kind(p) === k));
const orphans = sitemapPaths.filter((p) => !depth.has(p));
console.log(`sitemap URLs unreachable by links from /: ${orphans.length}`, orphans.slice(0, 15));
const deep = sitemapPaths.filter((p) => (depth.get(p) ?? 99) > 3);
console.log(`sitemap URLs deeper than 3 clicks: ${deep.length}`, deep.slice(0, 10));
const weak = sitemapPaths.filter((p) => (inbound.get(p) || 0) <= 2);
console.log(`sitemap URLs with <=2 inbound links: ${weak.length}`, weak.slice(0, 15));
const dead = [...pages].filter(([, p]) => p.status === 200 && p.out.size <= 3).map(([p, v]) => `${p}(${v.out.size})`);
console.log(`near dead ends (<=3 distinct internal links): ${dead.length}`, dead.slice(0, 10));
const heavy = [...pages].filter(([, p]) => p.out.size > 100).map(([p, v]) => `${p}(${v.out.size})`);
console.log(`pages with >100 distinct internal links: ${heavy.length}`, heavy);
const q = [...pages].flatMap(([p, v]) => v.queryLinks.map((l) => `${p} -> ${l}`));
console.log(`internal links carrying query strings: ${q.length}`, q.slice(0, 10));
const bad = [...pages].filter(([, p]) => p.status !== 200).map(([p, v]) => `${p}:${v.status}`);
console.log(`linked URLs not returning 200: ${bad.length}`, bad.slice(0, 15));
const top = (label, filter, n = 8) => console.log(`${label}:`, [...inbound].filter(([p]) => filter(p)).sort((a, b) => b[1] - a[1]).slice(0, n).map(([p, c]) => `${p}=${c}`).join("  "));
top("most linked pages", () => true, 12);
const teamCounts = sitemapPaths.filter((p) => kind(p) === "team").map((p) => [p, inbound.get(p) || 0]).sort((a, b) => a[1] - b[1]);
console.log("least-linked teams:", teamCounts.slice(0, 8).map(([p, c]) => `${p}=${c}`).join("  "));
const mCounts = sitemapPaths.filter((p) => kind(p) === "matchup").map((p) => [p, inbound.get(p) || 0]).sort((a, b) => a[1] - b[1]);
console.log("least-linked matchups:", mCounts.slice(0, 5).map(([p, c]) => `${p}=${c}`).join("  "), "| most:", mCounts.slice(-5).map(([p, c]) => `${p}=${c}`).join("  "));
const oneLink = mCounts.filter(([, c]) => c === 1).length;
console.log(`matchups with exactly 1 inbound link: ${oneLink}; with >=3: ${mCounts.filter(([, c]) => c >= 3).length}`);
