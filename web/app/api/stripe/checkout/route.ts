import { NextResponse, type NextRequest } from "next/server";
import { EARLY_BETA_END_LABEL, isEarlyBetaActive } from "@/lib/earlyBeta";
import { createClient } from "@/lib/supabase/server";
import { getStripe } from "@/lib/stripe/server";
import {
  isPaidPlan,
  PAID_PLAN_LABELS,
  priceIdForPlan,
  stripeBillingConfigured,
} from "@/lib/stripe/plans";
import {
  attachStripeCustomerToUser,
  syncStripeSubscription,
} from "@/lib/stripe/sync";

export const runtime = "nodejs";

function safeReturnTo(value: FormDataEntryValue | null) {
  const path = String(value ?? "").trim();
  return path.startsWith("/") && !path.startsWith("//") ? path : "/account";
}

function feedbackRedirect(
  request: NextRequest,
  destination: string,
  key: "error" | "message" | "checkout",
  message: string
) {
  const url = new URL(destination, request.url);
  url.searchParams.set(key, message);
  return NextResponse.redirect(url, 303);
}

function siteOrigin(request: NextRequest) {
  const configured = process.env.NEXT_PUBLIC_SITE_URL?.trim().replace(/\/$/, "");
  return configured || request.nextUrl.origin;
}

function destinationWithPlan(request: NextRequest, destination: string, plan: string) {
  const url = new URL(destination, request.url);
  url.searchParams.set("plan", plan);
  return `${url.pathname}${url.search}`;
}

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const requestedPlan = String(formData.get("plan") ?? "");
  const returnTo = safeReturnTo(formData.get("return_to"));

  if (!isPaidPlan(requestedPlan)) {
    return feedbackRedirect(request, returnTo, "error", "Choose a valid LEILA Ratings plan.");
  }

  if (isEarlyBetaActive()) {
    return feedbackRedirect(
      request,
      returnTo,
      "message",
      `Early Beta Access is free through ${EARLY_BETA_END_LABEL}. Paid subscriptions open October 16.`
    );
  }

  if (!stripeBillingConfigured()) {
    return feedbackRedirect(
      request,
      returnTo,
      "error",
      "Paid checkout is not live yet. Stripe products, prices, and the verified webhook still need to be configured."
    );
  }

  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const claims = claimsData?.claims;
  const userId = claims?.sub;

  if (!userId) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("message", "Sign in to continue with the LEILA Ratings plan you selected.");
    loginUrl.searchParams.set("next", destinationWithPlan(request, returnTo, requestedPlan));
    return NextResponse.redirect(loginUrl, 303);
  }

  const [{ data: profile }, { data: localSubscription }] = await Promise.all([
    supabase
      .from("profiles")
      .select("email")
      .eq("id", userId)
      .maybeSingle(),
    supabase
      .from("subscriptions")
      .select("status,stripe_customer_id")
      .eq("user_id", userId)
      .maybeSingle(),
  ]);

  if (localSubscription?.status === "active" || localSubscription?.status === "trialing") {
    return feedbackRedirect(
      request,
      "/account",
      "message",
      "You already have LEILA Ratings access. Use Manage billing to change your plan."
    );
  }

  try {
    const stripe = getStripe();
    const priceId = priceIdForPlan(requestedPlan);
    const email =
      profile?.email ?? (typeof claims?.email === "string" ? claims.email : undefined);

    let customerId = localSubscription?.stripe_customer_id ?? null;

    if (!customerId) {
      const customer = await stripe.customers.create({
        email: email || undefined,
        metadata: { user_id: userId },
      });
      customerId = customer.id;
      await attachStripeCustomerToUser(userId, customerId);
    }

    const existingSubscriptions = await stripe.subscriptions.list({
      customer: customerId,
      status: "all",
      limit: 20,
    });

    const existingLiveSubscription = existingSubscriptions.data.find((subscription) =>
      ["active", "trialing", "past_due", "unpaid", "paused", "incomplete"].includes(
        subscription.status
      )
    );

    if (existingLiveSubscription) {
      await syncStripeSubscription(existingLiveSubscription);
      return feedbackRedirect(
        request,
        "/account",
        "message",
        "An existing Stripe subscription was found and synced to your LEILA Ratings account."
      );
    }

    const origin = siteOrigin(request);
    const cancelUrl = new URL(returnTo, origin);
    cancelUrl.searchParams.set("checkout", "canceled");
    cancelUrl.searchParams.set("plan", requestedPlan);

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer: customerId,
      client_reference_id: userId,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${origin}/account?checkout=success`,
      cancel_url: cancelUrl.toString(),
      allow_promotion_codes: process.env.STRIPE_ALLOW_PROMOTION_CODES === "true",
      metadata: {
        user_id: userId,
        plan: requestedPlan,
      },
      subscription_data: {
        metadata: {
          user_id: userId,
          plan: requestedPlan,
        },
      },
    });

    if (!session.url) {
      return feedbackRedirect(
        request,
        returnTo,
        "error",
        `Stripe could not start checkout for ${PAID_PLAN_LABELS[requestedPlan]}.`
      );
    }

    return NextResponse.redirect(session.url, 303);
  } catch (error) {
    console.error("LEILA Ratings Stripe checkout error", error);
    return feedbackRedirect(
      request,
      returnTo,
      "error",
      "Stripe checkout is not available yet. Billing configuration still needs to be completed."
    );
  }
}
