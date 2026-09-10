import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { createAdminClient } from "@/lib/supabase/admin";
import type { PredictionsWeek } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

function proPredictionLimit() {
  const value = Number.parseInt(process.env.LEILA_PRO_PREDICTION_LIMIT ?? "5", 10);
  if (!Number.isFinite(value) || value < 1) return 5;
  return Math.min(value, 50);
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ season: string; week: string }> }
) {
  const { season, week } = await params;

  if (!/^\d{4}$/.test(season) || !/^\d{1,2}$/.test(week)) {
    return NextResponse.json(
      { code: "INVALID_WEEK", message: "Invalid predictions week." },
      { status: 400, headers: PRIVATE_HEADERS }
    );
  }

  const entitlements = await getCurrentEntitlements();

  if (!entitlements.userId) {
    return NextResponse.json(
      { code: "SIGN_IN_REQUIRED", message: "Sign in to access LEILA Ratings Predictions." },
      { status: 401, headers: PRIVATE_HEADERS }
    );
  }

  if (entitlements.predictions === "none") {
    return NextResponse.json(
      { code: "UPGRADE_REQUIRED", message: "A LEILA Ratings paid plan is required for Predictions." },
      { status: 403, headers: PRIVATE_HEADERS }
    );
  }

  try {
    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload")
      .eq("dataset_type", "predictions")
      .eq("season", Number(season))
      .eq("week", Number(week))
      .maybeSingle();

    if (error) throw error;
    if (!data) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Predictions are not published for this week." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }

    const published = data.payload as PredictionsWeek;
    const totalGames = published.games.length;
    const isLimited = entitlements.predictions === "limited";
    const response: PredictionsWeek = {
      ...published,
      games: isLimited
        ? published.games.slice(0, proPredictionLimit())
        : published.games,
      access: isLimited ? "limited" : "full",
      totalGames,
    };

    return NextResponse.json(response, {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "X-LEILA Ratings-Predictions-Access": entitlements.predictions,
        "X-LEILA Ratings-Predictions-Total": String(totalGames),
      },
    });
  } catch (error) {
    console.error("Failed to read private predictions", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Predictions are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
