import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { canonicalizeAdvancedSeason } from "@/lib/advanced-contract";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AdvancedSeason, RankingsSeason, ScheduleSeason } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

const EMPTY_ADVANCED_SEASON: AdvancedSeason = {
  weeks: [],
  weekLabels: {},
  byWeek: {},
};

async function loadCanonicalContext(request: Request, year: string) {
  const rankingsUrl = new URL(`/data/rankings/${year}.json`, request.url);
  const scheduleUrl = new URL(`/data/schedule/${year}.json`, request.url);
  const [rankingsResponse, scheduleResponse] = await Promise.all([
    fetch(rankingsUrl, { cache: "no-store" }),
    fetch(scheduleUrl, { cache: "no-store" }),
  ]);

  if (!rankingsResponse.ok) {
    throw new Error(`Failed to load canonical rankings for ${year}: ${rankingsResponse.status}`);
  }
  if (!scheduleResponse.ok && scheduleResponse.status !== 404) {
    throw new Error(`Failed to load canonical schedule for ${year}: ${scheduleResponse.status}`);
  }

  return {
    rankings: (await rankingsResponse.json()) as RankingsSeason,
    schedule: scheduleResponse.ok ? ((await scheduleResponse.json()) as ScheduleSeason) : null,
  };
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ year: string }> }
) {
  const { year } = await params;

  if (!/^\d{4}$/.test(year)) {
    return NextResponse.json(
      { code: "INVALID_SEASON", message: "Invalid season." },
      { status: 400, headers: PRIVATE_HEADERS }
    );
  }

  // Matchup pages themselves remain public. The deeper Advanced dataset used
  // to enrich them does not. Returning an empty compatible payload lets the
  // public matchup experience degrade to its free stats without leaking the
  // full premium season dataset or turning a basic matchup into a hard gate.
  const entitlements = await getCurrentEntitlements();
  if (!entitlements.advanced) {
    return NextResponse.json(EMPTY_ADVANCED_SEASON, {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "X-LEILA-Advanced-Access": "none",
      },
    });
  }

  try {
    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload")
      .eq("dataset_type", "advanced")
      .eq("season", Number(year))
      .eq("week", 0)
      .maybeSingle();

    if (error) throw error;
    if (!data) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Advanced analytics are not published for this season." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }

    const advanced = data.payload as AdvancedSeason;
    const { rankings, schedule } = await loadCanonicalContext(_request, year);
    const canonical = canonicalizeAdvancedSeason(advanced, rankings, schedule, year);

    return NextResponse.json(canonical, {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "X-LEILA-Advanced-Access": "full",
      },
    });
  } catch (error) {
    console.error("Failed to read matchup advanced analytics", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Matchup analytics are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
