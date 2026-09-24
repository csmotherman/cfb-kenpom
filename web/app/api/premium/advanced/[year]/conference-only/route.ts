import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { computeSample, type AdvancedSampleArtifact, type ConferenceOnlySampleResponse } from "@/lib/custom-sample";
import { getPremiumDataset } from "@/lib/premiumDataset";
import type { AdvancedSeason } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const PRIVATE_HEADERS = { "Cache-Control": "private, max-age=300", Vary: "Cookie" };
const NO_STORE_HEADERS = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie" };

function isIndependent(conf: string | null | undefined): boolean {
  const value = (conf ?? "").trim().toLowerCase();
  return !value || value === "ind" || value.includes("independent");
}

export async function GET(_request: Request, { params }: { params: Promise<{ year: string }> }) {
  const { year } = await params;
  if (!/^\d{4}$/.test(year)) {
    return NextResponse.json({ code: "INVALID_REQUEST", message: "Invalid season." }, { status: 400, headers: NO_STORE_HEADERS });
  }

  const entitlements = await getCurrentEntitlements();
  if (!entitlements.userId) {
    return NextResponse.json({ code: "SIGN_IN_REQUIRED", message: "Sign in to access PRIME Advanced Analytics." }, { status: 401, headers: NO_STORE_HEADERS });
  }
  if (!entitlements.advanced) {
    return NextResponse.json(
      { code: "UPGRADE_REQUIRED", message: "PRIME Advanced or Advanced + Predictions is required for Advanced Analytics." },
      { status: 403, headers: NO_STORE_HEADERS },
    );
  }

  try {
    const seasonNumber = Number(year);
    const [artifact, season] = await Promise.all([
      getPremiumDataset<AdvancedSampleArtifact>("advanced", seasonNumber, 1),
      getPremiumDataset<AdvancedSeason>("advanced", seasonNumber, 0),
    ]);

    if (!artifact || !season) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "In-conference game samples are not available for this season yet." },
        { status: 404, headers: NO_STORE_HEADERS },
      );
    }

    const eligibleWeeks = season.weeks.filter((week) => week <= artifact.meta.weekThrough);
    const snapshotWeek = eligibleWeeks.length ? eligibleWeeks[eligibleWeeks.length - 1] : null;
    const rows = snapshotWeek === null ? [] : season.byWeek[String(snapshotWeek)] ?? [];
    const confByTeamId = new Map(rows.map((row) => [row.teamId, row.conf]));

    const teams: ConferenceOnlySampleResponse["teams"] = {};
    for (const team of Object.values(artifact.teams)) {
      const ownConf = confByTeamId.get(team.teamId);
      const gameIds = team.games
        .filter((game) => {
          if (game.oi === null || game.oi === undefined || !game.fbs || isIndependent(ownConf)) return false;
          const opponentConf = confByTeamId.get(game.oi);
          return Boolean(opponentConf) && opponentConf === ownConf;
        })
        .map((game) => game.g);

      teams[team.slug] = {
        gameIds,
        result: computeSample({ meta: artifact.meta, team }, new Set(gameIds)),
      };
    }

    const payload: ConferenceOnlySampleResponse = {
      season: seasonNumber,
      weekThrough: artifact.meta.weekThrough,
      teams,
    };

    return NextResponse.json(payload, { status: 200, headers: PRIVATE_HEADERS });
  } catch (error) {
    console.error("Failed to build in-conference Advanced samples", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "In-conference game filtering is temporarily unavailable." },
      { status: 500, headers: NO_STORE_HEADERS },
    );
  }
}
