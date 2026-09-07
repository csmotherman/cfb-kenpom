import { NextResponse, type NextRequest } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { getStripe } from "@/lib/stripe/server";
import {
  configuredTrialDays,
  isPaidPlan,
  PAID_PLAN_LABELS,
  priceIdForPlan,
} from "@/lib/stripe/plans";
import {
  attachStripeCustomerToUser,
  syncStripeSubscription,
} from "@/lib/stripe/sync";

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
  const formData = await request.formData();
  const requestedPlan = String(formData.get("plan") ?? "");

  if (!isPaidPlan(requestedPlan)) {
    return accountRedirect(request, "error", "Choose a valid GRID plan.");
  }

  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const claims = claimsData?.claims;
  const userId = claims?.sub;

  if (!userId) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("message", "Sign in before starting GRID billing.");
    return NextResponse.redirect(loginUrl, 303);
  }

  const [{ data: profile }, { data: localSubscription }] = await Promise.all([
    supabase
      .from("profiles")
      .select("email,trial_used_at")
      .eq("id", userId)
      .maybeSingle(),
    supabase
      .from("subscriptions")
      .select("status,stripe_customer_id")
      .eq("user_id", userId)
      .maybeSingle(),
  ]);

  if (localSubscription?.status === "active" || localSubscription?.status === "trialing") {
    return accountRedirect(
      request,
      "message",
      "You already have GRID access. Use Manage billing to change your plan."
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
      return accountRedirect(
        request,
        "message",
        "An existing Stripe subscription was found and synced to your GRID account."
      );
    }

    const eligibleForTrial =
      !profile?.trial_used_at && existingSubscriptions.data.length === 0;
    const trialDays = eligibleForTrial ? configuredTrialDays() : 0;
    const origin = siteOrigin(request);

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer: customerId,
      client_reference_id: userId,
      line_items: [{ price: priceId, quantity: 1 }],
      success_url: `${origin}/account?checkout=success`,
      cancel_url: `${origin}/account?checkout=canceled`,
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
        ...(trialDays > 0 ? { trial_period_days: trialDays } : {}),
      },
    });

    if (!session.url) {
      return accountRedirect(
        request,
        "error",
        `Stripe could not start checkout for ${PAID_PLAN_LABELS[requestedPlan]}.`
      );
    }

    return NextResponse.redirect(session.url, 303);
  } catch (error) {
    console.error("GRID Stripe checkout error", error);
    return accountRedirect(
      request,
      "error",
      "Stripe checkout is not available yet. Billing configuration still needs to be completed."
    );
  }
}
