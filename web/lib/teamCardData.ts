import { createAdminClient } from "@/lib/supabase/admin";
import { getTeamSnapshot } from "@/lib/seoData";
import { conferenceName, teamMascot } from "@/lib/teamMascots";
import { logoUrl } from "@/lib/teamCode";
import type { AdvancedRow, AdvancedSeason } from "@/lib/types";

export type TeamCardMetric = {
  label: string;
  value: string;
  rank: number | null;
};

export type TeamCardData = {
  slug: string;
  team: string;
  nickname: string;
  teamId: number;
  logo: string;
  year: number;
  week: number;
  record: string;
  conference: string;
  primeRank: number | null;
  net: { value: string; rank: number | null };
  offenseRating: { value: string; rank: number | null };
  defenseRating: { value: string; rank: number | null };
  strengthOfRecordRank: number | null;
  strengthOfScheduleRank: number | null;
  adjustedScoringMargin: { value: string; rank: number | null };
  offense: TeamCardMetric[];
  defense: TeamCardMetric[];
};

const signed = (value: number | null | undefined, digits = 3) =>
  typeof value === "number" && Number.isFinite(value)
    ? (value >= 0 ? "+" : "") + value.toFixed(digits)
    : "—";

const pctEdge = (value: number | null | undefined) =>
  typeof value === "number" && Number.isFinite(value)
    ? (value >= 0 ? "+" : "") + (value * 100).toFixed(1) + "%"
    : "—";

type CardMetricKey =
  | "asm"
  | "epaAdj" | "passEpaAdj" | "rushEpaAdj" | "successAdj" | "offExp" | "offHavoc"
  | "epaAdjAllowed" | "passEpaAdjAllowed" | "rushEpaAdjAllowed" | "successAdjAllowed" | "defExp" | "defHavoc";

function rankFor(rows: AdvancedRow[], team: AdvancedRow | null, key: CardMetricKey): number | null {
  if (!team) return null;
  const own = team[key];
  if (own === null || own === undefined || !Number.isFinite(own)) return null;
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: row[key] }))
    .filter((row) => row.value !== null && row.value !== undefined && Number.isFinite(row.value))
    .sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
  const index = ranked.findIndex((row) => row.slug === team.slug);
  return index >= 0 ? index + 1 : null;
}

export async function getTeamCardData(slug: string): Promise<TeamCardData | null> {
  const snapshot = await getTeamSnapshot(slug);
  if (!snapshot?.latest || year === null || week === null) return null;

  const year = snapshot.year;
  const week = snapshot.week;
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
    const availableWeeks = season?.weeks?.filter((week) => week <= week) ?? [];
    const advancedWeek = availableWeeks.length ? Math.max(...availableWeeks) : null;
    rows = advancedWeek === null ? [] : season?.byWeek?.[String(advancedWeek)] ?? [];
    advanced = rows.find((row) => row.slug === slug) ?? null;
  } catch {
    // The public identity/rating portion can still render if the advanced
    // dataset is temporarily unavailable.
  }

  const metric = (label: string, value: string, key: CardMetricKey): TeamCardMetric => ({
    label,
    value,
    rank: rankFor(rows, advanced, key),
  });

  return {
    slug,
    team: snapshot.entry.team,
    nickname: teamMascot(snapshot.entry.team) ?? "",
    teamId: snapshot.entry.teamId,
    logo: logoUrl(snapshot.entry.teamId, 256),
    year: year,
    week: week,
    record: snapshot.latest.record,
    conference: conferenceName(snapshot.entry.conf),
    primeRank: snapshot.prime25Rank,
    net: { value: signed(snapshot.latest.adjEM, 1), rank: snapshot.latest.rank },
    offenseRating: { value: signed(snapshot.latest.adjO, 1), rank: snapshot.latest.adjORank },
    defenseRating: { value: signed(snapshot.latest.adjD, 1), rank: snapshot.latest.adjDRank },
    strengthOfRecordRank: snapshot.latest.sorRank,
    strengthOfScheduleRank: snapshot.latest.sosRank,
    adjustedScoringMargin: {
      value: signed(advanced?.asm, 1),
      rank: rankFor(rows, advanced, "asm"),
    },
    offense: [
      metric("EPA / Play", signed(advanced?.epaAdj), "epaAdj"),
      metric("Pass EPA", signed(advanced?.passEpaAdj), "passEpaAdj"),
      metric("Rush EPA", signed(advanced?.rushEpaAdj), "rushEpaAdj"),
      metric("Success Rate Edge", pctEdge(advanced?.successAdj), "successAdj"),
      metric("Explosiveness", signed(advanced?.offExp, 3), "offExp"),
      metric("Havoc Avoidance", signed(advanced?.offHavoc, 3), "offHavoc"),
    ],
    defense: [
      metric("EPA / Play", signed(advanced?.epaAdjAllowed), "epaAdjAllowed"),
      metric("Pass EPA", signed(advanced?.passEpaAdjAllowed), "passEpaAdjAllowed"),
      metric("Rush EPA", signed(advanced?.rushEpaAdjAllowed), "rushEpaAdjAllowed"),
      metric("Success Rate Edge", pctEdge(advanced?.successAdjAllowed), "successAdjAllowed"),
      metric("Explosiveness", signed(advanced?.defExp, 3), "defExp"),
      metric("Havoc", signed(advanced?.defHavoc, 3), "defHavoc"),
    ],
  };
}
