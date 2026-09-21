// Lab Core Web Vitals + layout-shift attribution for a running PRIME build (default http://localhost:3111).
// Usage: node scripts/cwv.mjs [--origin=http://localhost:3111] [--runs=3] [--paths=/,/ratings] [--verbose]
// Mobile = 390x800 with 4x CPU throttle; desktop = 1300x900. Reports median LCP/CLS, the LCP element, the elements
// responsible for layout shifts (with before/after rects), and the JSON/API requests each page makes.
import { chromium } from "playwright";
const args = Object.fromEntries(process.argv.slice(2).map((a) => { const [k, v] = a.replace(/^--/, "").split("="); return [k, v ?? true]; }));
const ORIGIN = args.origin || "http://localhost:3111";
const RUNS = Number(args.runs || 3);
const PATHS = (args.paths || "/,/ratings,/rankings,/predictions,/teams,/team/michigan,/matchup/2026/401856696").split(",");
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath: CHROME });
const median = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
for (const [label, viewport, cpu] of [["mobile ", { width: 390, height: 800 }, 4], ["desktop", { width: 1300, height: 900 }, 1]]) {
  for (const path of PATHS) {
    const runs = [];
    let reqs = [];
    for (let i = 0; i < RUNS; i++) {
      const ctx = await browser.newContext({ viewport });
      const page = await ctx.newPage();
      const cdp = await ctx.newCDPSession(page);
      if (cpu > 1) await cdp.send("Emulation.setCPUThrottlingRate", { rate: cpu });
      const seen = [];
      page.on("request", (r) => { const u = new URL(r.url()); if (/^\/(data|api)\//.test(u.pathname)) seen.push(u.pathname); });
      await page.addInitScript(() => {
        window.__m = { lcp: 0, lcpEl: "", cls: 0, shifts: [] };
        new PerformanceObserver((l) => { for (const e of l.getEntries()) { window.__m.lcp = e.startTime; const n = e.element; window.__m.lcpEl = n ? n.nodeName.toLowerCase() + (n.className && typeof n.className === "string" ? "." + n.className.trim().split(/\s+/)[0] : "") : ""; } }).observe({ type: "largest-contentful-paint", buffered: true });
        new PerformanceObserver((l) => { for (const e of l.getEntries()) { if (e.hadRecentInput) continue; window.__m.cls += e.value; window.__m.shifts.push({ t: Math.round(e.startTime), v: e.value, s: (e.sources || []).map((s) => ({ n: s.node ? (s.node.id ? "#" + s.node.id : s.node.nodeName.toLowerCase() + (typeof s.node.className === "string" && s.node.className ? "." + s.node.className.trim().split(/\s+/).slice(0, 2).join(".") : "")) : "?", p: [s.previousRect.y, s.previousRect.height], c: [s.currentRect.y, s.currentRect.height] })) }); } }).observe({ type: "layout-shift", buffered: true });
      });
      await page.goto(ORIGIN + path, { waitUntil: "load" });
      await page.waitForTimeout(cpu > 1 ? 4500 : 3000);
      // INP proxy: time to handle a click on the first sortable header / button, when present.
      let inp = null;
      const target = page.locator("th button, button.site-search__toggle").first();
      if (await target.count()) { const t0 = Date.now(); await target.click({ timeout: 2000 }).catch(() => {}); await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))); inp = Date.now() - t0; }
      const m = await page.evaluate(() => window.__m);
      runs.push({ ...m, inp });
      reqs = seen;
      await ctx.close();
    }
    const lcp = Math.round(median(runs.map((r) => r.lcp)));
    const cls = median(runs.map((r) => r.cls));
    const worst = runs.sort((a, b) => b.cls - a.cls)[Math.floor(runs.length / 2)];
    console.log(`${label} ${path.padEnd(26)} LCP ${String(lcp).padStart(5)}ms  CLS ${cls.toFixed(3)}  lcpEl ${worst.lcpEl}  clickMs ${worst.inp ?? "-"}  data/api requests: ${reqs.length}`);
    if (args.verbose || cls > 0.05) for (const s of worst.shifts.filter((x) => x.v > 0.005).slice(0, 6)) console.log(`      shift ${s.v.toFixed(3)} @${s.t}ms: ` + s.s.slice(0, 3).map((x) => `${x.n} y${Math.round(x.p[0])}h${Math.round(x.p[1])}->y${Math.round(x.c[0])}h${Math.round(x.c[1])}`).join(" | "));
    if (args.verbose) console.log("      requests:", [...new Set(reqs)].join(" "));
  }
}
await browser.close();
