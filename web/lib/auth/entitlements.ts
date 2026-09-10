import { isEarlyBetaActive } from "@/lib/earlyBeta";
import { createClient } from "@/lib/supabase/server";

export type SubscriptionPlan = "free" | "pro" | "pro_plus";
export type SubscriptionStatus =
  | "inactive"
  | "trialing"
  | "active"
  | "past_due"
  | "canceled";

export type Entitlements = {
  userId: string | null;
  plan: SubscriptionPlan;
  status: SubscriptionStatus;
  paidAccess: boolean;
  earlyBetaAccess: boolean;
  advanced: boolean;
  predictions: "none" | "full";
};

export async function getCurrentEntitlements(): Promise<Entitlements> {
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const userId = claimsData?.claims?.sub ?? null;

  if (!userId) {
    return {
      userId: null,
      plan: "free",
      status: "inactive",
      paidAccess: false,
      earlyBetaAccess: false,
      advanced: false,
      predictions: "none",
    };
  }

  const { data: subscription } = await supabase
    .from("subscriptions")
    .select("plan,status")
    .eq("user_id", userId)
    .maybeSingle();

  const plan = (subscription?.plan ?? "free") as SubscriptionPlan;
  const status = (subscription?.status ?? "inactive") as SubscriptionStatus;
  const paidAccess = status === "active" || status === "trialing";
  const earlyBetaAccess = isEarlyBetaActive();
  const subscribedToAdvanced = paidAccess && (plan === "pro" || plan === "pro_plus");
  const subscribedToPredictions = paidAccess && plan === "pro_plus";

  return {
    userId,
    plan,
    status,
    paidAccess,
    earlyBetaAccess,
    advanced: earlyBetaAccess || subscribedToAdvanced,
    predictions: earlyBetaAccess || subscribedToPredictions ? "full" : "none",
  };
}
