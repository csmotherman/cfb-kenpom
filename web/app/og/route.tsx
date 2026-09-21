import { ImageResponse } from "next/og";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { SITE_URL } from "@/lib/seo";
import { getGameContext, getLatestYear, getPrimeRankingsServer, getRankingsSeasonServer, getTeamSnapshot } from "@/lib/seoData";
import { logoUrl } from "@/lib/teamCode";
import { conferenceName } from "@/lib/teamMascots";

// Social share cards (1200x630) in the PRIME navy / gold / cream palette. Only a fixed set of card kinds is
// accepted and every team, game and number is read from the published data, so the URL cannot be used to put
// arbitrary text on a PRIME-branded image.
const NAVY = "#142742";
const GOLD = "#c59a43";
const GOLD_LIGHT = "#f2cf77";
const CREAM = "#f4f1ea";
const INK = "#171717";
const MUTED = "#4a473f";

async function asDataUri(fetchUrl: string | null, localFile?: string): Promise<string | null> {
  try {
    if (localFile) {
      const bytes = await readFile(path.join(process.cwd(), "public", localFile));
      return `data:image/png;base64,${bytes.toString("base64")}`;
    }
  } catch {
    /* fall through to the network */
  }
  if (!fetchUrl) return null;
  try {
    const response = await fetch(fetchUrl, { signal: AbortSignal.timeout(2500) });
    if (!response.ok) return null;
    const type = response.headers.get("content-type") || "image/png";
    return `data:${type};base64,${Buffer.from(await response.arrayBuffer()).toString("base64")}`;
  } catch {
    return null;
  }
}

const wordmark = () => asDataUri(`${SITE_URL}/brand/prime-wordmark-og.png`, "brand/prime-wordmark-og.png");

type Card = { eyebrow: string; headline: string; sub?: string; lines?: { left: string; right: string }[]; logos?: (string | null)[]; footerNote?: string };

function Frame({ card, mark }: { card: Card; mark: string | null }) {
  const long = card.headline.length > 34;
  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100%", height: "100%", background: CREAM, fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 132, padding: "0 64px", background: NAVY, borderBottom: `6px solid ${GOLD}` }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        {mark ? <img src={mark} width={264} height={88} alt="" style={{ objectFit: "contain" }} /> : <div style={{ display: "flex", color: GOLD_LIGHT, fontSize: 56, fontWeight: 700 }}>PRIME</div>}
        <div style={{ display: "flex", color: GOLD_LIGHT, fontSize: 24, letterSpacing: 3, textTransform: "uppercase" }}>College Football Analytics</div>
      </div>
      <div style={{ display: "flex", flex: 1, padding: "44px 64px 0", gap: 40 }}>
        {card.logos?.length ? (
          <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 20 }}>
            {card.logos.map((src, i) =>
              // eslint-disable-next-line @next/next/no-img-element
              src ? <img key={i} src={src} width={card.logos!.length > 1 ? 130 : 220} height={card.logos!.length > 1 ? 130 : 220} alt="" style={{ objectFit: "contain" }} /> : <div key={i} style={{ display: "flex", width: 130, height: 130 }} />,
            )}
          </div>
        ) : null}
        <div style={{ display: "flex", flexDirection: "column", flex: 1, justifyContent: "center" }}>
          <div style={{ display: "flex", color: GOLD, fontSize: 26, letterSpacing: 4, textTransform: "uppercase", fontWeight: 700 }}>{card.eyebrow}</div>
          <div style={{ display: "flex", color: NAVY, fontSize: long ? 60 : 78, fontWeight: 800, lineHeight: 1.05, marginTop: 14 }}>{card.headline}</div>
          {card.sub ? <div style={{ display: "flex", color: MUTED, fontSize: 32, marginTop: 18 }}>{card.sub}</div> : null}
          {card.lines?.length ? (
            <div style={{ display: "flex", flexDirection: "column", marginTop: 26, borderTop: `3px solid ${GOLD}` }}>
              {card.lines.map((line, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", color: INK, fontSize: 28, padding: "7px 0", borderBottom: "1px solid #d9d3c2" }}>
                  <span style={{ display: "flex" }}>{line.left}</span>
                  <span style={{ display: "flex", color: NAVY, fontWeight: 700 }}>{line.right}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", padding: "0 64px 26px", color: MUTED, fontSize: 24 }}>
        <span style={{ display: "flex" }}>{card.footerNote ?? "Opponent-adjusted ratings, rankings and predictions"}</span>
        <span style={{ display: "flex", color: NAVY, fontWeight: 700 }}>primecfb.com</span>
      </div>
    </div>
  );
}

async function buildCard(params: URLSearchParams): Promise<Card> {
  const kind = params.get("kind") ?? "default";
  const year = await getLatestYear();

  if (kind === "team") {
    const snapshot = await getTeamSnapshot(params.get("slug") ?? "");
    if (snapshot) {
      const row = snapshot.latest;
      const bits = [
        row?.record,
        snapshot.prime25Rank ? `PRIME 25 #${snapshot.prime25Rank}` : null,
        row?.rank ? `Power Rating #${row.rank}` : null,
      ].filter(Boolean);
      return {
        eyebrow: `${conferenceName(snapshot.entry.conf)} · Football Analytics`,
        headline: snapshot.fullName,
        sub: bits.join("  ·  ") || undefined,
        lines: row
          ? [
              { left: "Offense rating rank", right: row.adjORank ? `#${row.adjORank}` : "—" },
              { left: "Defense rating rank", right: row.adjDRank ? `#${row.adjDRank}` : "—" },
              { left: "Strength of schedule rank", right: row.sosRank ? `#${row.sosRank}` : "—" },
            ]
          : undefined,
        logos: [await asDataUri(logoUrl(snapshot.entry.teamId, 256))],
        footerNote: snapshot.year ? `${snapshot.year} season through ${snapshot.week !== null ? `Week ${snapshot.week}` : "the latest week"}` : undefined,
      };
    }
  }

  if (kind === "matchup") {
    const ctx = await getGameContext(params.get("season") ?? "", params.get("game") ?? "");
    if (ctx) {
      const record = (side: typeof ctx.away) => [side.rank ? `#${side.rank} PRIME rating` : null, side.record].filter(Boolean).join(" · ");
      return {
        eyebrow: `${ctx.season} · ${ctx.weekLabel} · Matchup Analytics`,
        headline: `${ctx.away.name} vs ${ctx.home.name}`,
        sub: ctx.game.venue ?? undefined,
        lines: [
          { left: ctx.away.name, right: record(ctx.away) || "—" },
          { left: ctx.home.name, right: record(ctx.home) || "—" },
        ],
        logos: [await asDataUri(logoUrl(ctx.game.awayTeamId, 256)), await asDataUri(logoUrl(ctx.game.homeTeamId, 256))],
      };
    }
  }

  if (kind === "ratings" || kind === "rankings") {
    if (kind === "rankings") {
      const prime = year ? await getPrimeRankingsServer(year) : null;
      if (prime) {
        return {
          eyebrow: `${prime.season} · Through Week ${prime.throughWeek}`,
          headline: "The PRIME 25",
          sub: "College football rankings built on performance and résumé",
          lines: prime.teams.slice(0, 4).map((t) => ({ left: `${t.rank}. ${t.team}`, right: t.record })),
        };
      }
      return { eyebrow: "College Football Rankings", headline: "The PRIME 25" };
    }
    const rankings = year ? await getRankingsSeasonServer(year) : null;
    const week = rankings?.weeks?.length ? rankings.weeks[rankings.weeks.length - 1] : null;
    const rows = rankings && week !== null ? (rankings.byWeek[String(week)] ?? []).filter((r) => r.rank && r.adjEM !== null).slice(0, 4) : [];
    return {
      eyebrow: year && week !== null ? `${year} · Through Week ${week}` : "College Football Ratings",
      headline: "PRIME Ratings",
      sub: "Opponent-adjusted team ratings",
      lines: rows.map((r) => ({ left: `${r.rank}. ${r.team}`, right: `${(r.adjEM ?? 0) >= 0 ? "+" : ""}${(r.adjEM ?? 0).toFixed(1)}` })),
    };
  }

  if (kind === "predictions") {
    return { eyebrow: year ? `${year} Season` : "College Football", headline: "Weekly Predictions", sub: "Projected margins, matchup analytics and game previews" };
  }

  return {
    eyebrow: "PRIME CFB Analytics",
    headline: "College football, measured by performance.",
    sub: "Opponent-adjusted ratings · The PRIME 25 · Weekly predictions",
  };
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const [card, mark] = await Promise.all([buildCard(params), wordmark()]);
  return new ImageResponse(<Frame card={card} mark={mark} />, {
    width: 1200,
    height: 630,
    headers: { "Cache-Control": "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800" },
  });
}
