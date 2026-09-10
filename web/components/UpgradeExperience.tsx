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
  trialDays?: number;
  trialEligible?: boolean | null;
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
      "Use custom week ranges and deeper offense, defense and efficiency views without changing the simple LEILA Ratings ratings experience.",
    reason:
      "The core ratings and team pages stay free. This view is paid because it adds research controls and deeper analysis beyond the public profile.",
  },
  predictions: {
    eyebrow: "Weekly Predictions",
    title: "Unlock Weekly Predictions",
    intro:
      "See LEILA's published pregame model outputs while the ratings and completed-game data remain public.",
    reason:
      "Pregame projections are a forward-looking model product. LEILA Pro gets limited weekly access; LEILA Pro+ gets the full published slate.",
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
    eyebrow: "LEILA Pro",
    title: "More data when you want it",
    intro:
      "LEILA Ratings stays a ratings-first site. Pro simply gives you deeper research controls and model access when you need them.",
    reason:
      "AdjNet ratings, team profiles, schedules and basic matchup context remain free. Paid access is for deeper analysis and forward-looking tools.",
  },
};

const PLAN_FEATURES: Record<PaidPlan, Array<{ text: string; note?: string }>> = {
  pro: [
    { text: "Advanced Analytics" },
    { text: "Custom week ranges" },
    { text: "Deeper offense and defense views" },
    { text: "Limited weekly predictions", note: "when published" },
  ],
  pro_plus: [
    { text: "Everything in LEILA Pro" },
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

function planPriceNumber(plan: PaidPlan) {
  return PAID_PLAN_MONTHLY_PRICE[plan].replace("/month", "");
}

export default function UpgradeExperience({
  feature,
  mode = "page",
  signedIn = false,
  billingConfigured = false,
  trialDays = 7,
  trialEligible = null,
  selectedPlan = null,
  message = null,
  error = null,
}: UpgradeExperienceProps) {
  const copy = FEATURE_COPY[feature];
  const returnTo = upgradeHref(feature, selectedPlan ?? "pro").replace(/&plan=pro$/, "");

  return (
    <div className={`upgrade-experience upgrade-experience--${mode}`}>
      <section className="upgrade-compact-head" aria-labelledby="upgradeTitle">
        <span className="eyebrow">{copy.eyebrow}</span>
        <h1 id="upgradeTitle">{copy.title}</h1>
        <p className="upgrade-compact-head__intro">{copy.intro}</p>
        <p className="upgrade-compact-head__reason">
          <strong>Why this is blocked:</strong> {copy.reason}
        </p>
        <div className="upgrade-trustline" aria-label="LEILA Ratings access principles">
          <span>Core ratings stay free</span>
          <span>Cancel anytime</span>
          <span>{trialDays > 0 ? `${trialDays}-day trial for eligible accounts` : "Monthly access"}</span>
        </div>
      </section>

      {error ? <p className="upgrade-alert upgrade-alert--error">{error}</p> : null}
      {message ? <p className="upgrade-alert">{message}</p> : null}

      {feature === "predictions" ? <PredictionsTrackRecord /> : null}

      <section className="upgrade-plans" aria-labelledby="upgradePlansTitle">
        <div className="upgrade-section-heading upgrade-section-heading--compact">
          <div>
            <span className="eyebrow">Access</span>
            <h2 id="upgradePlansTitle">Choose a plan</h2>
          </div>
        </div>

        <div className="upgrade-plan-grid">
          {(["pro", "pro_plus"] as PaidPlan[]).map((plan) => {
            const selected = selectedPlan === plan;
            const label = PAID_PLAN_LABELS[plan];
            const isPlus = plan === "pro_plus";
            const actionLabel = trialEligible === true && trialDays > 0
              ? `Start ${trialDays}-day free trial`
              : `Choose ${label}`;

            return (
              <article
                key={plan}
                className={`upgrade-plan ${isPlus ? "upgrade-plan--plus" : ""} ${selected ? "upgrade-plan--selected" : ""}`}
              >
                <header className="upgrade-plan__header">
                  <div>
                    <span className="upgrade-plan__label">{label}</span>
                    <h3>{isPlus ? "Full model access" : "Advanced research"}</h3>
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
                  {mode === "gate" ? (
                    <Link className="auth-button upgrade-plan__button" href={upgradeHref(feature, plan)}>
                      {actionLabel}
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
                        {actionLabel}
                      </button>
                    </form>
                  ) : (
                    <button className="auth-button upgrade-plan__button" type="button" disabled>
                      Checkout opening soon
                    </button>
                  )}

                  <small>
                    {trialEligible === true && trialDays > 0
                      ? `${trialDays} days free, then ${PAID_PLAN_MONTHLY_PRICE[plan]}. Cancel anytime.`
                      : trialEligible === false
                        ? `${PAID_PLAN_MONTHLY_PRICE[plan]}. Billed monthly. Cancel anytime.`
                        : `Eligible new accounts get ${trialDays} days free, then ${PAID_PLAN_MONTHLY_PRICE[plan]}.`}
                  </small>
                </div>
              </article>
            );
          })}
        </div>

        {!billingConfigured && mode === "page" ? (
          <p className="upgrade-billing-note">
            Checkout is not live yet. You can create a free LEILA Ratings account now; plan buttons will activate here after Stripe is configured.
          </p>
        ) : null}
      </section>

      <section className="upgrade-free-note" aria-labelledby="upgradeFreeTitle">
        <div>
          <span className="eyebrow">Still free</span>
          <h2 id="upgradeFreeTitle">The ratings table stays the main product</h2>
        </div>
        <div className="upgrade-free-note__items">
          <span>AdjNet / AdjOff / AdjDef</span>
          <span>Team profiles</span>
          <span>This Week</span>
          <span>Basic matchups</span>
        </div>
      </section>

      {!signedIn ? (
        <p className="upgrade-signin-note">
          Already have an account? <Link href={`/login?next=${encodeURIComponent(upgradeHref(feature, selectedPlan ?? "pro"))}`}>Sign in</Link>
        </p>
      ) : null}
    </div>
  );
}
