"use client";

import Link from "next/link";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SiteNav from "@/components/SiteNav";

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

  return (
    <>
      <SiteHeader tagline={product === "Advanced Analytics" ? "Opponent-Adjusted College Football Analytics" : "Weekly Game Predictions"} />
      <SiteNav />
      <main className="auth-main">
        <div className="auth-shell">
          <section className="auth-panel" role="alert">
            <span className="eyebrow auth-kicker">GRID {product}</span>
            <h1 className="auth-title">
              {signInRequired
                ? "Sign in required"
                : upgradeRequired
                  ? "Subscriber access"
                  : "Couldn’t load data"}
            </h1>
            <p className="auth-copy">
              {signInRequired
                ? `Sign in to your GRID account to view ${product}.`
                : upgradeRequired
                  ? `${product} is protected subscriber data. Upgrade your GRID account to unlock it.`
                  : "The data could not be loaded right now. Your public RPI ratings are still available."}
            </p>

            <div className="premium-error-actions">
              {signInRequired ? (
                <Link className="auth-button" href={`/login?message=${encodeURIComponent(`Sign in to view GRID ${product}.`)}`}>
                  Sign in
                </Link>
              ) : upgradeRequired ? (
                <Link className="auth-button" href="/account">
                  View plans
                </Link>
              ) : (
                <button className="auth-button" type="button" onClick={reset}>
                  Try again
                </button>
              )}
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
