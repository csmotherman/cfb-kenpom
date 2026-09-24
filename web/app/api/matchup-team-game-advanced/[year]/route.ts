import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { getPremiumDataset } from "@/lib/premiumDataset";
import type { TeamGameAdvancedSeason } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

const EMPTY_TEAM_GAME_ADVANCED_SEASON = (season: number): TeamGameAdvancedSeason => ({
  version: "",
  season,
  sourceVersions: {},
  fieldAvailabilityReasons: {},
  rows: [],
});

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

  // Matchup pages themselves remain public. The deeper single-game Advanced/
  // Exploratory breakdown used for a completed game's results view does not
  // -- same soft-degrade contract as /api/matchup-advanced: an empty but
  // shape-compatible payload for a signed-out or non-entitled visitor,
  // never a hard gate on the matchup page itself.
  const entitlements = await getCurrentEntitlements();
  if (!entitlements.advanced) {
    return NextResponse.json(EMPTY_TEAM_GAME_ADVANCED_SEASON(Number(year)), {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "X-PRIME-Advanced-Access": "none",
      },
    });
  }

  try {
    const payload = await getPremiumDataset<TeamGameAdvancedSeason>(
      "team_game_advanced",
      Number(year),
    );
    if (!payload) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Completed-game analytics are not published for this season." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }

    return NextResponse.json(payload, {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "X-PRIME-Advanced-Access": "full",
      },
    });
  } catch (error) {
    console.error("Failed to read matchup team-game-advanced analytics", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Completed-game analytics are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
