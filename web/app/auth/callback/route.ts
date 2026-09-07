import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : "/account";
}

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const flowId = request.nextUrl.searchParams.get("sb_flow_id");
  const next = safeNext(request.nextUrl.searchParams.get("next"));
  const redirectTo = request.nextUrl.clone();
  redirectTo.pathname = next;
  redirectTo.search = "";

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(
      code,
      flowId ? { flowId } : undefined
    );

    if (!error) {
      return NextResponse.redirect(redirectTo);
    }
  }

  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("error", "That confirmation link is invalid or has expired.");
  return NextResponse.redirect(loginUrl);
}
