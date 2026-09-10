import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AdvancedSeason } from "@/lib/types";

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

    return NextResponse.json(data.payload as AdvancedSeason, {
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
