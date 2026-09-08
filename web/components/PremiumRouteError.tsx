"use client";

import Link from "next/link";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import UpgradeExperience from "@/components/UpgradeExperience";

type PremiumRouteErrorProps = {
  error: Error & { status?: number; code?: string };
  reset: () => void;
  product: "Advanced Analytics" | "Predictions";
};

export default function PremiumRouteError({
  error,
  reset,
  product,
}: PremiumRouteErrorProps) {
  const signInRequired = error.status === 401 || error.code === "SIGN_IN_REQUIRED";
  const upgradeRequired = error.status === 403 || error.code === "UPGRADE_REQUIRED";
  const expectedAccessGate = signInRequired || upgradeRequired;

  if (expectedAccessGate) {
    return (
      <>
        <SiteHeader tagline={product === "Advanced Analytics" ? "Opponent-Adjusted College Football Analytics" : "Weekly Game Predictions"} />
        <SiteNav />
        <main className="container upgrade-main">
          <UpgradeExperience
            feature={product === "Advanced Analytics" ? "advanced" : "predictions"}
            mode="gate"
            signedIn={!signInRequired}
            trialDays={7}
            trialEligible={null}
          />
        </main>
        <SiteFooter note="GRID keeps core ratings and public team information free. Paid access is reserved for deeper research controls and forward-looking model products." />
      </>
    );
  }

  return (
    <>
      <SiteHeader tagline={product === "Advanced Analytics" ? "Opponent-Adjusted College Football Analytics" : "Weekly Game Predictions"} />
      <SiteNav />
      <main className="auth-main">
        <div className="auth-shell">
          <section className="auth-panel" role="alert">
            <span className="eyebrow auth-kicker">GRID {product}</span>
            <h1 className="auth-title">Couldn’t load data</h1>
            <p className="auth-copy">
              The data could not be loaded right now. Your public RPI ratings are still available.
            </p>

            <div className="premium-error-actions">
              <button className="auth-button" type="button" onClick={reset}>
                Try again
              </button>
              <Link className="auth-button auth-button--secondary" href="/">
                Back to ratings
              </Link>
            </div>
          </section>
        </div>
      </main>
      <SiteFooter note="Premium GRID data is delivered only after server-side account entitlement checks." />
    </>
  );
}
