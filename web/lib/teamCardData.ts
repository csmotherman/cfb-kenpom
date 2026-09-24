import { createAdminClient } from "@/lib/supabase/admin";
import { getTeamSnapshot } from "@/lib/seoData";
import { conferenceName, teamMascot } from "@/lib/teamMascots";
import { logoUrl } from "@/lib/teamCode";

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

type TeamCardAdvancedSlice = {
  week: number;
  row: Partial<Record<CardMetricKey, number | null>>;
  ranks: Partial<Record<CardMetricKey, number | null>>;
};

export async function getTeamCardData(slug: string): Promise<TeamCardData | null> {
  const snapshot = await getTeamSnapshot(slug);
  if (!snapshot?.latest || snapshot.year === null || snapshot.week === null) return null;

  const year = snapshot.year;
  const week = snapshot.week;
  let advanced: TeamCardAdvancedSlice | null = null;

  try {
    const admin = createAdminClient();
    const { data, error } = await admin.rpc("get_team_card_advanced", {
      p_season: year,
      p_week: week,
      p_slug: slug,
    });
    if (error) throw error;
    advanced = (data as TeamCardAdvancedSlice | null) ?? null;
  } catch {
    // The public identity/rating portion can still render if the advanced
    // dataset is temporarily unavailable.
  }

  const value = (key: CardMetricKey) => advanced?.row?.[key] ?? null;
  const rank = (key: CardMetricKey) => advanced?.ranks?.[key] ?? null;
  const metric = (label: string, formatted: string, key: CardMetricKey): TeamCardMetric => ({
    label,
    value: formatted,
    rank: rank(key),
  });

  return {
    slug,
    team: snapshot.entry.team,
    nickname: teamMascot(snapshot.entry.team) ?? "",
    teamId: snapshot.entry.teamId,
    logo: logoUrl(snapshot.entry.teamId, 256),
    year,
    week,
    record: snapshot.latest.record,
    conference: conferenceName(snapshot.entry.conf),
    primeRank: snapshot.prime25Rank,
    net: { value: signed(snapshot.latest.adjEM, 1), rank: snapshot.latest.rank },
    offenseRating: { value: signed(snapshot.latest.adjO, 1), rank: snapshot.latest.adjORank },
    defenseRating: { value: signed(snapshot.latest.adjD, 1), rank: snapshot.latest.adjDRank },
    strengthOfRecordRank: snapshot.latest.sorRank,
    strengthOfScheduleRank: snapshot.latest.sosRank,
    adjustedScoringMargin: {
      value: signed(value("asm"), 1),
      rank: rank("asm"),
    },
    offense: [
      metric("EPA / Play", signed(value("epaAdj")), "epaAdj"),
      metric("Pass EPA", signed(value("passEpaAdj")), "passEpaAdj"),
      metric("Rush EPA", signed(value("rushEpaAdj")), "rushEpaAdj"),
      metric("Success Rate Edge", pctEdge(value("successAdj")), "successAdj"),
      metric("Explosiveness", signed(value("offExp"), 3), "offExp"),
      metric("Havoc Avoidance", signed(value("offHavoc"), 3), "offHavoc"),
    ],
    defense: [
      metric("EPA / Play", signed(value("epaAdjAllowed")), "epaAdjAllowed"),
      metric("Pass EPA", signed(value("passEpaAdjAllowed")), "passEpaAdjAllowed"),
      metric("Rush EPA", signed(value("rushEpaAdjAllowed")), "rushEpaAdjAllowed"),
      metric("Success Rate Edge", pctEdge(value("successAdjAllowed")), "successAdjAllowed"),
      metric("Explosiveness", signed(value("defExp"), 3), "defExp"),
      metric("Havoc", signed(value("defHavoc"), 3), "defHavoc"),
    ],
  };
}
