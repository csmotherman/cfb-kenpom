export type PaidPlan = "pro" | "pro_plus";

export const PAID_PLAN_LABELS: Record<PaidPlan, string> = {
  pro: "GRID Pro",
  pro_plus: "GRID Pro+",
};

export const PAID_PLAN_MONTHLY_PRICE: Record<PaidPlan, string> = {
  pro: "$0.99/month",
  pro_plus: "$4.99/month",
};

export function isPaidPlan(value: unknown): value is PaidPlan {
  return value === "pro" || value === "pro_plus";
}

export function priceIdForPlan(plan: PaidPlan) {
  const priceId =
    plan === "pro"
      ? process.env.STRIPE_PRO_PRICE_ID
      : process.env.STRIPE_PRO_PLUS_PRICE_ID;

  if (!priceId) {
    throw new Error(`Missing Stripe price ID for ${PAID_PLAN_LABELS[plan]}.`);
  }

  return priceId;
}

export function planForPriceId(priceId: string | null | undefined): PaidPlan | null {
  if (!priceId) return null;
  if (priceId === process.env.STRIPE_PRO_PRICE_ID) return "pro";
  if (priceId === process.env.STRIPE_PRO_PLUS_PRICE_ID) return "pro_plus";
  return null;
}

export function configuredTrialDays() {
  const parsed = Number.parseInt(process.env.STRIPE_TRIAL_DAYS ?? "7", 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return 0;
  return Math.min(parsed, 730);
}

export function stripeBillingConfigured() {
  return Boolean(
    process.env.STRIPE_SECRET_KEY &&
      process.env.STRIPE_WEBHOOK_SECRET &&
      process.env.STRIPE_PRO_PRICE_ID &&
      process.env.STRIPE_PRO_PLUS_PRICE_ID &&
      (process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY)
  );
}
