import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getStripe } from "@/lib/stripe/server";

export const runtime = "nodejs";

function accountRedirect(request: NextRequest, key: "error" | "message", message: string) {
  const url = new URL("/account", request.url);
  url.searchParams.set(key, message);
  return NextResponse.redirect(url, 303);
}

function siteOrigin(request: NextRequest) {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "");
  return configured || request.nextUrl.origin;
}

export async function POST(request: NextRequest) {
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const userId = claimsData?.claims?.sub;

  if (!userId) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("message", "Sign in to manage GRID billing.");
    return NextResponse.redirect(loginUrl, 303);
  }

  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("stripe_customer_id")
    .eq("user_id", userId)
    .maybeSingle();

  if (!subscription?.stripe_customer_id) {
    return accountRedirect(
      request,
      "message",
      "No Stripe billing profile exists for this account yet."
    );
  }

  try {
    const stripe = getStripe();
    const portal = await stripe.billingPortal.sessions.create({
      customer: subscription.stripe_customer_id,
      return_url: `${siteOrigin(request)}/account`,
    });

    return NextResponse.redirect(portal.url, 303);
  } catch (error) {
    console.error("GRID Stripe portal error", error);
    return accountRedirect(
      request,
      "error",
      "The Stripe billing portal is not available yet."
    );
  }
}
