import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import type { PredictionsWeek } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
};

function proPredictionLimit() {
  const value = Number.parseInt(process.env.GRID_PRO_PREDICTION_LIMIT ?? "5", 10);
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
      { code: "SIGN_IN_REQUIRED", message: "Sign in to access GRID Predictions." },
      { status: 401, headers: PRIVATE_HEADERS }
    );
  }

  if (entitlements.predictions === "none") {
    return NextResponse.json(
      { code: "UPGRADE_REQUIRED", message: "A GRID paid plan is required for Predictions." },
      { status: 403, headers: PRIVATE_HEADERS }
    );
  }

  try {
    const filePath = path.join(
      process.cwd(),
      "public",
      "data",
      "predictions",
      `${season}-${week}.json`
    );
    const raw = await readFile(filePath, "utf8");
    const published = JSON.parse(raw) as PredictionsWeek;
    const totalGames = published.games.length;
    const isLimited = entitlements.predictions === "limited";
    const response: PredictionsWeek = isLimited
      ? { ...published, games: published.games.slice(0, proPredictionLimit()) }
      : published;

    return NextResponse.json(response, {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "X-GRID-Predictions-Access": entitlements.predictions,
        "X-GRID-Predictions-Total": String(totalGames),
      },
    });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Predictions are not published for this week." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }
    console.error("Failed to read protected predictions", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Predictions are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
