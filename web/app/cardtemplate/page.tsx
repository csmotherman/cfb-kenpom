import type { Metadata } from "next";
import { conferenceName, teamMascot } from "@/lib/teamMascots";
import { getTeamSnapshot } from "@/lib/seoData";

export const metadata: Metadata = {
  title: "Michigan Team Card | PRIME",
  robots: { index: false, follow: false },
};

const offense = [
  ["EPA / Play", "+0.24", "#8"], ["Pass EPA / Play", "+0.31", "#11"],
  ["Rush EPA / Play", "+0.18", "#6"], ["Success Rate", "48.7%", "#12"], ["Explosiveness", "1.21", "#7"],
];
const defense = [
  ["EPA / Play Allowed", "-0.09", "#5"], ["Pass EPA / Play Allowed", "-0.04", "#18"],
  ["Rush EPA / Play Allowed", "-0.14", "#3"], ["Success Rate Allowed", "34.1%", "#8"], ["Explosiveness Allowed", "0.92", "#29"],
];

function StatSection({ title, rows }: { title: string; rows: string[][] }) {
  return <section className="ct-section">
    <div className="ct-section-head"><h2>{title}</h2><span>National Rank</span></div>
    <div className="ct-cols"><span>Metric</span><span>Value</span><span>Rank</span></div>
    {rows.map(([label,value,rank]) => <div className="ct-row" key={label}><span>{label}</span><strong>{value}</strong><b>{rank}</b></div>)}
  </section>;
}

export default async function CardTemplatePage() {
  const snapshot = await getTeamSnapshot("michigan");
  const team = snapshot?.entry.team ?? "Michigan";
  const nickname = teamMascot(team) ?? "";
  const teamId = snapshot?.entry.teamId ?? 130;
  const year = snapshot?.year ?? 2026;
  const record = snapshot?.latest?.record ?? "—";
  const conf = conferenceName(snapshot?.entry.conf);
  const net = snapshot?.latest?.adjEM;
  const ratingRank = snapshot?.latest?.rank;
  const netText = typeof net === "number" ? `${net >= 0 ? "+" : ""}${net.toFixed(1)}` : "—";
  return <main className="ct-page">
    <article className="ct-card">
      <header className="ct-brand">
        <img src="/brand/prime-header.png" alt="PRIME College Football" className="ct-prime-logo" />
        <span>{year} TEAM CARD</span>
      </header>
      <section className="ct-team">
        <div className="ct-team-logo-wrap"><img className="ct-team-logo" src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${teamId}.png`} alt={`${team} logo`} /></div>
        <div className="ct-identity"><h1>{team}</h1><p>{nickname}</p><div>{year}<i />{record}<i />{conf}</div></div>
        <div className="ct-rating"><span>NET RATING</span><strong>{netText}</strong><p>{ratingRank ? <><b>#{ratingRank}</b> NATIONALLY</> : "UNRANKED"}</p></div>
      </section>
      <StatSection title="OFFENSE" rows={offense} />
      <StatSection title="DEFENSE" rows={defense} />
      <footer><span>DATA. CONTEXT. A CLEARER PICTURE.</span><b>PRIMECFB.COM</b></footer>
    </article>
  </main>;
}