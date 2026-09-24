import { teamGamesResponse } from "@/lib/teamGamesRoute";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// One team's per-game Exploratory counts for the "custom sample" feature
// (see scripts/export_exploratory_data.py and lib/teamGamesRoute.ts).
export async function GET(_request: Request, { params }: { params: Promise<{ year: string; teamId: string }> }) {
  const { year, teamId } = await params;
  return teamGamesResponse("exploratory", year, teamId);
}
