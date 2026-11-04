# Stripe web billing

Stripe Hosted Checkout, subscriptions, a customer portal and signed-webhook
fulfillment are implemented for the web app. Cards and payment-method details
stay on Stripe; no publishable key is required by this hosted flow. Secrets stay
on the backend. This does not publish native Google Play or Apple in-app billing.

## Configuration and activation

The current deployment cannot accept payments until real server configuration
is supplied. No Stripe keys were found in the development environment or Render
when this integration was prepared. No actual Stripe sandbox or live transaction
has been executed. Automated tests use explicit local Stripe transports.

1. In Render → HAYTILE AI → Environment, set `STRIPE_SECRET_KEY` to the Stripe
   **test-mode** secret key. Never send it through chat or put it in Git.
2. In Stripe's test dashboard, create a webhook/event destination for
   `https://haytile-ai.onrender.com/api/v1/billing/webhook`. Copy its signing secret
   into Render as `STRIPE_WEBHOOK_SECRET` and redeploy the existing free service.
   Subscribe to:
   - `checkout.session.completed`
   - `checkout.session.async_payment_succeeded`
   - `invoice.paid`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `charge.refunded`
   - `charge.dispute.created`
3. Create HAYTILE AI products and actual Stripe prices in test mode. In the app's
   Administration → Stripe section, map their `price_…` IDs to credit quantities
   and the free/Creator/Pro plan. The backend fetches and validates each price.
   `free` means a one-time credit pack, not a free purchase. Creator/Pro require
   recurring monthly or yearly prices with interval count 1. At least 100 credits
   per offer are required. Initially only fixed USD prices are supported, with
   at least one US cent per credit, matching the app's internal credit reference.
   This is a retail floor, not a claim about Stripe fees, exchange rates or profit.
   Check whether the merchant account supports USD presentment before activation.
4. Test Hosted Checkout, asynchronous completion where relevant, invoice renewal,
   cancellation, portal access, duplicate webhook delivery and a failed payment.
   Verify real Stripe sandbox events reach this endpoint with 200 responses.
   Sandbox checkout is administrator-only. It updates an isolated sandbox wallet,
   shown in the administration/pricing screens, and **cannot grant spendable
   credits or a real plan**. This is deliberate separation from production funds.
5. After actual sandbox verification, configure live prices and the matching live
   secret key and webhook signing secret. Only then set
   `HAYTILE_STRIPE_LIVE_ENABLED=1`. Disable the old sandbox event destination when
   switching this single deployment to the live signing secret. Ordinary users
   cannot start sandbox checkouts. Existing valid webhooks can still settle while
   new live checkout admission is disabled.

The server's Stripe REST API version is pinned to `2025-02-24.acacia`; invoice
parsing accepts both the legacy subscription field and the newer parent details.
No prices, Stripe IDs, fees or successful payments are fabricated. Provider fees,
taxes, merchant verification, refund policies and country availability require
merchant-specific review. This release does not implement automatic tax or FX.

## Financial behavior

- The server selects the approved Price ID and quantity. Clients supply only an
  offer ID and idempotency key; they cannot set a charge amount or credit grant.
- A durable purchase snapshot precedes Checkout creation. Stripe idempotency keys
  recover customer/session creation after lost responses. Pending/active
  subscriptions prevent duplicate recurring checkouts.
- Return URLs never grant credits. An owned receipt endpoint reports paid status
  only after verified fulfillment. The UI waits for that status and refreshes the
  balance. A forged URL cannot turn an unpaid purchase into a completed payment.
- The raw webhook body is bounded and verified using HMAC-SHA256, timestamp
  tolerance and constant-time comparison. No cookie login is required by Stripe.
- One-time purchases are re-checked against the Stripe session, customer, price,
  quantity, currency and paid amount. Recurring credits are granted only for paid
  initial/cycle invoices, once per subscription and period, after checking the
  actual subscription. Unpaid invoices and mere subscription creation grant none.
- Firestore atomically commits wallet/plan changes, an event marker, cycle marker,
  purchase receipt and wallet ledger event. Replays, concurrent deliveries and
  loss of the SQL projection cannot grant the same credits twice.
- The portal permits invoices, payment methods and cancellation at period end.
  Plan upgrades/prorations are intentionally disabled in its managed configuration.
  Monthly/yearly credits are granted per paid invoice, not by an independent cron.
- Refund/dispute events put the affected wallet on billing review. New generation
  is blocked while the hold is active; previously approved work may finish. The
  administrator reviews the actual Stripe refund/dispute, removes available
  unreserved credits where appropriate and records a reason before resolving the
  hold. Refund initiation, already-consumed-credit losses and dispute decisions
  are manual merchant operations; they are not falsely presented as automated.
- Account deletion first cancels the matching Stripe customer/subscriptions.
  Failure to cancel blocks erasure until resolved. Minimal pseudonymous payment
  and audit records remain for accounting; the merchant must define legal
  retention periods. No card numbers are stored by Haytile.

New private collections: `haytile_billing_offers`, `haytile_billing_customers`,
`haytile_billing_purchases`, `haytile_billing_events`, `haytile_billing_cycles`,
`haytile_billing_sandbox_wallets`, `haytile_billing_risks`. The existing server-only
Firestore rules cover them. No SQL migration is needed: Firestore is authoritative.
All required queries use single-field indexes.

Official references consulted:
- https://docs.stripe.com/payments/checkout/fulfill-orders
- https://docs.stripe.com/billing/subscriptions/webhooks
- https://docs.stripe.com/webhooks/signature

## Validation

Backend tests exercise the real routes, signatures, owned receipts, mode gating,
provider-field validation, concurrent duplicate fulfillment, sandbox separation,
subscription renewal/cancellation, refund holds, portal configuration and account
cancellation using an explicit local Stripe transport and atomic Firestore fixture.
Browser tests exercise Checkout redirection, administrator Price mapping and
payment-return handling with local mocks. They do not contact Stripe or charge a
card. A disposable real Firestore probe verified concurrent fulfillment once,
sandbox-wallet isolation and replay after total SQL-cache loss, then cleaned up
its own records. Actual Stripe sandbox verification is still required before live
activation. No Google generation is involved in these checks.
