// Notifies IndexNow-participating engines (Bing, Yandex, Naver, Seznam; Google does not use IndexNow) about canonical
// URLs whose <lastmod> changed since the last successful submission. It never submits the whole site: it diffs the live
// sitemap against a local state file and sends only new or newer URLs.
//
// Setup (once): generate a key (8-128 hex characters), host it at https://primecfb.com/<key>.txt by adding
// web/public/<key>.txt containing exactly the key, and export INDEXNOW_KEY=<key> where you run this script.
// Usage:  npm run indexnow -- --dry-run          show what would be sent
//         npm run indexnow                        send changed URLs
//         npm run indexnow -- --sitemap=https://primecfb.com/sitemap.xml
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const HOST = "primecfb.com";
const args = new Map(process.argv.slice(2).map((a) => { const [k, v] = a.replace(/^--/, "").split("="); return [k, v ?? true]; }));
const dryRun = args.has("dry-run");
const sitemapUrl = args.get("sitemap") || `https://${HOST}/sitemap.xml`;
const STATE = new URL("../.indexnow-state.json", import.meta.url);
const key = process.env.INDEXNOW_KEY;
if (!key && !dryRun) { console.error("Set INDEXNOW_KEY (see the header of this file)."); process.exit(1); }
if (key && !/^[a-zA-Z0-9-]{8,128}$/.test(key)) { console.error("INDEXNOW_KEY must be 8-128 letters, digits or dashes."); process.exit(1); }

const xml = await (await fetch(sitemapUrl)).text();
const entries = [...xml.matchAll(/<url>([\s\S]*?)<\/url>/g)].map((m) => ({
  url: (m[1].match(/<loc>([^<]+)<\/loc>/) || [])[1],
  lastmod: (m[1].match(/<lastmod>([^<]+)<\/lastmod>/) || [])[1] || null,
  freq: (m[1].match(/<changefreq>([^<]+)<\/changefreq>/) || [])[1] || null,
})).filter((e) => e.url && new URL(e.url).hostname === HOST);
const state = existsSync(STATE) ? JSON.parse(readFileSync(STATE, "utf8")) : {};
const changed = entries.filter((e) => {
  const seen = state[e.url];
  if (seen === undefined) return true; // never submitted
  return !!e.lastmod && (!seen || new Date(e.lastmod) > new Date(seen));
});
// The first run would otherwise submit the entire site; require an explicit opt-in for that.
if (!Object.keys(state).length && changed.length > 200 && !args.has("initial")) {
  console.log(`First run: ${changed.length} URLs are new to the state file. Re-run with --initial to submit them (once), or --dry-run to inspect.`);
  process.exit(dryRun ? 0 : 1);
}
console.log(`${entries.length} sitemap URLs, ${changed.length} new or changed since the last submission.`);
if (dryRun || !changed.length) { changed.slice(0, 25).forEach((e) => console.log("  " + e.url)); process.exit(0); }
for (let i = 0; i < changed.length; i += 10000) {
  const batch = changed.slice(i, i + 10000);
  const res = await fetch("https://api.indexnow.org/IndexNow", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({ host: HOST, key, keyLocation: `https://${HOST}/${key}.txt`, urlList: batch.map((e) => e.url) }),
  });
  if (!(res.status === 200 || res.status === 202)) { console.error(`IndexNow rejected the batch: ${res.status} ${await res.text()}`); writeFileSync(STATE, JSON.stringify(state, null, 1)); process.exit(1); }
  for (const e of batch) state[e.url] = e.lastmod || new Date().toISOString();
}
writeFileSync(STATE, JSON.stringify(state, null, 1));
console.log(`Submitted ${changed.length} URLs.`);
