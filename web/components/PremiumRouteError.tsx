"use client";

import Link from "next/link";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";
import UpgradeExperience from "@/components/UpgradeExperience";
import { EARLY_BETA_END_LABEL, isEarlyBetaActive } from "@/lib/earlyBeta";

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
  const earlyBetaActive = isEarlyBetaActive();

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
            earlyBetaActive={earlyBetaActive}
            earlyBetaEndLabel={EARLY_BETA_END_LABEL}
          />
        </main>
        <SiteFooter note="Core LEILA ratings remain free. Premium features are free to signed-in users during Early Beta and require the appropriate plan afterward." />
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
            <span className="eyebrow auth-kicker">LEILA {product}</span>
            <h1 className="auth-title">Couldn’t load data</h1>
            <p className="auth-copy">
              The data could not be loaded right now. Your public Adj. Net ratings are still available.
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
      <SiteFooter note="Premium LEILA data is delivered only after server-side account entitlement checks." />
    </>
  );
}
