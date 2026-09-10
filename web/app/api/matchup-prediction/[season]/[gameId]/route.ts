import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { createAdminClient } from "@/lib/supabase/admin";
import type { PredictionGame, PredictionsWeek } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ season: string; gameId: string }> }
) {
  const { season, gameId } = await params;

  if (!/^\d{4}$/.test(season) || !gameId) {
    return NextResponse.json(
      { code: "INVALID_MATCHUP", message: "Invalid matchup." },
      { status: 400, headers: PRIVATE_HEADERS }
    );
  }

  try {
    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload,week")
      .eq("dataset_type", "predictions")
      .eq("season", Number(season))
      .order("week", { ascending: true });

    if (error) throw error;

    let prediction: PredictionGame | null = null;
    for (const row of data ?? []) {
      const published = row.payload as PredictionsWeek;
      const match = published.games?.find((game) => game.gameId === gameId);
      if (match) {
        prediction = match;
        break;
      }
    }

    // Do not advertise a locked pick for a game the model has not actually scored.
    if (!prediction) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "No prediction is published for this matchup." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }

    const entitlements = await getCurrentEntitlements();
    if (!entitlements.userId) {
      return NextResponse.json(
        { code: "SIGN_IN_REQUIRED", message: "LEILA Pro+ is required to reveal this prediction." },
        { status: 401, headers: PRIVATE_HEADERS }
      );
    }

    if (!entitlements.paidAccess || entitlements.plan !== "pro_plus") {
      return NextResponse.json(
        { code: "PRO_PLUS_REQUIRED", message: "Upgrade to LEILA Pro+ to reveal this prediction." },
        { status: 403, headers: PRIVATE_HEADERS }
      );
    }

    return NextResponse.json(prediction, {
      status: 200,
      headers: PRIVATE_HEADERS,
    });
  } catch (error) {
    console.error("Failed to read matchup prediction", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Prediction is temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
