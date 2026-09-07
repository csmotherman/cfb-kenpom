import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  const pathname = request.nextUrl.pathname;

  // Legacy premium JSON URLs used to resolve directly from /public. Keep the
  // URLs from becoming a bypass by rewriting them into entitlement-checked
  // server routes before static-file handling occurs.
  if (pathname.startsWith("/data/advanced/")) {
    const match = pathname.match(/^\/data\/advanced\/(\d{4})\.json$/);
    if (!match) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    const url = request.nextUrl.clone();
    url.pathname = `/api/premium/advanced/${match[1]}`;
    return NextResponse.rewrite(url);
  }

  if (pathname.startsWith("/data/predictions/")) {
    const match = pathname.match(/^\/data\/predictions\/(\d{4})-(\d{1,2})\.json$/);
    if (!match) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }
    const url = request.nextUrl.clone();
    url.pathname = `/api/premium/predictions/${match[1]}/${match[2]}`;
    return NextResponse.rewrite(url);
  }

  return updateSession(request);
}

export const config = {
  // Public rankings remain cache-friendly. Auth surfaces refresh Supabase
  // cookies, while premium static-looking paths are intercepted and routed
  // through the server entitlement checks above.
  matcher: [
    "/account/:path*",
    "/login",
    "/signup",
    "/auth/:path*",
    "/data/advanced/:path*",
    "/data/predictions/:path*",
  ],
};
