"use client";

import Link from "next/link";
import type { PaidPlan } from "@/lib/stripe/plans";
import {
  PAID_PLAN_LABELS,
  PAID_PLAN_MONTHLY_PRICE,
} from "@/lib/stripe/plans";
import PredictionsTrackRecord from "./PredictionsTrackRecord";

export type UpgradeFeature = "advanced" | "predictions" | "matchup" | "general";

type UpgradeExperienceProps = {
  feature: UpgradeFeature;
  mode?: "gate" | "page";
  signedIn?: boolean;
  billingConfigured?: boolean;
  earlyBetaActive?: boolean;
  earlyBetaEndLabel?: string;
  selectedPlan?: PaidPlan | null;
  message?: string | null;
  error?: string | null;
};

type FeatureCopy = {
  eyebrow: string;
  title: string;
  intro: string;
  reason: string;
};

const FEATURE_COPY: Record<UpgradeFeature, FeatureCopy> = {
  advanced: {
    eyebrow: "Advanced Analytics",
    title: "Unlock Advanced Analytics",
    intro:
      "Use custom week ranges and deeper offense, defense and efficiency views without changing the simple LEILA ratings experience.",
    reason:
      "After Early Beta, Advanced Analytics is included with either paid plan.",
  },
  predictions: {
    eyebrow: "Weekly Predictions",
    title: "Unlock Weekly Predictions",
    intro:
      "See LEILA's published pregame model outputs while the ratings and completed-game data remain public.",
    reason:
      "After Early Beta, weekly predictions are included only with Advanced + Predictions.",
  },
  matchup: {
    eyebrow: "Matchup Intelligence",
    title: "Matchup Intelligence",
    intro:
      "Basic matchup pages stay free. Deeper game-specific edges will be added only as the underlying analysis is validated.",
    reason:
      "This is a deeper research layer rather than a core rating. Any unfinished matchup tools remain clearly labeled as coming soon.",
  },
  general: {
    eyebrow: "LEILA Advanced",
    title: "More data when you want it",
    intro:
      "LEILA Ratings stays a ratings-first site. Paid access adds deeper research controls, with Predictions available as a separate upgrade.",
    reason:
      "Adj. Net ratings, team profiles, schedules and basic matchup context remain free. Paid access is for deeper analysis and forward-looking tools.",
  },
};

const PLAN_FEATURES: Record<PaidPlan, Array<{ text: string; note?: string }>> = {
  pro: [
    { text: "Advanced Analytics" },
    { text: "Custom week ranges" },
    { text: "Deeper offense and defense views" },
    { text: "Opponent-adjusted efficiency metrics" },
  ],
  pro_plus: [
    { text: "Everything in Advanced" },
    { text: "All published weekly predictions" },
    { text: "Full weekly model slate" },
    { text: "Matchup Intelligence", note: "coming soon after validation" },
  ],
};

function upgradeHref(feature: UpgradeFeature, plan: PaidPlan) {
  const params = new URLSearchParams({ feature, plan });
  return `/upgrade?${params.toString()}`;
}

function signupHref(feature: UpgradeFeature, plan: PaidPlan) {
  const next = upgradeHref(feature, plan);
  return `/signup?next=${encodeURIComponent(next)}`;
}

function betaDestination(feature: UpgradeFeature) {
  if (feature === "predictions") return "/predictions";
  if (feature === "advanced") return "/advanced";
  return "/";
}

function betaSignupHref(feature: UpgradeFeature) {
  return `/signup?next=${encodeURIComponent(betaDestination(feature))}`;
}

function planPriceNumber(plan: PaidPlan) {
  return PAID_PLAN_MONTHLY_PRICE[plan].replace("/month", "");
}

export default function UpgradeExperience({
  feature,
  mode = "page",
  signedIn = false,
  billingConfigured = false,
  earlyBetaActive = false,
  earlyBetaEndLabel = "October 15, 2026",
  selectedPlan = null,
  message = null,
  error = null,
}: UpgradeExperienceProps) {
  const copy = FEATURE_COPY[feature];
  const returnTo = upgradeHref(feature, selectedPlan ?? "pro").replace(/&plan=pro$/, "");

  return (
    <div className={`upgrade-experience upgrade-experience--${mode}`}>
      <section className="upgrade-compact-head" aria-labelledby="upgradeTitle">
        <span className="eyebrow">{earlyBetaActive ? "Early Beta Access" : copy.eyebrow}</span>
        <h1 id="upgradeTitle">{earlyBetaActive ? "Premium access is free during Early Beta" : copy.title}</h1>
        <p className="upgrade-compact-head__intro">
          {earlyBetaActive
            ? `Sign in and use Advanced Analytics plus all published Predictions free through ${earlyBetaEndLabel}. No payment method is required.`
            : copy.intro}
        </p>
        <p className="upgrade-compact-head__reason">
          <strong>{earlyBetaActive ? "After beta:" : "Why this is blocked:"}</strong> {copy.reason}
        </p>
        <div className="upgrade-trustline" aria-label="LEILA Ratings access principles">
          <span>Core ratings stay free</span>
          <span>Cancel anytime</span>
          <span>{earlyBetaActive ? `Full beta access through ${earlyBetaEndLabel}` : "Monthly access"}</span>
        </div>
        {earlyBetaActive ? (
          <div className="upgrade-plan__action">
            <Link
              className="auth-button upgrade-plan__button"
              href={signedIn ? betaDestination(feature) : betaSignupHref(feature)}
            >
              {signedIn ? "Use Early Beta Access" : "Create free account for Early Beta"}
            </Link>
          </div>
        ) : null}
      </section>

      {error ? <p className="upgrade-alert upgrade-alert--error">{error}</p> : null}
      {message ? <p className="upgrade-alert">{message}</p> : null}

      {feature === "predictions" ? <PredictionsTrackRecord /> : null}

      <section className="upgrade-plans" aria-labelledby="upgradePlansTitle">
        <div className="upgrade-section-heading upgrade-section-heading--compact">
          <div>
            <span className="eyebrow">{earlyBetaActive ? "After Early Beta" : "Access"}</span>
            <h2 id="upgradePlansTitle">{earlyBetaActive ? "Pricing starting October 16" : "Choose a plan"}</h2>
          </div>
        </div>

        <div className="upgrade-plan-grid">
          {(["pro", "pro_plus"] as PaidPlan[]).map((plan) => {
            const selected = selectedPlan === plan;
            const label = PAID_PLAN_LABELS[plan];
            const isPlus = plan === "pro_plus";

            return (
              <article
                key={plan}
                className={`upgrade-plan ${isPlus ? "upgrade-plan--plus" : ""} ${selected ? "upgrade-plan--selected" : ""}`}
              >
                <header className="upgrade-plan__header">
                  <div>
                    <span className="upgrade-plan__label">{label}</span>
                    <h3>{isPlus ? "Advanced + predictions" : "Advanced analytics"}</h3>
                  </div>
                </header>

                <div className="upgrade-plan__price">
                  <strong>{planPriceNumber(plan)}</strong>
                  <span>/ month</span>
                </div>

                <ul className="upgrade-plan__features">
                  {PLAN_FEATURES[plan].map((featureItem) => (
                    <li key={featureItem.text}>
                      <span aria-hidden="true">✓</span>
                      <div>
                        <strong>{featureItem.text}</strong>
                        {featureItem.note ? <small>{featureItem.note}</small> : null}
                      </div>
                    </li>
                  ))}
                </ul>

                <div className="upgrade-plan__action">
                  {earlyBetaActive ? (
                    <button className="auth-button upgrade-plan__button" type="button" disabled>
                      Subscriptions open October 16
                    </button>
                  ) : mode === "gate" ? (
                    <Link className="auth-button upgrade-plan__button" href={upgradeHref(feature, plan)}>
                      Choose {label}
                    </Link>
                  ) : !signedIn ? (
                    <Link className="auth-button upgrade-plan__button" href={signupHref(feature, plan)}>
                      Create account &amp; continue
                    </Link>
                  ) : billingConfigured ? (
                    <form action="/api/stripe/checkout" method="post">
                      <input type="hidden" name="plan" value={plan} />
                      <input type="hidden" name="return_to" value={returnTo} />
                      <input type="hidden" name="source" value={feature} />
                      <button className="auth-button upgrade-plan__button" type="submit">
                        Subscribe to {label}
                      </button>
                    </form>
                  ) : (
                    <button className="auth-button upgrade-plan__button" type="button" disabled>
                      Checkout opening soon
                    </button>
                  )}

                  <small>
                    {earlyBetaActive
                      ? `Free premium access through ${earlyBetaEndLabel}. No payment required.`
                      : `${PAID_PLAN_MONTHLY_PRICE[plan]}. Billed monthly. Cancel anytime.`}
                  </small>
                </div>
              </article>
            );
          })}
        </div>

        {!billingConfigured && !earlyBetaActive && mode === "page" ? (
          <p className="upgrade-billing-note">
            Checkout is not live yet. You can create a free LEILA Ratings account now; plan buttons will activate here after Stripe is configured.
          </p>
        ) : null}
      </section>

      <section className="upgrade-free-note" aria-labelledby="upgradeFreeTitle">
        <div>
          <span className="eyebrow">Always free</span>
          <h2 id="upgradeFreeTitle">The ratings table stays the main product</h2>
        </div>
        <div className="upgrade-free-note__items">
          <span>Adj. Net / Adj. Off / Adj. Def</span>
          <span>Team profiles</span>
          <span>This Week</span>
          <span>Basic matchups</span>
        </div>
      </section>

      {!signedIn ? (
        <p className="upgrade-signin-note">
          Already have an account? <Link href={`/login?next=${encodeURIComponent(earlyBetaActive ? betaDestination(feature) : upgradeHref(feature, selectedPlan ?? "pro"))}`}>Sign in</Link>
        </p>
      ) : null}
    </div>
  );
}
