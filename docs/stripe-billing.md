# GRID Stripe billing

GRID uses Stripe Checkout + Stripe Billing for paid subscriptions and Supabase for account entitlements.

## Plans

| Plan | Monthly price | Trial | Access |
| --- | ---: | --- | --- |
| GRID Pro | $0.99 | 7 days, once per GRID account | Advanced Analytics + 5 weekly predictions by default |
| GRID Pro+ | $4.99 | 7 days, once per GRID account | Advanced Analytics + all weekly predictions |

Create two recurring monthly Stripe Prices and map their `price_...` IDs to the environment variables below. Keep test-mode and live-mode IDs separate.

## Required environment variables

```text
NEXT_PUBLIC_SITE_URL=https://your-grid-domain.example
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_PRO_PLUS_PRICE_ID=price_...
STRIPE_TRIAL_DAYS=7
GRID_PRO_PREDICTION_LIMIT=5
SUPABASE_SECRET_KEY=sb_secret_...
```

Use `sk_test_...` and test-mode Price IDs until the complete checkout/webhook flow has been verified. Do not commit any secret values.

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

Advanced Analytics and Predictions are now checked on the server against the signed-in user's Supabase subscription record.

Protected routes:

```text
GET /api/premium/advanced/:year
GET /api/premium/predictions/:season/:week
```

Access rules:

- signed out: `401 SIGN_IN_REQUIRED`
- free, inactive, past-due, or canceled: `403 UPGRADE_REQUIRED`
- active/trialing GRID Pro: Advanced Analytics + the configured limited predictions preview
- active/trialing GRID Pro+: Advanced Analytics + all published predictions

Legacy URLs under `/data/advanced/*.json` and `/data/predictions/*.json` are intercepted by Next.js Proxy and rewritten into those entitlement-checked routes, so the deployed site cannot use the old static URLs as a paywall bypass. Premium responses use `private, no-store` caching.

The source repository is currently public. Any premium dataset committed to that public GitHub repository remains retrievable from GitHub itself even though the deployed website blocks direct access. Before treating the data as proprietary, move generated premium datasets to private storage/database infrastructure or make the data-bearing repository private.

## Trial behavior

The Checkout Session collects a payment method by default. An eligible first-time subscriber receives a seven-day trial. GRID records `profiles.trial_used_at` when Stripe confirms a trialing subscription so canceling and re-subscribing does not create repeated GRID trials for the same account.

## Customer portal

`POST /api/stripe/portal` creates a Stripe-hosted Customer Portal session. In Stripe, allow customers to update payment methods and cancel subscriptions. If plan switching is enabled in the portal, remember that Stripe can end an active trial immediately when a customer changes subscription prices; test the desired Pro ↔ Pro+ behavior before enabling live plan changes.

## Production checklist

1. Create and test both products/prices in Stripe test mode.
2. Set test-mode environment variables in the deployment environment.
3. Register the webhook endpoint and save its signing secret.
4. Run a full test: new GRID account → Checkout → trialing access → protected data → portal → cancel/update → access sync.
5. Confirm signed-out and free accounts receive 401/403 responses from premium API routes.
6. Confirm the legacy `/data/advanced/...` and `/data/predictions/...` URLs cannot bypass entitlement checks.
7. Confirm duplicate-trial protection.
8. Move proprietary premium datasets out of the public GitHub repository before relying on repository secrecy.
9. Create the equivalent live-mode prices.
10. Replace only the Stripe keys/price IDs/webhook secret with live values.
11. Run a low-risk live checkout before announcing paid access.
