import type { Metadata } from "next";
import { redirect } from "next/navigation";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import { updateDisplayName } from "@/app/auth/actions";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Account | GRID",
  robots: { index: false, follow: false },
};

type AccountPageProps = {
  searchParams: Promise<{ error?: string; message?: string }>;
};

function planLabel(plan: string) {
  if (plan === "pro_plus") return "GRID Pro+";
  if (plan === "pro") return "GRID Pro";
  return "Free";
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
      .select("display_name,email")
      .eq("id", userId)
      .maybeSingle(),
    supabase
      .from("subscriptions")
      .select("plan,status,trial_end,current_period_end,cancel_at_period_end")
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

  return (
    <>
      <SiteHeader tagline="Opponent-Adjusted College Football Ratings" />
      <SiteNav />
      <main className="auth-main account-main">
        <div className="auth-shell account-shell">
          <section className="auth-panel account-panel" aria-labelledby="accountTitle">
            <div className="account-heading">
              <div>
                <span className="eyebrow auth-kicker">GRID Account</span>
                <h1 id="accountTitle" className="auth-title">Your account</h1>
              </div>
              <span className={`account-plan account-plan--${plan}`}>{planLabel(plan)}</span>
            </div>

            {params.error ? <p className="auth-alert auth-alert--error">{params.error}</p> : null}
            {params.message ? <p className="auth-alert auth-alert--success">{params.message}</p> : null}

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
                <dd>{status === "inactive" ? "Free account" : status.replaceAll("_", " ")}</dd>
              </div>
              {subscription?.trial_end ? (
                <div>
                  <dt>Trial ends</dt>
                  <dd>{new Date(subscription.trial_end).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}</dd>
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
                <span>Entitlements are enforced server-side as billing is added.</span>
              </div>
              <div className="entitlement-list">
                <div className="entitlement-row">
                  <div><strong>RPI Ratings</strong><span>Core GRID team ratings</span></div>
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
              <p className="account-billing-note">
                Billing is not connected yet. Creating a GRID account does not start a trial or charge you.
              </p>
            </div>

            <form className="account-signout" action="/auth/signout" method="post">
              <button className="auth-text-button" type="submit">Sign out</button>
            </form>
          </section>
        </div>
      </main>
      <SiteFooter note="Account access is backed by Supabase authentication and row-level security. Paid billing will be connected separately." />
    </>
  );
}
