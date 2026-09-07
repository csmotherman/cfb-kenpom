import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/proxy";

export async function proxy(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  // Keep auth refresh off the public ratings/data routes so the existing
  // data-first experience keeps its current cache/performance behavior.
  matcher: ["/account/:path*", "/login", "/signup", "/auth/:path*"],
};
