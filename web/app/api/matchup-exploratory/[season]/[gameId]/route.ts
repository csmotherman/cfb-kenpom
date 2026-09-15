import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { createAdminClient } from "@/lib/supabase/admin";
import type { MatchupEdgesGame } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

type StoredMatchupSeason = {
  version: string;
  byGame: Record<string, MatchupEdgesGame>;
  // `models` (fitted coefficients per week) is intentionally never read here --
  // it is an internal audit artifact, not something a client response should
  // carry even to an entitled user.
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

  const entitlements = await getCurrentEntitlements();
  if (!entitlements.userId) {
    return NextResponse.json(
      { code: "SIGN_IN_REQUIRED", message: "Sign in to see LEILA's matchup edges." },
      { status: 401, headers: PRIVATE_HEADERS }
    );
  }
  // Matchup edges ride on the same entitlement as Exploratory -- a
  // research-stage sub-surface of Advanced, not a separate paid tier.
  if (!entitlements.advanced) {
    return NextResponse.json(
      {
        code: "UPGRADE_REQUIRED",
        message: "LEILA Advanced or Advanced + Predictions is required for matchup edges.",
      },
      { status: 403, headers: PRIVATE_HEADERS }
    );
  }

  try {
    const admin = createAdminClient();
    const { data, error } = await admin
      .from("premium_datasets")
      .select("payload")
      .eq("dataset_type", "exploratory_matchups")
      .eq("season", Number(season))
      .eq("week", 0)
      .maybeSingle();

    if (error) throw error;
    if (!data) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Matchup edges are not published for this season." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }

    const payload = data.payload as StoredMatchupSeason;
    const game = payload.byGame?.[gameId];
    if (!game) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "No matchup edges are published for this game." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }

    return NextResponse.json(game, {
      status: 200,
      headers: PRIVATE_HEADERS,
    });
  } catch (error) {
    console.error("Failed to read matchup edges", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Matchup edges are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
