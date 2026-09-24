import { ImageResponse } from "next/og";
import { getTeamCardData, type TeamCardMetric } from "@/lib/teamCardData";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const navy = "#102b4a";
const gold = "#ad7d20";
const paper = "#f9f7f1";
const line = "#d7d1c6";
const muted = "#6f7a87";

function Rank({ value }: { value: number | null }) {
  return <span style={{ color: gold, fontSize: 24, fontWeight: 800 }}>{value ? "#" + value : "—"}</span>;
}

function MetricRow({ metric }: { metric: TeamCardMetric }) {
  return (
    <div style={{ display: "flex", alignItems: "center", height: 61, padding: "0 18px", borderBottom: "1px solid #e6e1d8" }}>
      <span style={{ flex: 1, fontSize: 19, fontWeight: 600 }}>{metric.label}</span>
      <strong style={{ width: 122, textAlign: "right", fontSize: 20 }}>{metric.value}</strong>
      <span style={{ width: 66, textAlign: "right" }}><Rank value={metric.rank} /></span>
    </div>
  );
}

export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const data = await getTeamCardData(slug);
  if (!data) return new Response("Team not found", { status: 404 });

  const primeLogo = new URL("/brand/prime-header.png", request.url).toString();

  return new ImageResponse(
    <div style={{ width: "100%", height: "100%", display: "flex", background: "#dedbd4", padding: 28, color: navy, fontFamily: "Arial, sans-serif" }}>
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 18, background: paper, border: "2px solid #cfc9bd", padding: 34, position: "relative" }}>
        <div style={{ position: "absolute", left: 0, right: 0, top: 0, height: 7, background: "#b88624" }} />

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 64, borderBottom: "1px solid " + line, paddingBottom: 13 }}>
          <img src={primeLogo} width="210" height="58" style={{ objectFit: "contain" }} />
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
            <strong style={{ fontSize: 17, letterSpacing: 3 }}>{data.year} TEAM PROFILE</strong>
            <span style={{ marginTop: 6, fontSize: 14, letterSpacing: 3, color: "#8c7650" }}>PRIMECFB.COM</span>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", minHeight: 148, borderBottom: "1px solid " + line, paddingBottom: 16 }}>
          <div style={{ width: 154, display: "flex", justifyContent: "center" }}>
            <img src={data.logo} width="132" height="132" style={{ objectFit: "contain" }} />
          </div>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", borderLeft: "2px solid #d0bd93", paddingLeft: 24 }}>
            <strong style={{ fontSize: 66, lineHeight: .9, textTransform: "uppercase", letterSpacing: -1 }}>{data.team}</strong>
            <span style={{ marginTop: 11, color: gold, fontSize: 22, fontWeight: 700, letterSpacing: 5, textTransform: "uppercase" }}>{data.nickname}</span>
            <span style={{ marginTop: 13, color: "#617083", fontSize: 16, fontWeight: 700, letterSpacing: 1.5 }}>{data.record} · {data.conference} · THROUGH WEEK {data.week}</span>
          </div>
          <div style={{ width: 166, display: "flex", flexDirection: "column", alignItems: "center", borderLeft: "2px solid #d0bd93", paddingLeft: 16 }}>
            <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: 2.5, color: "#8a7550" }}>PRIME 25</span>
            <strong style={{ marginTop: 4, fontSize: 70, lineHeight: 1 }}>{data.primeRank ? "#" + data.primeRank : "—"}</strong>
          </div>
        </div>

        <div style={{ display: "flex", border: "1px solid " + line, background: "#fff", height: 126 }}>
          {[
            ["NET RATING", data.net],
            ["OFF RATING", data.offenseRating],
            ["DEF RATING", data.defenseRating],
          ].map(([label, stat], index) => {
            const item = stat as { value: string; rank: number | null };
            return (
              <div key={label as string} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", borderRight: index < 2 ? "1px solid #e2ddd4" : "none" }}>
                <span style={{ color: muted, fontSize: 14, fontWeight: 700, letterSpacing: 2 }}>{label as string}</span>
                <strong style={{ marginTop: 4, fontSize: 52, lineHeight: 1 }}>{item.value}</strong>
                <Rank value={item.rank} />
              </div>
            );
          })}
        </div>

        <div style={{ display: "flex", border: "1px solid " + line, background: "#f2efe8", height: 77 }}>
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 14, borderRight: "1px solid #ddd6ca" }}>
            <span style={{ color: muted, fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>STRENGTH OF RECORD</span><Rank value={data.strengthOfRecordRank} />
          </div>
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 14, borderRight: "1px solid #ddd6ca" }}>
            <span style={{ color: muted, fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>STRENGTH OF SCHEDULE</span><Rank value={data.strengthOfScheduleRank} />
          </div>
          <div style={{ flex: 1.2, display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
            <span style={{ color: muted, fontSize: 12, fontWeight: 700, letterSpacing: 1.5 }}>ADJ. SCORING MARGIN</span>
            <strong style={{ fontSize: 21 }}>{data.adjustedScoringMargin.value}</strong>
            <Rank value={data.adjustedScoringMargin.rank} />
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "center", color: "#88734e", fontSize: 13, fontWeight: 700, letterSpacing: 3 }}>
          ALL ADVANCED METRICS OPPONENT-ADJUSTED
        </div>

        <div style={{ flex: 1, display: "flex", gap: 18 }}>
          {[["OFFENSE", data.offense], ["DEFENSE", data.defense]].map(([title, metrics]) => (
            <div key={title as string} style={{ flex: 1, display: "flex", flexDirection: "column", border: "1px solid #d5d0c6", background: "#fff" }}>
              <div style={{ height: 74, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px", background: navy, color: "#fff", borderBottom: "5px solid #b88624" }}>
                <strong style={{ fontSize: 36, letterSpacing: 1.5 }}>{title as string}</strong>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: 2, color: "#c8d0d8" }}>VALUE · RANK</span>
              </div>
              {(metrics as TeamCardMetric[]).map((metric) => <MetricRow key={metric.label} metric={metric} />)}
            </div>
          ))}
        </div>

        <div style={{ height: 48, display: "flex", alignItems: "center", justifyContent: "center", gap: 24, borderTop: "1px solid " + line, paddingTop: 10 }}>
          <img src={primeLogo} width="126" height="34" style={{ objectFit: "contain" }} />
          <strong style={{ fontSize: 16, letterSpacing: 3 }}>PRIMECFB.COM</strong>
        </div>
      </div>
    </div>,
    { width: 1080, height: 1350 }
  );
}
