import { NextRequest, NextResponse } from "next/server";
import { promises as fs } from "node:fs";
import path from "node:path";

type RatingRow = {
  rank: number | null;
  team: string;
  teamId?: number | string;
  slug?: string;
  conf?: string | null;
  record?: string;
  adjEM: number | null;
  adjO: number | null;
  adjD: number | null;
  adjORank?: number | null;
  adjDRank?: number | null;
  sos: number | null;
  sosRank?: number | null;
  sor: number | null;
  sorRank?: number | null;
};

type RankingsSeason = {
  season?: number;
  weeks: number[];
  byWeek: Record<string, RatingRow[]>;
};

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams;
  const seasonParam = params.get("season") ?? "2026";
  const season = Number(seasonParam);

  if (!Number.isInteger(season) || season < 1900 || season > 2100) {
    return NextResponse.json({ error: "Invalid season" }, { status: 400 });
  }

  const filePath = path.join(process.cwd(), "public", "data", "rankings", `${season}.json`);

  let data: RankingsSeason;
  try {
    data = JSON.parse(await fs.readFile(filePath, "utf8")) as RankingsSeason;
  } catch {
    return NextResponse.json({ error: `Ratings not found for season ${season}` }, { status: 404 });
  }

  if (!Array.isArray(data.weeks) || data.weeks.length === 0) {
    return NextResponse.json({ error: `No ratings available for season ${season}` }, { status: 404 });
  }

  const requestedWeek = params.get("week");
  const week = requestedWeek === null
    ? data.weeks[data.weeks.length - 1]
    : Number(requestedWeek);

  if (!Number.isInteger(week) || !data.byWeek?.[String(week)]) {
    return NextResponse.json(
      { error: `Ratings not found for season ${season}, week ${requestedWeek}`, available_weeks: data.weeks },
      { status: 404 }
    );
  }

  const ratings = data.byWeek[String(week)]
    .map((row) => ({
      rank: row.rank,
      team: row.team,
      team_id: row.teamId ?? null,
      slug: row.slug ?? null,
      conference: row.conf ?? null,
      record: row.record ?? null,
      rating: row.adjEM,
      net_apr: row.adjEM,
      off_apr: row.adjO,
      off_apr_rank: row.adjORank ?? null,
      def_apr: row.adjD,
      def_apr_rank: row.adjDRank ?? null,
      sos: row.sos,
      sos_rank: row.sosRank ?? null,
      sor: row.sor,
      sor_rank: row.sorRank ?? null,
    }))
    .sort((a, b) => (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER));

  return NextResponse.json(
    {
      source: "PRIME CFB",
      methodology: "APR (Adjusted Possession Rating)",
      season,
      week,
      available_weeks: data.weeks,
      count: ratings.length,
      ratings,
    },
    {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, s-maxage=300, stale-while-revalidate=3600",
      },
    }
  );
}
