# LEILA Ratings Stripe billing

LEILA Ratings uses Stripe Checkout + Stripe Billing for paid subscriptions and Supabase for account entitlements and private premium datasets.

## Plans

| Plan | Monthly price | Trial | Access |
| --- | ---: | --- | --- |
| LEILA Pro | $0.99 | 7 days, once per LEILA Ratings account | Advanced Analytics + 5 weekly predictions by default |
| LEILA Pro+ | $4.99 | 7 days, once per LEILA Ratings account | Advanced Analytics + all weekly predictions |

Create two recurring monthly Stripe Prices and map their `price_...` IDs to the environment variables below. Keep test-mode and live-mode IDs separate.

## Required environment variables

```text
NEXT_PUBLIC_SITE_URL=https://your-grid-domain.example
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_PRO_PLUS_PRICE_ID=price_...
STRIPE_TRIAL_DAYS=7
LEILA_PRO_PREDICTION_LIMIT=5
SUPABASE_SECRET_KEY=sb_secret_...
```

Use `sk_test_...` and test-mode Price IDs until the complete checkout/webhook flow has been verified. Do not commit any secret values.

The scheduled GitHub data refresh also requires a repository Actions secret named `SUPABASE_SECRET_KEY`. The Supabase project URL is non-secret and is already configured in the workflow. Premium files generated during the refresh are hydrated only on the runner, uploaded to Supabase, then deleted before any Git commit.

## Webhook

Configure Stripe to send webhook events to:

```text
https://YOUR_GRID_DOMAIN/api/stripe/webhook
```

The app currently handles:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `customer.subscription.paused`
- `customer.subscription.resumed`

The webhook is authoritative. The browser never directly grants itself Pro access.

## Premium data enforcement

Advanced Analytics and Predictions are checked on the server against the signed-in user's Supabase subscription record, then loaded from the private `premium_datasets` table with the server-only Supabase secret key. The table has RLS enabled and grants no direct access to `anon` or `authenticated` roles.

Protected routes:

```text
GET /api/premium/advanced/:year
GET /api/premium/predictions/:season/:week
```

Access rules:

- signed out: `401 SIGN_IN_REQUIRED`
- free, inactive, past-due, or canceled: `403 UPGRADE_REQUIRED`
- active/trialing LEILA Pro: Advanced Analytics + the configured limited predictions preview
- active/trialing LEILA Pro+: Advanced Analytics + all published predictions

Legacy URLs under `/data/advanced/*.json` and `/data/predictions/*.json` are intercepted by Next.js Proxy and rewritten into those entitlement-checked routes. Premium responses use `private, no-store` caching.

Premium JSON is no longer kept in the current public branch. `site/advanced-data.js`, `web/public/data/advanced/`, and `web/public/data/predictions/` are gitignored so future refreshes do not accidentally republish them. Because the repository was already public before this migration, deleted files can still exist in old Git commit history until that history is rewritten or the repository is made private.

## Trial behavior

The Checkout Session collects a payment method by default. An eligible first-time subscriber receives a seven-day trial. LEILA Ratings records `profiles.trial_used_at` when Stripe confirms a trialing subscription so canceling and re-subscribing does not create repeated LEILA Ratings trials for the same account.

## Customer portal

`POST /api/stripe/portal` creates a Stripe-hosted Customer Portal session. In Stripe, allow customers to update payment methods and cancel subscriptions. If plan switching is enabled in the portal, remember that Stripe can end an active trial immediately when a customer changes subscription prices; test the desired Pro ↔ Pro+ behavior before enabling live plan changes.

## Production checklist

1. Create and test both products/prices in Stripe test mode.
2. Set test-mode environment variables in the deployment environment.
3. Add `SUPABASE_SECRET_KEY` to GitHub Actions repository secrets so scheduled premium publication can run.
4. Register the webhook endpoint and save its signing secret.
5. Run a full test: new LEILA Ratings account → Checkout → trialing access → protected data → portal → cancel/update → access sync.
6. Confirm signed-out and free accounts receive 401/403 responses from premium API routes.
7. Confirm the legacy `/data/advanced/...` and `/data/predictions/...` URLs cannot bypass entitlement checks.
8. Confirm duplicate-trial protection.
9. Confirm the refresh workflow uploads premium data to Supabase without committing ignored premium artifacts.
10. Create the equivalent live-mode prices.
11. Replace only the Stripe keys/price IDs/webhook secret with live values.
12. Run a low-risk live checkout before announcing paid access.
