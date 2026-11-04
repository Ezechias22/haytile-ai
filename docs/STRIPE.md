# Stripe web billing

Stripe Hosted Checkout, subscriptions, a customer portal and signed-webhook
fulfillment are implemented for the web app. Cards and payment-method details
stay on Stripe; no publishable key is required by this hosted flow. Secrets stay
on the backend. This does not publish native Google Play or Apple in-app billing.

## Configuration and activation

The owner explicitly selected production credentials on 2026-11-04. The live key
has been verified against Stripe; the Brazilian account reports card payments
active and no outstanding requirements. A live webhook endpoint has been created
and its signing secret saved directly in Render. No key was printed or committed.
No card charge or completed paid transaction has been made for verification.
The live catalog uses BRL; publication and delivery verification are recorded below.

The following sandbox procedure remains available for isolated development;
it is not a claim that a real Stripe sandbox transaction was performed:

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
   per offer are required. Fixed USD and BRL prices are supported, with
   at least US$0.01 or R$0.06 per credit. The BRL floor is rounded upward from
   the internal US$0.01 credit reference using the observed USD/BRL 5.4654
   on 2026-11-04 (https://api.frankfurter.dev/v1/latest?base=USD&symbols=BRL).
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
merchant-specific review. This release does not implement automatic tax or automatic FX conversion.
The BRL retail floor is an app policy, not a guaranteed current exchange rate.

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

## Verified deployment

Source `c96c392670f47ca716dd5b97d5fd91f7e6fab573` is live on the existing free
Render service, deploy `dep-dblk5s0n74is73ac268g`, release `stripe-checkout-v6`.
Public-source checks matched; anonymous billing administration is rejected and
unsigned webhooks return 400. Native live configuration remains available and
the owner's wallet did not change during read/quote checks. Both Stripe server
secrets were confirmed absent, so payment admission remains disabled. Anonymous
Firestore reads of wallets and billing purchases returned 403.

Validation: 120 backend tests in the full suite, then all 12 billing tests after
adding the atomic hold-race check; eight core browser workflows plus three billing
workflows; production web build and four locale/configuration checks. The tests
use local providers; actual Stripe sandbox verification and live activation remain
blocked by the missing configuration. No Google generation or real Stripe charge
was made.

## Production connection follow-up

At the owner's explicit request, configuration uses live credentials rather than
requiring a test key. Initial BRL offers: a 500-credit pack at R$34.90, Creator with
1,000 credits at R$69.90/month, and Pro with 3,000 credits at R$199.90/month. These
are Haytile retail prices, not provider API prices. Published Stripe Brazil card
pricing was checked at https://stripe.com/br/pricing (domestic reference 3.99% +
R$0.39); account-specific fees, taxes and FX variation can differ. There is no
profit guarantee. Actual product/price IDs and connection verification are recorded
only after creation. No payment is submitted on behalf of the owner.

The Next API proxy forwards `Stripe-Signature`; a transport regression checks that
the public HTTP gateway, Next and backend preserve both this header and the exact
UTF-8 body. Credentials, BRL grants, invoice currency checks and duplicate-credit
protection were verified with 123 backend tests and four browser billing flows.

## Production verification completed

Live source `759fbdcedc2ff8ba2e1857bd552544418af47704`, free Render deploy
`dep-dblok2dg1s2s73d2rbjg`, release `stripe-live-brl-v7`, is publicly verified.
The live signing secret is stored only in Render. Three real `product.created`
events were acknowledged (Stripe reports zero pending webhooks for each), proving
the live signing/transport path without creating a charge. The temporary product
verification event was then removed from the destination's seven billing events.

Published live offers:

| Offer | Credits | Price | Interval |
| --- | ---: | ---: | --- |
| Credit pack | 500 | R$34.90 | One time |
| Creator | 1,000 | R$69.90 | Monthly |
| Pro | 3,000 | R$199.90 | Monthly |

Actual live Checkout sessions for the pack and Creator subscription were opened,
verified as BRL with the intended amounts, and their hosted pages returned 200.
Both sessions were expired while still unpaid, and only their own pending app
records were removed. The billing portal was created successfully. The owner's
wallet, reservations and plan remained unchanged. No card charge, completed paid
purchase, actual renewal or Google generation was submitted for verification.
Automatic credit fulfillment is covered by local signature/provider tests and
real Firestore atomicity probes; a real paid purchase is not claimed as tested.

Stripe account readiness was checked: BR, BRL, card payments active, no currently
due requirements. Live payment admission is enabled by explicit owner request.
Products/prices are genuine live Stripe objects, and the app catalog is active.
