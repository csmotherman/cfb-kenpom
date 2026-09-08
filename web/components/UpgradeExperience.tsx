"use client";

import Link from "next/link";
import type { PaidPlan } from "@/lib/stripe/plans";
import {
  PAID_PLAN_LABELS,
  PAID_PLAN_MONTHLY_PRICE,
} from "@/lib/stripe/plans";

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
  previewTitle: string;
  previewRows: Array<{ label: string; detail: string }>;
};

const FEATURE_COPY: Record<UpgradeFeature, FeatureCopy> = {
  advanced: {
    eyebrow: "Advanced Analytics",
    title: "Go deeper than the rankings.",
    intro:
      "GRID's free ratings tell you how good a team has been. Advanced Analytics gives you the research tools to investigate why.",
    reason:
      "This view is blocked because it combines GRID's paid research tools: custom week ranges, deeper offense and defense views, efficiency splits, explosiveness, finishing and other analysis beyond the public team profile.",
    previewTitle: "Inside Advanced Analytics",
    previewRows: [
      { label: "Custom ranges", detail: "Choose the exact start and end week" },
      { label: "Offense / defense", detail: "Separate team performance on each side" },
      { label: "Efficiency", detail: "Success, pass success and rush success" },
      { label: "Context", detail: "Explosiveness, finishing, pace and field position" },
    ],
  },
  predictions: {
    eyebrow: "Weekly Predictions",
    title: "See the model before the games happen.",
    intro:
      "GRID keeps its core ratings public. Pregame model outputs are paid because they turn those ratings into a forward-looking weekly product.",
    reason:
      "This view is blocked because it contains GRID's pregame projections. Pro receives a limited weekly set when predictions are published; Pro+ receives the full published slate.",
    previewTitle: "Inside Weekly Predictions",
    previewRows: [
      { label: "Projected winner", detail: "Model-selected side for each published matchup" },
      { label: "Projected margin", detail: "Expected scoring margin from the frozen pregame model" },
      { label: "Pregame snapshot", detail: "Built only from information available before the game" },
      { label: "Full slate", detail: "Complete published weekly access with GRID Pro+" },
    ],
  },
  matchup: {
    eyebrow: "Matchup Intelligence",
    title: "Turn team strength into game-specific edges.",
    intro:
      "Basic matchup pages stay free. The deeper product is designed to identify which strengths and weaknesses actually collide in a specific game.",
    reason:
      "Full Matchup Intelligence is still being built and will only be sold once the underlying matchup logic is validated. The upgrade page shows where it fits without pretending unfinished analysis is live today.",
    previewTitle: "Matchup Intelligence roadmap",
    previewRows: [
      { label: "Rush matchup", detail: "Offensive rushing strength vs defensive resistance" },
      { label: "Pass matchup", detail: "Passing efficiency vs opponent pass defense" },
      { label: "Explosiveness", detail: "Which side is more likely to create or prevent big plays" },
      { label: "Situational edges", detail: "Down, distance and game-state analysis as validated" },
    ],
  },
  general: {
    eyebrow: "GRID Pro",
    title: "Use GRID as a research tool, not just a rankings page.",
    intro:
      "The public site answers where teams stand. GRID Pro is for fans who want to investigate the numbers and use the model throughout the week.",
    reason:
      "Core RPI ratings, team profiles, schedules and basic matchup context remain free. Paid access is reserved for deeper research controls and forward-looking model products.",
    previewTitle: "What paid access adds",
    previewRows: [
      { label: "Advanced Analytics", detail: "Custom ranges and deeper team analysis" },
      { label: "Weekly Predictions", detail: "Pregame model projections when published" },
      { label: "Research workflow", detail: "Move from a rating into the numbers behind it" },
      { label: "Future tools", detail: "Validated matchup and split tools as they ship" },
    ],
  },
};

const PLAN_FEATURES: Record<PaidPlan, Array<{ text: string; note?: string }>> = {
  pro: [
    { text: "Advanced Analytics" },
    { text: "Custom start/end week ranges" },
    { text: "General, offense and defense research views" },
    { text: "Limited weekly predictions", note: "when published" },
  ],
  pro_plus: [
    { text: "Everything in GRID Pro" },
    { text: "Every published weekly prediction" },
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
      <section className="upgrade-hero" aria-labelledby="upgradeTitle">
        <div className="upgrade-hero__copy">
          <span className="eyebrow">You opened · {copy.eyebrow}</span>
          <h1 id="upgradeTitle">{copy.title}</h1>
          <p>{copy.intro}</p>
          <div className="upgrade-trustline" aria-label="GRID access principles">
            <span>Core ratings stay free</span>
            <span>Cancel anytime</span>
            <span>{trialDays > 0 ? `${trialDays}-day trial for eligible accounts` : "Simple monthly access"}</span>
          </div>
        </div>
        <aside className="upgrade-why">
          <strong>Why is this blocked?</strong>
          <p>{copy.reason}</p>
        </aside>
      </section>

      {error ? <p className="upgrade-alert upgrade-alert--error">{error}</p> : null}
      {message ? <p className="upgrade-alert">{message}</p> : null}

      <section className="upgrade-plans" aria-labelledby="upgradePlansTitle">
        <div className="upgrade-section-heading">
          <div>
            <span className="eyebrow">Choose access</span>
            <h2 id="upgradePlansTitle">Pick the level that matches how you use GRID</h2>
          </div>
          <p>Pricing is shown up front. No hidden annual commitment.</p>
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
                  {isPlus ? <span className="upgrade-plan__flag">Full access</span> : null}
                </header>

                <div className="upgrade-plan__price">
                  <strong>{planPriceNumber(plan)}</strong>
                  <span>/ month</span>
                </div>

                <p className="upgrade-plan__fit">
                  {isPlus
                    ? "For fans who want the complete weekly model product."
                    : "For fans who want to investigate teams beyond the public profile."}
                </p>

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
                      ? `${trialDays} days free, then ${PAID_PLAN_MONTHLY_PRICE[plan]}. Payment method collected by Stripe. Cancel anytime.`
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
            Paid checkout is not live yet. You can create a free GRID account now; the subscription buttons will activate here after Stripe pricing and the verified webhook are configured.
          </p>
        ) : null}
      </section>

      <section className="upgrade-preview" aria-labelledby="upgradePreviewTitle">
        <div className="upgrade-section-heading">
          <div>
            <span className="eyebrow">What you unlock</span>
            <h2 id="upgradePreviewTitle">{copy.previewTitle}</h2>
          </div>
          <p>Specific tools, not a vague “premium data” promise.</p>
        </div>
        <div className="upgrade-preview__grid">
          {copy.previewRows.map((row) => (
            <div className="upgrade-preview__row" key={row.label}>
              <strong>{row.label}</strong>
              <span>{row.detail}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="upgrade-compare" aria-labelledby="upgradeCompareTitle">
        <div className="upgrade-section-heading">
          <div>
            <span className="eyebrow">Free vs paid</span>
            <h2 id="upgradeCompareTitle">GRID stays useful before you subscribe</h2>
          </div>
          <p>Paid access is for deeper research and forward-looking tools.</p>
        </div>

        <div className="upgrade-compare__table" role="table" aria-label="GRID plan comparison">
          <div className="upgrade-compare__row upgrade-compare__row--head" role="row">
            <span role="columnheader">Feature</span>
            <span role="columnheader">Free</span>
            <span role="columnheader">Pro</span>
            <span role="columnheader">Pro+</span>
          </div>
          {[
            ["RPI, RPI-O, RPI-D", "Included", "Included", "Included"],
            ["Team profiles", "Included", "Included", "Included"],
            ["This Week + basic matchups", "Included", "Included", "Included"],
            ["Advanced Analytics", "—", "Included", "Included"],
            ["Custom week ranges", "—", "Included", "Included"],
            ["Weekly predictions", "—", "Limited", "All published"],
            ["Matchup Intelligence", "Basic view", "Coming soon", "Coming soon"],
          ].map((row) => (
            <div className="upgrade-compare__row" role="row" key={row[0]}>
              {row.map((cell, index) => (
                <span role="cell" key={`${row[0]}-${index}`}>{cell}</span>
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className="upgrade-faq" aria-labelledby="upgradeFaqTitle">
        <div className="upgrade-section-heading">
          <div>
            <span className="eyebrow">Before you start</span>
            <h2 id="upgradeFaqTitle">Straightforward billing</h2>
          </div>
        </div>
        <div className="upgrade-faq__grid">
          <div>
            <strong>What stays free?</strong>
            <p>GRID's core ratings, public team profiles, This Week schedule and basic matchup context remain available without a subscription.</p>
          </div>
          <div>
            <strong>What happens after the trial?</strong>
            <p>If your account is trial-eligible, Stripe starts monthly billing at the displayed plan price when the trial ends unless you cancel first.</p>
          </div>
          <div>
            <strong>Where is payment handled?</strong>
            <p>Checkout and payment details are handled by Stripe. GRID stores subscription identifiers and access status, not raw card numbers.</p>
          </div>
          <div>
            <strong>Already have an account?</strong>
            <p>
              {signedIn ? "You're signed in. Choose a plan above to continue." : (
                <>Sign in first and GRID will bring you back to the plan you selected. <Link href={`/login?next=${encodeURIComponent(upgradeHref(feature, selectedPlan ?? "pro"))}`}>Sign in →</Link></>
              )}
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
