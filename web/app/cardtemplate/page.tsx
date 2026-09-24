import type { Metadata } from "next";
import { conferenceName, teamMascot } from "@/lib/teamMascots";
import { getTeamSnapshot } from "@/lib/seoData";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AdvancedRow, AdvancedSeason } from "@/lib/types";

export const metadata: Metadata = {
  title: "Michigan Team Profile Card | PRIME",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

type Metric = { label: string; value: string; rank: number | null };

const signed = (v: number | null | undefined, digits = 3) =>
  typeof v === "number" ? (v >= 0 ? "+" : "") + v.toFixed(digits) : "—";

const pctEdge = (v: number | null | undefined) =>
  typeof v === "number" ? (v >= 0 ? "+" : "") + (v * 100).toFixed(1) + "%" : "—";

function rankFor(rows: AdvancedRow[], team: AdvancedRow | null, key: keyof AdvancedRow) {
  if (!team) return null;
  const own = team[key];
  if (typeof own !== "number") return null;
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: row[key] }))
    .filter((row): row is { slug: string; value: number } => typeof row.value === "number")
    .sort((a, b) => b.value - a.value);
  const index = ranked.findIndex((row) => row.slug === team.slug);
  return index >= 0 ? index + 1 : null;
}

function MetricRow({ metric }: { metric: Metric }) {
  return (
    <div className="ct-metric-row">
      <span>{metric.label}</span>
      <strong>{metric.value}</strong>
      <b>{metric.rank ? "#" + metric.rank : "—"}</b>
    </div>
  );
}

export default async function CardTemplatePage() {
  const snapshot = await getTeamSnapshot("michigan");
  const team = snapshot?.entry.team ?? "Michigan";
  const nickname = teamMascot(team) ?? "";
  const teamId = snapshot?.entry.teamId ?? 130;
  const year = snapshot?.year ?? 2026;
  const week = snapshot?.week ?? 3;
  const record = snapshot?.latest?.record ?? "—";
  const conf = conferenceName(snapshot?.entry.conf);
  const primeRank = snapshot?.prime25Rank ?? null;
  const latest = snapshot?.latest;

  let advanced: AdvancedRow | null = null;
  let rows: AdvancedRow[] = [];
  try {
    const admin = createAdminClient();
    const { data } = await admin
      .from("premium_datasets")
      .select("payload")
      .eq("dataset_type", "advanced")
      .eq("season", year)
      .eq("week", 0)
      .maybeSingle();
    const season = data?.payload as AdvancedSeason | undefined;
    const latestWeek = season?.weeks?.length ? Math.max(...season.weeks) : null;
    rows = latestWeek === null ? [] : season?.byWeek?.[String(latestWeek)] ?? [];
    advanced = rows.find((row) => row.slug === "michigan") ?? null;
  } catch {}

  const metric = (label: string, value: string, key: keyof AdvancedRow): Metric => ({
    label,
    value,
    rank: rankFor(rows, advanced, key),
  });

  const offense: Metric[] = [
    metric("EPA / Play", signed(advanced?.epaAdj), "epaAdj"),
    metric("Pass EPA", signed(advanced?.passEpaAdj), "passEpaAdj"),
    metric("Rush EPA", signed(advanced?.rushEpaAdj), "rushEpaAdj"),
    metric("Success Rate Edge", pctEdge(advanced?.successAdj), "successAdj"),
    metric("Explosiveness", signed(advanced?.offExp, 3), "offExp"),
    metric("Havoc Avoidance", signed(advanced?.offHavoc, 3), "offHavoc"),
  ];

  const defense: Metric[] = [
    metric("EPA / Play", signed(advanced?.epaAdjAllowed), "epaAdjAllowed"),
    metric("Pass EPA", signed(advanced?.passEpaAdjAllowed), "passEpaAdjAllowed"),
    metric("Rush EPA", signed(advanced?.rushEpaAdjAllowed), "rushEpaAdjAllowed"),
    metric("Success Rate Edge", pctEdge(advanced?.successAdjAllowed), "successAdjAllowed"),
    metric("Explosiveness", signed(advanced?.defExp, 3), "defExp"),
    metric("Havoc", signed(advanced?.defHavoc, 3), "defHavoc"),
  ];

  const asmRank = rankFor(rows, advanced, "asm");

  return (
    <main className="ct-page">
      <article className="ct-card" aria-label={team + " " + year + " PRIME team profile"}>
        <header className="ct-topbar">
          <img src="/brand/prime-header.png" alt="PRIME" />
          <div>
            <strong>{year} TEAM PROFILE</strong>
            <span>PRIMECFB.COM</span>
          </div>
        </header>

        <section className="ct-team">
          <img className="ct-team-logo" src={"https://a.espncdn.com/i/teamlogos/ncaa/500/" + teamId + ".png"} alt={team + " logo"} />
          <div className="ct-team-copy">
            <h1>{team}</h1>
            <p>{nickname}</p>
            <span>{record} · {conf} · Through Week {week}</span>
          </div>
          <div className="ct-prime-rank">
            <span>PRIME 25</span>
            <strong>{primeRank ? "#" + primeRank : "—"}</strong>
          </div>
        </section>

        <section className="ct-ratings">
          <div><span>NET RATING</span><strong>{signed(latest?.adjEM, 1)}</strong><b>{latest?.rank ? "#" + latest.rank : "—"}</b></div>
          <div><span>OFF RATING</span><strong>{signed(latest?.adjO, 1)}</strong><b>{latest?.adjORank ? "#" + latest.adjORank : "—"}</b></div>
          <div><span>DEF RATING</span><strong>{signed(latest?.adjD, 1)}</strong><b>{latest?.adjDRank ? "#" + latest.adjDRank : "—"}</b></div>
        </section>

        <section className="ct-context">
          <div><span>STRENGTH OF RECORD</span><b>{latest?.sorRank ? "#" + latest.sorRank : "—"}</b></div>
          <div><span>STRENGTH OF SCHEDULE</span><b>{latest?.sosRank ? "#" + latest.sosRank : "—"}</b></div>
          <div><span>ADJ. SCORING MARGIN</span><strong>{signed(advanced?.asm, 1)}</strong><b>{asmRank ? "#" + asmRank : "—"}</b></div>
        </section>

        <div className="ct-adjusted-note">ALL ADVANCED METRICS OPPONENT-ADJUSTED</div>

        <section className="ct-splits">
          <div className="ct-split">
            <div className="ct-split-head"><h2>OFFENSE</h2><span>VALUE · RANK</span></div>
            {offense.map((item) => <MetricRow key={item.label} metric={item} />)}
          </div>
          <div className="ct-split">
            <div className="ct-split-head"><h2>DEFENSE</h2><span>VALUE · RANK</span></div>
            {defense.map((item) => <MetricRow key={item.label} metric={item} />)}
          </div>
        </section>

        <footer className="ct-footer">
          <img src="/brand/prime-header.png" alt="" />
          <strong>PRIMECFB.COM</strong>
        </footer>
      </article>
    </main>
  );
}
