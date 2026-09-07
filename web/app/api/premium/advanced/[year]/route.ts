import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";

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
      { code: "SIGN_IN_REQUIRED", message: "Sign in to access GRID Advanced Analytics." },
      { status: 401, headers: PRIVATE_HEADERS }
    );
  }

  if (!entitlements.advanced) {
    return NextResponse.json(
      { code: "UPGRADE_REQUIRED", message: "GRID Pro or Pro+ is required for Advanced Analytics." },
      { status: 403, headers: PRIVATE_HEADERS }
    );
  }

  try {
    const filePath = path.join(
      process.cwd(),
      "public",
      "data",
      "advanced",
      `${year}.json`
    );
    const body = await readFile(filePath, "utf8");

    return new NextResponse(body, {
      status: 200,
      headers: {
        ...PRIVATE_HEADERS,
        "Content-Type": "application/json; charset=utf-8",
      },
    });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return NextResponse.json(
        { code: "NOT_FOUND", message: "Advanced analytics are not published for this season." },
        { status: 404, headers: PRIVATE_HEADERS }
      );
    }
    console.error("Failed to read protected advanced analytics", error);
    return NextResponse.json(
      { code: "DATA_UNAVAILABLE", message: "Advanced analytics are temporarily unavailable." },
      { status: 500, headers: PRIVATE_HEADERS }
    );
  }
}
