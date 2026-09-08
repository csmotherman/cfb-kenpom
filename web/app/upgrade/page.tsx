import type { Metadata } from "next";
import { redirect } from "next/navigation";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import UpgradeExperience, { type UpgradeFeature } from "@/components/UpgradeExperience";
import { createClient } from "@/lib/supabase/server";
import {
  configuredTrialDays,
  isPaidPlan,
  stripeBillingConfigured,
} from "@/lib/stripe/plans";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "GRID Pro | Advanced College Football Analytics",
  description:
    "Compare GRID Pro plans and unlock advanced college football research tools, custom week ranges, and weekly model access.",
};

type UpgradePageProps = {
  searchParams: Promise<{
    feature?: string;
    plan?: string;
    error?: string;
    message?: string;
    checkout?: string;
  }>;
};

function safeFeature(value: string | undefined): UpgradeFeature {
  if (value === "advanced" || value === "predictions" || value === "matchup") return value;
  return "general";
}

export default async function UpgradePage({ searchParams }: UpgradePageProps) {
  const params = await searchParams;
  const feature = safeFeature(params.feature);
  const selectedPlan = isPaidPlan(params.plan) ? params.plan : null;
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const userId = claimsData?.claims?.sub;

  let trialUsedAt: string | null = null;
  let subscription: { plan: string; status: string } | null = null;

  if (userId) {
    const [{ data: profile }, { data: subscriptionRow }] = await Promise.all([
      supabase
        .from("profiles")
        .select("trial_used_at")
        .eq("id", userId)
        .maybeSingle(),
      supabase
        .from("subscriptions")
        .select("plan,status")
        .eq("user_id", userId)
        .maybeSingle(),
    ]);
    trialUsedAt = profile?.trial_used_at ?? null;
    subscription = subscriptionRow ?? null;
  }

  const paidAccess =
    subscription &&
    subscription.plan !== "free" &&
    (subscription.status === "active" || subscription.status === "trialing");

  if (paidAccess) {
    redirect(
      "/account?message=" +
        encodeURIComponent(
          "You already have GRID access. Use Manage billing from your account to change plans."
        )
    );
  }

  const trialDays = configuredTrialDays();
  const trialEligible = userId ? trialDays > 0 && !trialUsedAt : null;
  const checkoutMessage =
    params.checkout === "canceled"
      ? "Checkout canceled. Nothing was charged. Your plan selection is still here."
      : params.message ?? null;

  return (
    <>
      <a className="skip-link" href="#upgradeContent">Skip to plans</a>
      <SiteHeader tagline="Advanced College Football Research" />
      <SiteNav />
      <main id="upgradeContent" className="container upgrade-main">
        <UpgradeExperience
          feature={feature}
          signedIn={Boolean(userId)}
          billingConfigured={stripeBillingConfigured()}
          trialDays={trialDays}
          trialEligible={trialEligible}
          selectedPlan={selectedPlan}
          message={checkoutMessage}
          error={params.error ?? null}
        />
      </main>
      <SiteFooter note="GRID keeps its core ratings and team profiles public. Paid plans are reserved for deeper research controls and forward-looking model products." />
    </>
  );
}
