import { NextResponse } from "next/server";
import { canonicalizeAdvancedSeason } from "@/lib/advanced-contract";
import { createAdminClient } from "@/lib/supabase/admin";
import type {
  AdvancedRow,
  AdvancedSeason,
  PublicMatchupAdvanced,
  PublicMatchupAdvancedMetric,
  PublicMatchupAdvancedMetricKey,
  RankingsSeason,
  ScheduleGame,
  ScheduleSeason,
} from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CACHE_HEADERS = {
  "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400",
};

const METRICS: PublicMatchupAdvancedMetricKey[] = [
  "epaAdj",
  "epaAdjAllowed",
  "passEpaAdj",
  "passEpaAdjAllowed",
  "rushEpaAdj",
  "rushEpaAdjAllowed",
  "passSuccessAdj",
  "passSuccessAdjAllowed",
  "rushSuccessAdj",
  "rushSuccessAdjAllowed",
];

function findGame(schedule: ScheduleSeason, gameId: string): ScheduleGame | null {
  for (const week of schedule.weeks) {
    const game = (schedule.byWeek[String(week)] ?? []).find((row) => String(row.gameId) === gameId);
    if (game) return game;
  }
  return null;
}

function pregameWeek(rankings: RankingsSeason, game: ScheduleGame): number | null {
  const prior = rankings.weeks.filter((week) => week < game.week);
  if (prior.length) return prior[prior.length - 1] ?? null;

  // Week 1 can have no true pregame PRIME snapshot. Mirror the matchup page's
  // existing fallback by using the earliest available current-season snapshot.
  return rankings.weeks[0] ?? null;
}

function metricValue(row: AdvancedRow, key: PublicMatchupAdvancedMetricKey): number | null {
  const value = row[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function metricFor(
  rows: AdvancedRow[],
  slug: string,
  key: PublicMatchupAdvancedMetricKey,
): PublicMatchupAdvancedMetric {
  const ranked = rows
    .map((row) => ({ slug: row.slug, value: metricValue(row, key) }))
    .filter((row): row is { slug: string; value: number } => row.value !== null)
    .sort((a, b) => b.value - a.value);

  const index = ranked.findIndex((row) => row.slug === slug);
  const team = rows.find((row) => row.slug === slug);

  return {
    value: team ? metricValue(team, key) : null,
    rank: index >= 0 ? index + 1 : null,
    total: ranked.length,
  };
}

async function loadCanonicalContext(request: Request, year: string) {
  const rankingsUrl = new URL(`/data/rankings/${year}.json`, request.url);
  const scheduleUrl = new URL(`/data/schedule/${year}.json`, request.url);
  const [rankingsResponse, scheduleResponse] = await Promise.all([
    fetch(rankingsUrl, { next: { revalidate: 3600 } }),
    fetch(scheduleUrl, { next: { revalidate: 3600 } }),
  ]);

  if (!rankingsResponse.ok || !scheduleResponse.ok) return null;

  return {
    rankings: (await rankingsResponse.json()) as RankingsSeason,
    schedule: (await scheduleResponse.json()) as ScheduleSeason,
  };
}

/**
 * Public matchup-only advanced slice.
 *
 * The full Advanced season remains premium. This endpoint intentionally emits
 * only the ten adjusted EPA/success metrics already shown on a public matchup
 * page, for the two teams in the requested game, plus their national rank for
 * those metrics. No raw weekly counts or other Advanced columns are exposed.
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ year: string; gameId: string }> },
) {
  const { year, gameId } = await params;

  if (!/^\d{4}$/.test(year) || !gameId) {
    return NextResponse.json({ code: "INVALID_REQUEST" }, { status: 400 });
  }

  try {
    const context = await loadCanonicalContext(request, year);
    if (!context) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });

    const game = findGame(context.schedule, gameId);
    if (!game) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });

    const week = pregameWeek(context.rankings, game);
    if (week === null) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });

    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload")
      .eq("dataset_type", "advanced")
      .eq("season", Number(year))
      .eq("week", 0)
      .maybeSingle();

    if (error) throw error;
    if (!data) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });

    const canonical = canonicalizeAdvancedSeason(
      data.payload as AdvancedSeason,
      context.rankings,
      context.schedule,
      year,
    );
    const rows = canonical.byWeek[String(week)] ?? [];

    const buildTeam = (slug: string) => ({
      slug,
      metrics: Object.fromEntries(
        METRICS.map((key) => [key, metricFor(rows, slug, key)]),
      ) as Record<PublicMatchupAdvancedMetricKey, PublicMatchupAdvancedMetric>,
    });

    const payload: PublicMatchupAdvanced = {
      season: Number(year),
      gameId,
      week,
      teams: {
        [game.awaySlug]: buildTeam(game.awaySlug),
        [game.homeSlug]: buildTeam(game.homeSlug),
      },
    };

    return NextResponse.json(payload, {
      status: 200,
      headers: {
        ...CACHE_HEADERS,
        "X-PRIME-Matchup-Advanced": "public-slice",
      },
    });
  } catch (error) {
    console.error("Failed to build public matchup advanced slice", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Matchup analytics are temporarily unavailable." },
      { status: 500 },
    );
  }
}
