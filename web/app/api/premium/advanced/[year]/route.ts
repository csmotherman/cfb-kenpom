import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AdvancedSeason, RankingsSeason } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store, max-age=0",
  Vary: "Cookie",
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

  const entitlements = await getCurrentEntitlements();

  if (!entitlements.userId) {
    return NextResponse.json(
      { code: "SIGN_IN_REQUIRED", message: "Sign in to access LEILA Ratings Advanced Analytics." },
      { status: 401, headers: PRIVATE_HEADERS }
    );
  }

  if (!entitlements.advanced) {
    return NextResponse.json(
      { code: "UPGRADE_REQUIRED", message: "LEILA Pro or Pro+ is required for Advanced Analytics." },
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

    // Ratings are the single source of truth for the three headline ratings.
    // Merge those public snapshots into the premium Advanced payload so every
    // page shows the exact same values and national ranks.
    const rankingsUrl = new URL(`/data/rankings/${year}.json`, _request.url);
    const rankingsResponse = await fetch(rankingsUrl, { cache: "no-store" });
    if (!rankingsResponse.ok) {
      throw new Error(`Failed to load canonical rankings for ${year}: ${rankingsResponse.status}`);
    }
    const rankings = (await rankingsResponse.json()) as RankingsSeason;

    if (
      advanced.weeks.length !== rankings.weeks.length ||
      advanced.weeks.some((week, index) => week !== rankings.weeks[index])
    ) {
      throw new Error(`Advanced/rankings week mismatch for ${year}`);
    }

    const byWeek = Object.fromEntries(
      advanced.weeks.map((week) => {
        const key = String(week);
        const ratingRows = rankings.byWeek[key] ?? [];
        const ratingsBySlug = new Map(ratingRows.map((row) => [row.slug, row]));
        const advancedRows = advanced.byWeek[key] ?? [];

        if (
          advancedRows.length !== ratingRows.length ||
          advancedRows.some((row) => !ratingsBySlug.has(row.slug))
        ) {
          throw new Error(`Advanced/rankings team coverage mismatch for ${year} week ${week}`);
        }

        return [
          key,
          advancedRows.map((row) => {
            const rating = ratingsBySlug.get(row.slug)!;
            return {
              ...row,
              adjEM: rating.adjEM,
              adjO: rating.adjO,
              adjD: rating.adjD,
              rank: rating.rank,
              adjORank: rating.adjORank,
              adjDRank: rating.adjDRank,
            };
          }),
        ];
      })
    );

    return NextResponse.json({ ...advanced, byWeek } as AdvancedSeason, {
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
