import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";
import { createAdminClient } from "@/lib/supabase/admin";
import type { SampleMeta, SampleTeam } from "@/lib/custom-sample";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// One team's per-game ingredients for the Advanced "custom sample" feature
// (see scripts/custom_sample.py). The season artifact lives in premium_datasets
// as dataset_type='advanced', week=1 -- a multi-megabyte JSON -- so this route
// NEVER pulls it whole: PostgREST extracts `meta` and the one requested team
// inside Postgres and only that slice (~10 KB) crosses the wire. If that path
// select is ever rejected, a short-lived in-memory cache keeps the fallback (a
// full read) to at most one per instance per TTL instead of one per click.
const PRIVATE_HEADERS = {
  "Cache-Control": "private, max-age=300",
  Vary: "Cookie",
};
const NO_STORE_HEADERS = { "Cache-Control": "private, no-store, max-age=0", Vary: "Cookie" };
const FALLBACK_TTL_MS = 10 * 60 * 1000;
const fallbackCache = new Map<number, { at: number; payload: { meta: SampleMeta; teams: Record<string, SampleTeam> } }>();

type Slice = { meta: SampleMeta | null; team: SampleTeam | null };

async function readSlice(season: number, teamId: string): Promise<Slice | null> {
  const admin = createAdminClient();
  const base = admin.from("premium_datasets").select(`meta:payload->meta,team:payload->teams->t${teamId}`);
  const narrow = await base.eq("dataset_type", "advanced").eq("season", season).eq("week", 1).maybeSingle();
  if (!narrow.error) return narrow.data ? (narrow.data as unknown as Slice) : null;

  console.warn("Custom-sample path select failed; using cached full read", narrow.error.message);
  const cached = fallbackCache.get(season);
  if (cached && Date.now() - cached.at < FALLBACK_TTL_MS) {
    return { meta: cached.payload.meta, team: cached.payload.teams[`t${teamId}`] ?? null };
  }
  const full = await admin
    .from("premium_datasets")
    .select("payload")
    .eq("dataset_type", "advanced")
    .eq("season", season)
    .eq("week", 1)
    .maybeSingle();
  if (full.error) throw full.error;
  if (!full.data) return null;
  const payload = full.data.payload as { meta: SampleMeta; teams: Record<string, SampleTeam> };
  fallbackCache.set(season, { at: Date.now(), payload });
  return { meta: payload.meta, team: payload.teams[`t${teamId}`] ?? null };
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ year: string; teamId: string }> },
) {
  const { year, teamId } = await params;
  if (!/^\d{4}$/.test(year) || !/^\d{1,6}$/.test(teamId)) {
    return NextResponse.json({ code: "INVALID_REQUEST", message: "Invalid season or team." }, { status: 400, headers: NO_STORE_HEADERS });
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
    const slice = await readSlice(Number(year), teamId);
    if (!slice?.meta || !slice.team) {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Custom game samples are not available for this team and season yet." },
        { status: 404, headers: NO_STORE_HEADERS },
      );
    }
    return NextResponse.json({ meta: slice.meta, team: slice.team }, { status: 200, headers: PRIVATE_HEADERS });
  } catch (error) {
    console.error("Failed to read custom-sample data", error);
    return NextResponse.json({ code: "DATA_UNAVAILABLE", message: "Custom game samples are temporarily unavailable." }, { status: 500, headers: NO_STORE_HEADERS });
  }
}
