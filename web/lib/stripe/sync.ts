import type Stripe from "stripe";
import { createAdminClient } from "@/lib/supabase/admin";
import { isPaidPlan, planForPriceId } from "./plans";

export type LocalSubscriptionStatus =
  | "inactive"
  | "trialing"
  | "active"
  | "past_due"
  | "canceled";

function stripeObjectId(value: string | { id: string } | null | undefined) {
  if (!value) return null;
  return typeof value === "string" ? value : value.id;
}

function timestampToIso(value: number | null | undefined) {
  return value ? new Date(value * 1000).toISOString() : null;
}

function localStatus(status: Stripe.Subscription.Status): LocalSubscriptionStatus {
  if (status === "active") return "active";
  if (status === "trialing") return "trialing";
  if (status === "past_due") return "past_due";
  if (status === "canceled") return "canceled";
  return "inactive";
}

async function resolveUserId(subscription: Stripe.Subscription) {
  const metadataUserId = subscription.metadata?.user_id;
  if (metadataUserId) return metadataUserId;

  const admin = createAdminClient();
  const customerId = stripeObjectId(subscription.customer);

  const { data: bySubscription } = await admin
    .from("subscriptions")
    .select("user_id")
    .eq("stripe_subscription_id", subscription.id)
    .maybeSingle();

  if (bySubscription?.user_id) return bySubscription.user_id as string;

  if (customerId) {
    const { data: byCustomer } = await admin
      .from("subscriptions")
      .select("user_id")
      .eq("stripe_customer_id", customerId)
      .maybeSingle();

    if (byCustomer?.user_id) return byCustomer.user_id as string;
  }

  return null;
}

export async function syncStripeSubscription(subscription: Stripe.Subscription) {
  const admin = createAdminClient();
  const userId = await resolveUserId(subscription);
  if (!userId) return false;

  const customerId = stripeObjectId(subscription.customer);
  const firstItem = subscription.items.data[0];
  const priceId = firstItem?.price?.id ?? null;
  const metadataPlan = isPaidPlan(subscription.metadata?.plan)
    ? subscription.metadata.plan
    : null;

  const { data: existing } = await admin
    .from("subscriptions")
    .select("plan")
    .eq("user_id", userId)
    .maybeSingle();

  const existingPlan = isPaidPlan(existing?.plan) ? existing.plan : null;
  const plan = planForPriceId(priceId) ?? metadataPlan ?? existingPlan ?? "free";
  const now = new Date().toISOString();

  const { error } = await admin.from("subscriptions").upsert(
    {
      user_id: userId,
      plan,
      status: localStatus(subscription.status),
      stripe_customer_id: customerId,
      stripe_subscription_id: subscription.id,
      stripe_price_id: priceId,
      trial_start: timestampToIso(subscription.trial_start),
      trial_end: timestampToIso(subscription.trial_end),
      current_period_end: timestampToIso(firstItem?.current_period_end),
      cancel_at_period_end: subscription.cancel_at_period_end,
      updated_at: now,
    },
    { onConflict: "user_id" }
  );

  if (error) throw error;

  if (subscription.status === "trialing") {
    const { error: trialError } = await admin
      .from("profiles")
      .update({ trial_used_at: now, updated_at: now })
      .eq("id", userId)
      .is("trial_used_at", null);

    if (trialError) throw trialError;
  }

  return true;
}

export async function attachStripeCustomerToUser(userId: string, customerId: string) {
  const admin = createAdminClient();
  const { error } = await admin.from("subscriptions").upsert(
    {
      user_id: userId,
      stripe_customer_id: customerId,
      updated_at: new Date().toISOString(),
    },
    { onConflict: "user_id" }
  );

  if (error) throw error;
}
