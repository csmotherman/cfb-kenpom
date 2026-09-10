import type { Metadata } from "next";
import { redirect } from "next/navigation";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import UpgradeExperience, { type UpgradeFeature } from "@/components/UpgradeExperience";
import { EARLY_BETA_END_LABEL, isEarlyBetaActive } from "@/lib/earlyBeta";
import { createClient } from "@/lib/supabase/server";
import {
  isPaidPlan,
  stripeBillingConfigured,
} from "@/lib/stripe/plans";

export const dynamic = "force-dynamic";

export function generateMetadata(): Metadata {
  if (isEarlyBetaActive()) {
    return {
      title: "Early Beta Access | LEILA Ratings",
      description:
        "Use LEILA Advanced Analytics and Predictions free during Early Beta, then choose Advanced or Advanced + Predictions beginning October 16, 2026.",
    };
  }

  return {
    title: "Plans | LEILA Ratings",
    description:
      "Compare LEILA Advanced at $1.99 per month with LEILA Advanced + Predictions at $4.99 per month.",
  };
}

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
  const earlyBetaActive = isEarlyBetaActive();
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const userId = claimsData?.claims?.sub;

  let subscription: { plan: string; status: string } | null = null;

  if (userId) {
    const { data: subscriptionRow } = await supabase
      .from("subscriptions")
      .select("plan,status")
      .eq("user_id", userId)
      .maybeSingle();
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
          "You already have LEILA Ratings access. Use Manage billing from your account to change plans."
        )
    );
  }

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
          earlyBetaActive={earlyBetaActive}
          earlyBetaEndLabel={EARLY_BETA_END_LABEL}
          selectedPlan={selectedPlan}
          message={checkoutMessage}
          error={params.error ?? null}
        />
      </main>
      <SiteFooter note="Core LEILA ratings remain free. Early Beta includes premium features through October 15, 2026; paid Advanced plans begin October 16." />
    </>
  );
}
