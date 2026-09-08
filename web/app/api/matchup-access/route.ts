import { NextResponse } from "next/server";
import { getCurrentEntitlements } from "@/lib/auth/entitlements";

export const dynamic = "force-dynamic";

export async function GET() {
  const entitlements = await getCurrentEntitlements();
  const ultimate = entitlements.paidAccess && entitlements.plan === "pro_plus";

  return NextResponse.json(
    { ultimate },
    {
      headers: {
        "Cache-Control": "private, no-store, max-age=0",
      },
    }
  );
}
