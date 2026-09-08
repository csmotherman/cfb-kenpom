import { NextResponse } from "next/server";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AdvancedSeason } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const HEADERS = {
  "Cache-Control": "public, max-age=60, s-maxage=300, stale-while-revalidate=600",
};

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ year: string }> }
) {
  const { year } = await params;

  if (!/^\d{4}$/.test(year)) {
    return NextResponse.json(
      { code: "INVALID_SEASON", message: "Invalid season." },
      { status: 400, headers: HEADERS }
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
        { status: 404, headers: HEADERS }
      );
    }

    return NextResponse.json(data.payload as AdvancedSeason, {
      status: 200,
      headers: HEADERS,
    });
  } catch (error) {
    console.error("Failed to read matchup advanced analytics", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Matchup analytics are temporarily unavailable." },
      { status: 500, headers: { "Cache-Control": "no-store" } }
    );
  }
}
