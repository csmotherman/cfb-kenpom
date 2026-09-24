import type { Metadata } from "next";
import { conferenceName, teamMascot } from "@/lib/teamMascots";
import { getTeamSnapshot } from "@/lib/seoData";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AdvancedRow, AdvancedSeason } from "@/lib/types";

export const metadata: Metadata = {
  title: "Michigan Team Card Concepts | PRIME",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

type Metric = { label: string; value: string; rank: number | null };
type RankSpec = { key: keyof AdvancedRow; lowerBetter?: boolean };

const signed = (v: number | null | undefined, digits = 3) =>
  typeof v === "number" ? `${v >= 0 ? "+" : ""}${v.toFixed(digits)}` : "—";
const pctEdge = (v: number | null | undefined) =>
  typeof v === "number" ? `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%` : "—";

function rankFor(rows: AdvancedRow[], team: AdvancedRow | null, spec: RankSpec) {
  if (!team) return null;
  const own = team[spec.key];
  if (typeof own !== "number") return null;
  const vals = rows
    .map((row) => ({ slug: row.slug, value: row[spec.key] }))
    .filter((row): row is { slug: string; value: number } => typeof row.value === "number")
    .sort((a, b) => spec.lowerBetter ? a.value - b.value : b.value - a.value);
  const idx = vals.findIndex((row) => row.slug === team.slug);
  return idx >= 0 ? idx + 1 : null;
}

function Stat({ metric, compact = false }: { metric: Metric; compact?: boolean }) {
  return <div className={compact ? "ct-stat compact" : "ct-stat"}>
    <span>{metric.label}</span>
    <strong>{metric.value}</strong>
    <b>{metric.rank ? `#${metric.rank}` : "—"}</b>
  </div>;
}

function Brand({ year, inverse = false }: { year: number; inverse?: boolean }) {
  return <div className={inverse ? "ct-mini-brand inverse" : "ct-mini-brand"}>
    <img src="/brand/prime-header.png" alt="PRIME College Football" />
    <span>{year} · OPPONENT-ADJUSTED</span>
  </div>;
}

function TeamLockup({ team, nickname, teamId, record, conf }: { team:string; nickname:string; teamId:number; record:string; conf:string }) {
  return <div className="ct-lockup">
    <img src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${teamId}.png`} alt={`${team} logo`} />
    <div><h2>{team}</h2><p>{nickname}</p><span>{record} · {conf}</span></div>
  </div>;
}

export default async function CardTemplatePage() {
  const snapshot = await getTeamSnapshot("michigan");
  const team = snapshot?.entry.team ?? "Michigan";
  const nickname = teamMascot(team) ?? "";
  const teamId = snapshot?.entry.teamId ?? 130;
  const year = snapshot?.year ?? 2026;
  const record = snapshot?.latest?.record ?? "—";
  const conf = conferenceName(snapshot?.entry.conf);
  const net = snapshot?.latest?.adjEM ?? null;
  const off = snapshot?.latest?.adjO ?? null;
  const def = snapshot?.latest?.adjD ?? null;
  const netRank = snapshot?.latest?.rank ?? null;
  const offRank = snapshot?.latest?.adjORank ?? null;
  const defRank = snapshot?.latest?.adjDRank ?? null;

  let advanced: AdvancedRow | null = null;
  let advancedRows: AdvancedRow[] = [];
  try {
    const admin = createAdminClient();
    const { data } = await admin.from("premium_datasets").select("payload").eq("dataset_type","advanced").eq("season",year).eq("week",0).maybeSingle();
    const season = data?.payload as AdvancedSeason | undefined;
    const latestWeek = season?.weeks?.length ? Math.max(...season.weeks) : null;
    advancedRows = latestWeek === null ? [] : season?.byWeek?.[String(latestWeek)] ?? [];
    advanced = advancedRows.find((row) => row.slug === "michigan") ?? null;
  } catch {}

  const m = (label:string, value:string, key:keyof AdvancedRow, lowerBetter=false): Metric => ({
    label, value, rank: rankFor(advancedRows, advanced, { key, lowerBetter }),
  });

  const offense: Metric[] = [
    m("EPA / Play", signed(advanced?.epaAdj), "epaAdj"),
    m("Pass EPA / Play", signed(advanced?.passEpaAdj), "passEpaAdj"),
    m("Rush EPA / Play", signed(advanced?.rushEpaAdj), "rushEpaAdj"),
    m("Success Rate", pctEdge(advanced?.successAdj), "successAdj"),
    m("Explosiveness", signed(advanced?.offExp,4), "offExp"),
  ];
  const defense: Metric[] = [
    m("EPA / Play Allowed", signed(advanced?.epaAdjAllowed), "epaAdjAllowed", true),
    m("Pass EPA / Play Allowed", signed(advanced?.passEpaAdjAllowed), "passEpaAdjAllowed", true),
    m("Rush EPA / Play Allowed", signed(advanced?.rushEpaAdjAllowed), "rushEpaAdjAllowed", true),
    m("Success Rate Allowed", pctEdge(advanced?.successAdjAllowed), "successAdjAllowed", true),
    m("Explosiveness", signed(advanced?.defExp,4), "defExp"),
  ];
  const finishHavoc: Metric[] = [
    m("Off. Finishing", signed(advanced?.offFin,2), "offFin"),
    m("Off. Havoc Avoid.", signed(advanced?.offHavoc,4), "offHavoc"),
    m("Def. Finishing", signed(advanced?.defFin,2), "defFin"),
    m("Def. Havoc", signed(advanced?.defHavoc,4), "defHavoc"),
  ];
  const ratings: Metric[] = [
    { label:"Net Rating", value:signed(net,1), rank:netRank },
    { label:"Off Rating", value:signed(off,1), rank:offRank },
    { label:"Def Rating", value:signed(def,1), rank:defRank },
    { label:"ASM", value:signed(advanced?.asm,2), rank:rankFor(advancedRows,advanced,{key:"asm"}) },
  ];
  const hero = ratings[0];

  const cards = [
    { id:"01", name:"The Complete Profile", node:
      <article className="ct-concept ct-c1"><Brand year={year}/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-hero-rating"><span>PRIME NET RATING</span><strong>{hero.value}</strong><b>{hero.rank ? `#${hero.rank} NATIONALLY` : ""}</b></div>
        <div className="ct-two"><div><h3>OFFENSE</h3>{offense.map(x=><Stat key={x.label} metric={x} compact/>)}</div><div><h3>DEFENSE</h3>{defense.map(x=><Stat key={x.label} metric={x} compact/>)}</div></div>
        <div className="ct-url">PRIMECFB.COM</div></article> },
    { id:"02", name:"Big Rank", node:
      <article className="ct-concept ct-c2"><Brand year={year} inverse/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-big-rank"><span>NATIONAL PRIME RATING</span><strong>{hero.rank ? `#${hero.rank}` : "—"}</strong><p>{hero.value} NET RATING</p></div>
        <div className="ct-rating-strip">{ratings.slice(1).map(x=><Stat key={x.label} metric={x} compact/>)}</div>
        <footer>ALL METRICS OPPONENT-ADJUSTED <b>PRIMECFB.COM</b></footer></article> },
    { id:"03", name:"Offensive Identity", node:
      <article className="ct-concept ct-c3"><Brand year={year}/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-kicker">OFFENSIVE IDENTITY</div><div className="ct-feature"><span>OFF RATING</span><strong>{signed(off,1)}</strong><b>{offRank ? `#${offRank}` : "—"}</b></div>
        <div className="ct-list">{offense.map(x=><Stat key={x.label} metric={x}/>)}</div><div className="ct-url">PRIMECFB.COM</div></article> },
    { id:"04", name:"Defensive Identity", node:
      <article className="ct-concept ct-c4"><Brand year={year} inverse/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-kicker">DEFENSIVE IDENTITY</div><div className="ct-feature"><span>DEF RATING</span><strong>{signed(def,1)}</strong><b>{defRank ? `#${defRank}` : "—"}</b></div>
        <div className="ct-list">{defense.map(x=><Stat key={x.label} metric={x}/>)}</div><div className="ct-url">PRIMECFB.COM</div></article> },
    { id:"05", name:"Scouting Snapshot", node:
      <article className="ct-concept ct-c5"><Brand year={year}/><div className="ct-scout-top"><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/><div className="ct-scout-grade"><span>NET</span><strong>{hero.value}</strong><b>{hero.rank ? `#${hero.rank}` : "—"}</b></div></div>
        <h3>WHAT DEFINES THIS TEAM</h3><div className="ct-quad">{[offense[0],defense[0],finishHavoc[1],finishHavoc[3]].map(x=><Stat key={x.label} metric={x}/>)}</div>
        <footer>OPPONENT-ADJUSTED TEAM SNAPSHOT <b>PRIMECFB.COM</b></footer></article> },
    { id:"06", name:"Prime Grid", node:
      <article className="ct-concept ct-c6"><Brand year={year} inverse/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-grid-title"><span>PRIME PROFILE</span><strong>{hero.value}</strong><b>{hero.rank ? `#${hero.rank}` : ""}</b></div>
        <div className="ct-metric-grid">{[...offense.slice(0,3),...defense.slice(0,3)].map(x=><Stat key={x.label} metric={x}/>)}</div><div className="ct-url">PRIMECFB.COM</div></article> },
    { id:"07", name:"Efficiency Split", node:
      <article className="ct-concept ct-c7"><Brand year={year}/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-versus"><div><span>OFFENSE</span><strong>{signed(off,1)}</strong><b>{offRank ? `#${offRank}` : ""}</b></div><i>+</i><div><span>DEFENSE</span><strong>{signed(def,1)}</strong><b>{defRank ? `#${defRank}` : ""}</b></div></div>
        <div className="ct-mini-grid">{[offense[0],offense[3],defense[0],defense[3]].map(x=><Stat key={x.label} metric={x}/>)}</div><footer>EFFICIENCY, ADJUSTED FOR OPPONENT <b>PRIMECFB.COM</b></footer></article> },
    { id:"08", name:"Pressure & Finish", node:
      <article className="ct-concept ct-c8"><Brand year={year} inverse/><TeamLockup team={team} nickname={nickname} teamId={teamId} record={record} conf={conf}/>
        <div className="ct-kicker">PRESSURE + FINISHING</div><div className="ct-list ct-bold-list">{finishHavoc.map(x=><Stat key={x.label} metric={x}/>)}</div>
        <div className="ct-note">How Michigan creates disruption and finishes possessions after opponent adjustment.</div><div className="ct-url">PRIMECFB.COM</div></article> },
    { id:"09", name:"Editorial Profile", node:
      <article className="ct-concept ct-c9"><Brand year={year}/><div className="ct-editorial-head"><img src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${teamId}.png`} alt="" /><div><span>{year} TEAM PROFILE</span><h2>{team}</h2><p>{nickname}</p></div></div>
        <div className="ct-editorial-number"><span>NET RATING</span><strong>{hero.value}</strong><b>{hero.rank ? `NATIONAL RANK #${hero.rank}` : ""}</b></div>
        <div className="ct-editorial-stats">{[offense[0],offense[1],defense[0],defense[1],finishHavoc[3]].map(x=><Stat key={x.label} metric={x}/>)}</div><footer>{record} · {conf} <b>PRIMECFB.COM</b></footer></article> },
    { id:"10", name:"Social Hero", node:
      <article className="ct-concept ct-c10"><div className="ct-watermark">PRIME</div><Brand year={year} inverse/><img className="ct-hero-logo" src={`https://a.espncdn.com/i/teamlogos/ncaa/500/${teamId}.png`} alt="" /><h2>{team}</h2><p>{nickname}</p>
        <div className="ct-social-rating"><span>PRIME NET RATING</span><strong>{hero.value}</strong><b>{hero.rank ? `#${hero.rank} NATIONALLY` : ""}</b></div>
        <div className="ct-social-strip">{[offense[0],defense[0],finishHavoc[3]].map(x=><Stat key={x.label} metric={x} compact/>)}</div><footer>THE SIGNAL BEHIND COLLEGE FOOTBALL. <b>PRIMECFB.COM</b></footer></article> },
  ];

  return <main className="ct-page"><header className="ct-gallery-head"><img src="/brand/prime-header.png" alt="PRIME"/><div><h1>TEAM CARD LAB</h1><p>10 mobile-first concepts · Michigan · live PRIME data</p></div></header>
    <div className="ct-gallery">{cards.map(card=><section className="ct-gallery-item" key={card.id}><div className="ct-concept-label"><b>{card.id}</b><span>{card.name}</span></div>{card.node}</section>)}</div>
  </main>;
}