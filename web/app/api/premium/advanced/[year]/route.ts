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

  const entitlements = await getCurrentEntitlements();

  if (!entitlements.userId) {
    return NextResponse.json(
      { code: "SIGN_IN_REQUIRED", message: "Sign in to access LEILA Advanced Analytics." },
      { status: 401, headers: PRIVATE_HEADERS }
    );
  }

  if (!entitlements.advanced) {
    return NextResponse.json(
      {
        code: "UPGRADE_REQUIRED",
        message: "LEILA Advanced or Advanced + Predictions is required for Advanced Analytics.",
      },
      { status: 403, headers: PRIVATE_HEADERS }
    );
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
      headers: PRIVATE_HEADERS,
    });
  } catch (error) {
    console.error("Failed to read private advanced analytics", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Advanced analytics are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
