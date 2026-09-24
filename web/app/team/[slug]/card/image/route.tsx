import { ImageResponse } from "next/og";
import { getTeamCardData, type TeamCardMetric } from "@/lib/teamCardData";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const navy = "#102b4a";
const gold = "#ad7d20";
const paper = "#f9f7f1";
const line = "#d7d1c6";
const muted = "#6f7a87";

async function asDataUrl(url: string): Promise<string | null> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return null;
    const mime = response.headers.get("content-type") || "image/png";
    const bytes = Buffer.from(await response.arrayBuffer());
    return "data:" + mime + ";base64," + bytes.toString("base64");
  } catch {
    return null;
  }
}

function Rank({ value }: { value: number | null }) {
  return (
    <span style={{ color: gold, fontSize: 28, lineHeight: 1, fontWeight: 800 }}>
      {value ? "#" + value : "—"}
    </span>
  );
}

function MetricRow({ metric }: { metric: TeamCardMetric }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        height: 72,
        padding: "0 22px",
        borderBottom: "1px solid #e6e1d8",
      }}
    >
      <span style={{ flex: 1, fontSize: 22, fontWeight: 600 }}>{metric.label}</span>
      <strong style={{ width: 132, textAlign: "right", fontSize: 23 }}>{metric.value}</strong>
      <span style={{ width: 76, textAlign: "right" }}>
        <Rank value={metric.rank} />
      </span>
    </div>
  );
}

export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const data = await getTeamCardData(slug);
  if (!data) return new Response("Team not found", { status: 404 });

  const primeAssetUrl = new URL("/brand/prime-header.png", request.url).toString();
  const espnFallback = "https://a.espncdn.com/i/teamlogos/ncaa/500/" + data.teamId + ".png";
  const [primeLogo, teamLogoPrimary] = await Promise.all([
    asDataUrl(primeAssetUrl),
    asDataUrl(data.logo),
  ]);
  const teamLogo = teamLogoPrimary ?? await asDataUrl(espnFallback);

  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        background: "#dedbd4",
        padding: 28,
        color: navy,
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 18,
          background: paper,
          border: "2px solid #cfc9bd",
          padding: 36,
          position: "relative",
        }}
      >
        <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 8, background: "#b88624" }} />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: 76,
            borderBottom: "1px solid " + line,
            paddingBottom: 15,
          }}
        >
          {primeLogo ? (
            <img src={primeLogo} alt="PRIME" width="205" height="58" style={{ objectFit: "contain", objectPosition: "left center" }} />
          ) : (
            <strong style={{ color: gold, fontSize: 34, letterSpacing: 2 }}>PRIME</strong>
          )}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <strong style={{ fontSize: 18, letterSpacing: 4 }}>{data.year} TEAM PROFILE</strong>
            <span style={{ marginTop: 8, fontSize: 14, letterSpacing: 4, color: "#8c7650" }}>PRIMECFB.COM</span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            height: 170,
            borderBottom: "1px solid " + line,
            paddingBottom: 18,
          }}
        >
          <div style={{ width: 150, height: 145, display: "flex", alignItems: "center", justifyContent: "center" }}>
            {teamLogo ? (
              <img src={teamLogo} alt={data.team + " logo"} width="126" height="126" style={{ objectFit: "contain" }} />
            ) : null}
          </div>

          <div
            style={{
              flex: 1,
              height: 132,
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              borderLeft: "2px solid #d0bd93",
              paddingLeft: 26,
            }}
          >
            <strong
              style={{
                fontSize: 66,
                lineHeight: 0.9,
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: -1.5,
              }}
            >
              {data.team}
            </strong>
            <span
              style={{
                marginTop: 12,
                color: gold,
                fontSize: 22,
                fontWeight: 700,
                letterSpacing: 6,
                textTransform: "uppercase",
              }}
            >
              {data.nickname}
            </span>
            <span style={{ marginTop: 15, color: "#617083", fontSize: 16, fontWeight: 700, letterSpacing: 1.5 }}>
              {data.record} · {data.conference} · THROUGH WEEK {data.week}
            </span>
          </div>

          <div
            style={{
              width: 170,
              height: 116,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              borderLeft: "2px solid #d0bd93",
              paddingLeft: 16,
            }}
          >
            <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: 3, color: "#8a7550" }}>PRIME 25</span>
            <strong style={{ marginTop: 4, fontSize: 72, lineHeight: 0.95, fontWeight: 800 }}>
              {data.primeRank ? "#" + data.primeRank : "—"}
            </strong>
          </div>
        </div>

        <div style={{ display: "flex", border: "1px solid " + line, background: "#fff", height: 142 }}>
          {[
            ["NET RATING", data.net],
            ["OFF RATING", data.offenseRating],
            ["DEF RATING", data.defenseRating],
          ].map(([label, stat], index) => {
            const item = stat as { value: string; rank: number | null };
            return (
              <div
                key={label as string}
                style={{
                  flex: 1,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRight: index < 2 ? "1px solid #e2ddd4" : "none",
                }}
              >
                <span style={{ color: muted, fontSize: 14, fontWeight: 700, letterSpacing: 2.5 }}>{label as string}</span>
                <strong style={{ marginTop: 7, fontSize: 54, lineHeight: 0.95, fontWeight: 800 }}>{item.value}</strong>
                <span style={{ marginTop: 6 }}><Rank value={item.rank} /></span>
              </div>
            );
          })}
        </div>

        <div style={{ display: "flex", border: "1px solid " + line, background: "#f2efe8", height: 84 }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 14, borderRight: "1px solid #ddd6ca" }}>
            <span style={{ color: muted, fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>STRENGTH OF RECORD</span>
            <Rank value={data.strengthOfRecordRank} />
          </div>
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 14, borderRight: "1px solid #ddd6ca" }}>
            <span style={{ color: muted, fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>STRENGTH OF SCHEDULE</span>
            <Rank value={data.strengthOfScheduleRank} />
          </div>
          <div style={{ flex: 1.2, display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
            <span style={{ color: muted, fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>ADJ. SCORING MARGIN</span>
            <strong style={{ fontSize: 22 }}>{data.adjustedScoringMargin.value}</strong>
            <Rank value={data.adjustedScoringMargin.rank} />
          </div>
        </div>

        <div
          style={{
            height: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#88734e",
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: 3.5,
          }}
        >
          ALL ADVANCED METRICS OPPONENT-ADJUSTED
        </div>

        <div style={{ display: "flex", gap: 18, height: 508 }}>
          {[["OFFENSE", data.offense], ["DEFENSE", data.defense]].map(([title, metrics]) => (
            <div
              key={title as string}
              style={{
                flex: 1,
                height: 508,
                display: "flex",
                flexDirection: "column",
                border: "1px solid #d5d0c6",
                background: "#fff",
              }}
            >
              <div
                style={{
                  height: 76,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0 20px",
                  background: navy,
                  color: "#fff",
                  borderBottom: "5px solid #b88624",
                }}
              >
                <strong style={{ fontSize: 38, fontWeight: 800, letterSpacing: 1.5 }}>{title as string}</strong>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 2, color: "#c8d0d8" }}>VALUE · RANK</span>
              </div>
              {(metrics as TeamCardMetric[]).map((metric) => <MetricRow key={metric.label} metric={metric} />)}
            </div>
          ))}
        </div>

        <div
          style={{
            height: 52,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 24,
            borderTop: "1px solid " + line,
            paddingTop: 12,
          }}
        >
          {primeLogo ? (
            <img src={primeLogo} alt="" width="126" height="34" style={{ objectFit: "contain" }} />
          ) : (
            <strong style={{ color: gold, fontSize: 22 }}>PRIME</strong>
          )}
          <strong style={{ fontSize: 16, letterSpacing: 3 }}>PRIMECFB.COM</strong>
        </div>
      </div>
    </div>,
    { width: 1080, height: 1350 }
  );
}
