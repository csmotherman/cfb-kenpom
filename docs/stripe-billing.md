# GRID Stripe billing

GRID uses Stripe Checkout + Stripe Billing for paid subscriptions and Supabase for account entitlements.

## Plans

| Plan | Monthly price | Trial | Access |
| --- | ---: | --- | --- |
| GRID Pro | $0.99 | 7 days, once per GRID account | Advanced Analytics + limited weekly predictions |
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

## Trial behavior

The Checkout Session collects a payment method by default. An eligible first-time subscriber receives a seven-day trial. GRID records `profiles.trial_used_at` when Stripe confirms a trialing subscription so canceling and re-subscribing does not create repeated GRID trials for the same account.

## Customer portal

`POST /api/stripe/portal` creates a Stripe-hosted Customer Portal session. In Stripe, allow customers to update payment methods and cancel subscriptions. If plan switching is enabled in the portal, remember that Stripe can end an active trial immediately when a customer changes subscription prices; test the desired Pro ↔ Pro+ behavior before enabling live plan changes.

## Production checklist

1. Create and test both products/prices in Stripe test mode.
2. Set test-mode environment variables in the deployment environment.
3. Register the webhook endpoint and save its signing secret.
4. Run a full test: new GRID account → Checkout → trialing access → portal → cancel/update → Supabase sync.
5. Confirm duplicate-trial protection.
6. Create the equivalent live-mode prices.
7. Replace only the Stripe keys/price IDs/webhook secret with live values.
8. Run a low-risk live checkout before announcing paid access.

Do not move premium data behind a visual blur alone. The Advanced Analytics and Predictions data must ultimately be served through authenticated server routes so users cannot download paid JSON directly from `/public`.
