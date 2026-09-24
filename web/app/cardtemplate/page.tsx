import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Michigan Team Card | PRIME",
  robots: { index: false, follow: false },
};

const offense = [
  ["EPA / Play", "+0.24", "#8"],
  ["Pass EPA / Play", "+0.31", "#11"],
  ["Rush EPA / Play", "+0.18", "#6"],
  ["Success Rate", "48.7%", "#12"],
  ["Explosiveness", "1.21", "#7"],
];

const defense = [
  ["EPA / Play Allowed", "-0.09", "#5"],
  ["Pass EPA / Play Allowed", "-0.04", "#18"],
  ["Rush EPA / Play Allowed", "-0.14", "#3"],
  ["Success Rate Allowed", "34.1%", "#8"],
  ["Explosiveness Allowed", "0.92", "#29"],
];

function StatSection({ title, rows }: { title: string; rows: string[][] }) {
  return (
    <section className="ct-section">
      <div className="ct-section-head"><h2>{title}</h2><span>National Rank</span></div>
      <div className="ct-cols"><span>Metric</span><span>Value</span><span>Rank</span></div>
      {rows.map(([label,value,rank]) => (
        <div className="ct-row" key={label}><span>{label}</span><strong>{value}</strong><b>{rank}</b></div>
      ))}
    </section>
  );
}

export default function CardTemplatePage() {
  return (
    <main className="ct-page">
      <article className="ct-card">
        <header className="ct-brand"><span>PRIME CFB ANALYTICS</span><strong>PRIME</strong></header>
        <section className="ct-team">
          <div className="ct-mark" aria-label="Michigan">M</div>
          <div className="ct-identity"><h1>MICHIGAN</h1><p>WOLVERINES</p><div>2026 <i /> 3-0 <i /> BIG TEN</div></div>
          <div className="ct-rating"><span>NET RATING</span><strong>+21.8</strong><p><b>#9</b> NATIONALLY</p></div>
        </section>
        <StatSection title="OFFENSE" rows={offense} />
        <StatSection title="DEFENSE" rows={defense} />
        <footer><span>DATA. CONTEXT. A CLEARER PICTURE.</span><b>PRIMECFB.COM</b></footer>
      </article>
    </main>
  );
}
