import type { Metadata } from "next";
import { redirect } from "next/navigation";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import { updateDisplayName } from "@/app/auth/actions";
import { createClient } from "@/lib/supabase/server";
import {
  configuredTrialDays,
  PAID_PLAN_MONTHLY_PRICE,
  stripeBillingConfigured,
} from "@/lib/stripe/plans";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Account | LEILA Ratings",
  robots: { index: false, follow: false },
};

type AccountPageProps = {
  searchParams: Promise<{
    error?: string;
    message?: string;
    checkout?: string;
  }>;
};

function planLabel(plan: string) {
  if (plan === "pro_plus") return "LEILA Pro+";
  if (plan === "pro") return "LEILA Pro";
  return "Free";
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export default async function AccountPage({ searchParams }: AccountPageProps) {
  const params = await searchParams;
  const supabase = await createClient();
  const { data: claimsData } = await supabase.auth.getClaims();
  const claims = claimsData?.claims;
  const userId = claims?.sub;

  if (!userId) {
    redirect("/login?message=Sign%20in%20to%20manage%20your%20GRID%20account.");
  }

  const [{ data: profile }, { data: subscription }] = await Promise.all([
    supabase
      .from("profiles")
      .select("display_name,email,trial_used_at")
      .eq("id", userId)
      .maybeSingle(),
    supabase
      .from("subscriptions")
      .select(
        "plan,status,stripe_customer_id,stripe_subscription_id,trial_end,current_period_end,cancel_at_period_end"
      )
      .eq("user_id", userId)
      .maybeSingle(),
  ]);

  const plan = subscription?.plan ?? "free";
  const status = subscription?.status ?? "inactive";
  const paidAccess = status === "active" || status === "trialing";
  const advancedAccess = paidAccess && plan !== "free";
  const predictionAccess = !paidAccess
    ? "Locked"
    : plan === "pro_plus"
      ? "All predictions"
      : plan === "pro"
        ? "Limited predictions"
        : "Locked";
  const email = profile?.email ?? (typeof claims?.email === "string" ? claims.email : "");
  const displayName = profile?.display_name ?? "";
  const billingConfigured = stripeBillingConfigured();
  const trialDays = configuredTrialDays();
  const trialEligible = trialDays > 0 && !profile?.trial_used_at;
  const canStartCheckout = status === "inactive" || status === "canceled";
  const canManageBilling = Boolean(
    billingConfigured && subscription?.stripe_customer_id
  );

  const checkoutMessage =
    params.checkout === "success"
      ? "Stripe checkout completed. Your LEILA Ratings access will sync from the verified Stripe webhook."
      : params.checkout === "canceled"
        ? "Checkout canceled. Nothing was charged."
        : null;

  return (
    <>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />
      <main className="auth-main account-main">
        <div className="auth-shell account-shell">
          <section className="auth-panel account-panel" aria-labelledby="accountTitle">
            <div className="account-heading">
              <div>
                <span className="eyebrow auth-kicker">LEILA Ratings Account</span>
                <h1 id="accountTitle" className="auth-title">Your account</h1>
              </div>
              <span className={`account-plan account-plan--${plan}`}>{planLabel(plan)}</span>
            </div>

            {params.error ? <p className="auth-alert auth-alert--error">{params.error}</p> : null}
            {params.message ? <p className="auth-alert auth-alert--success">{params.message}</p> : null}
            {checkoutMessage ? <p className="auth-alert auth-alert--success">{checkoutMessage}</p> : null}

            <dl className="account-details">
              <div>
                <dt>Email</dt>
                <dd>{email}</dd>
              </div>
              <div>
                <dt>Subscription</dt>
                <dd>{planLabel(plan)}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  {status === "inactive"
                    ? "Free account"
                    : subscription?.cancel_at_period_end && status === "active"
                      ? "Active · cancels at period end"
                      : status.replaceAll("_", " ")}
                </dd>
              </div>
              {subscription?.trial_end ? (
                <div>
                  <dt>Trial ends</dt>
                  <dd>{formatDate(subscription.trial_end)}</dd>
                </div>
              ) : subscription?.current_period_end ? (
                <div>
                  <dt>Current period ends</dt>
                  <dd>{formatDate(subscription.current_period_end)}</dd>
                </div>
              ) : null}
            </dl>

            <div className="account-section">
              <h2>Profile</h2>
              <form className="account-profile-form" action={updateDisplayName}>
                <label className="auth-field">
                  <span>Display name</span>
                  <input
                    name="display_name"
                    type="text"
                    autoComplete="name"
                    defaultValue={displayName}
                    maxLength={80}
                    placeholder="Your name"
                  />
                </label>
                <button className="auth-button auth-button--secondary" type="submit">Save</button>
              </form>
            </div>

            <div className="account-section">
              <div className="account-section__heading">
                <h2>Access</h2>
                <span>Access levels are synced from Stripe into your LEILA Ratings account.</span>
              </div>
              <div className="entitlement-list">
                <div className="entitlement-row">
                  <div><strong>AdjNet Ratings</strong><span>Core opponent-adjusted ratings</span></div>
                  <b className="entitlement-state entitlement-state--on">Included</b>
                </div>
                <div className="entitlement-row">
                  <div><strong>Advanced Analytics</strong><span>Expanded team and efficiency metrics</span></div>
                  <b className={advancedAccess ? "entitlement-state entitlement-state--on" : "entitlement-state"}>
                    {advancedAccess ? "Unlocked" : "Locked"}
                  </b>
                </div>
                <div className="entitlement-row">
                  <div><strong>Predictions</strong><span>Weekly model projections</span></div>
                  <b className={predictionAccess !== "Locked" ? "entitlement-state entitlement-state--on" : "entitlement-state"}>
                    {predictionAccess}
                  </b>
                </div>
              </div>
            </div>

            <div className="account-section">
              <div className="account-section__heading">
                <h2>Billing</h2>
                <span>Secure checkout and subscription management are hosted by Stripe.</span>
              </div>

              {canStartCheckout ? (
                <div className="billing-plan-grid">
                  <article className="billing-plan-card">
                    <div>
                      <span className="billing-plan-card__eyebrow">LEILA Pro</span>
                      <h3>Advanced analytics</h3>
                      <p>Unlock the advanced team analytics table plus limited weekly predictions.</p>
                      <strong className="billing-plan-card__price">
                        {trialEligible ? `${trialDays} days free, then ` : ""}{PAID_PLAN_MONTHLY_PRICE.pro}
                      </strong>
                    </div>
                    <form action="/api/stripe/checkout" method="post">
                      <input type="hidden" name="plan" value="pro" />
                      <button className="auth-button billing-button" type="submit" disabled={!billingConfigured}>
                        Start LEILA Pro
                      </button>
                    </form>
                  </article>

                  <article className="billing-plan-card billing-plan-card--plus">
                    <div>
                      <span className="billing-plan-card__eyebrow">LEILA Pro+</span>
                      <h3>Full model access</h3>
                      <p>Everything in LEILA Pro plus complete access to weekly model predictions.</p>
                      <strong className="billing-plan-card__price">
                        {trialEligible ? `${trialDays} days free, then ` : ""}{PAID_PLAN_MONTHLY_PRICE.pro_plus}
                      </strong>
                    </div>
                    <form action="/api/stripe/checkout" method="post">
                      <input type="hidden" name="plan" value="pro_plus" />
                      <button className="auth-button billing-button" type="submit" disabled={!billingConfigured}>
                        Start LEILA Pro+
                      </button>
                    </form>
                  </article>
                </div>
              ) : null}

              {canManageBilling ? (
                <form className="billing-manage" action="/api/stripe/portal" method="post">
                  <div>
                    <strong>Stripe customer portal</strong>
                    <span>Manage payment details, cancellation, and available plan changes.</span>
                  </div>
                  <button className="auth-button auth-button--secondary" type="submit">Manage billing</button>
                </form>
              ) : null}

              <p className="account-billing-note">
                {billingConfigured
                  ? "Payment details are handled by Stripe. LEILA Ratings stores subscription identifiers and access status, not raw card numbers."
                  : "Stripe billing code is installed, but checkout stays disabled until the Stripe products, price IDs, webhook secret, and server secrets are configured."}
              </p>
            </div>

            <form className="account-signout" action="/auth/signout" method="post">
              <button className="auth-text-button" type="submit">Sign out</button>
            </form>
          </section>
        </div>
      </main>
      <SiteFooter note="LEILA Ratings accounts use Supabase authentication. Paid subscription state is synchronized from Stripe webhooks into row-level-secured account records." />
    </>
  );
}
