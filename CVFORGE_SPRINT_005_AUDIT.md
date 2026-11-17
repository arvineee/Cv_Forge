# CVForge Sprint 005 — Implementation Audit

## Executive summary

Sprint 005 hardens CVForge's current payment stack without replacing the existing application or changing the production database schema. The only supported payment providers remain **Paystack** and **IntaSend**.

The highest-risk issue in the Sprint 004 source was that an IntaSend webhook with a valid challenge and `COMPLETE` state could activate a subscription without checking the invoice's amount or currency against the stored order. Sprint 005 changes the IntaSend path so CVForge retrieves the invoice from IntaSend's status API and validates it before changing subscription state.

Paystack already had server-side verification. Sprint 005 centralizes and strengthens its local order checks, validates the stored currency rather than hard-coding a comparison in the callback, and stores only a minimal verification summary.

## 1. Payment architecture

### Paystack

Checkout is initialized by CVForge using a server-computed KES amount and a unique CVForge reference. The callback and webhook are notifications only; CVForge verifies the reference through Paystack's transaction verification API before activating access.

The verified transaction must match:

- a local `Payment` with `payment_method="paystack"`;
- the associated `Subscription` and user;
- the CVForge reference;
- the stored payment and subscription amount;
- the stored currency;
- successful provider status;
- amount in Paystack's minor units;
- customer email when returned by Paystack;
- a provider transaction ID not already assigned to another CVForge payment.

### IntaSend

The webhook is authenticated using the static challenge configured in IntaSend. A valid challenge does not, by itself, activate a plan. On final invoice states, CVForge calls the IntaSend status API and validates:

- `invoice_id`;
- `api_ref` against the CVForge payment reference;
- `state` (`COMPLETE` for activation; `FAILED` or `CANCELED` for failure);
- `value` against the server-stored payment amount;
- `currency` against the stored payment/subscription currency;
- local payment/subscription/user relationships;
- IntaSend payment method (`mpesa` or `card`);
- the invoice ID stored at checkout, when available.

Non-final states such as `PENDING`, `PROCESSING`, `RETRY`, and `PARTIAL` do not activate subscriptions.

## 2. Subscription correctness

The checkout record now stores an order snapshot in the existing `Payment.raw_webhook` JSON field. This protects the billing period purchased from subsequent plan edits while a payment is pending. It also records the original plan, amount, currency and user ID for consistency checks.

The activation handler remains shared with admin-approved manual claims, but provider-originated success must pass the provider-specific verification path first. Late failure events cannot undo a successful payment. Repeated success events do not extend the subscription more than once.

## 3. Schema and migration safety

No new database columns, tables, indexes, constraints or migrations are added in Sprint 005.

The existing application model maps legacy columns named `lipana_transaction_id`, `lipana_checkout_request_id`, and `lipana_payment_link_id`. Renaming or dropping these columns would require a production schema migration and could break historical payment data. They are therefore retained, with generic SQLAlchemy aliases exposed to application code:

- `provider_transaction_id` → `lipana_transaction_id`;
- `provider_reference` → `lipana_checkout_request_id`;
- `provider_payment_link_id` → `lipana_payment_link_id`.

The legacy Lipana webhook route and Lipana environment configuration have been removed. The legacy column names are storage compatibility only; Lipana is not a configured provider.

Migration directories remain excluded in `.gitignore` and the PythonAnywhere deployment uploader. The deployment uploader skips any path with a `migrations` directory component, so an ordinary application deploy does not upload or replace deployment-managed migration history.

## 4. Entitlement assessment

The existing `PricingPlan` model already stores daily limits for CV generation, cover letters and ATS checks, plus flags for DOCX, version history, Career Coach and public links. Before Sprint 005, some of those daily fields were administrative display values rather than runtime limits.

Sprint 005 adds a shared effective-plan resolver and connects the existing limits to the routes. Expired paid plans use the free plan's entitlements. No migration is needed.

## 5. Revenue reporting

The admin growth dashboard now groups gross successful payments by currency and provider/payment method. It deliberately does not sum different currencies. The report does not claim to be net revenue: fees, refunds, reversals and chargebacks are not yet reconciled into a separate ledger.

## 6. Findings still open

| Priority | Remaining item | Reason / next action |
|---|---|---|
| P1 | Sandbox end-to-end payment tests | Run a success and failure transaction for Paystack and IntaSend using the merchant's real sandbox configuration before production rollout. |
| P1 | Production database backup and smoke test | Back up before deployment; verify a small-value live payment only after sandbox sign-off. |
| P2 | Refund/reversal/chargeback ledger | Add a controlled reconciliation workflow before using dashboard gross receipts as accounting-grade net revenue. |
| P2 | Provider reference uniqueness | Add a unique constraint only after production data has been audited and a separate migration is approved. |
| P2 | Concurrency on SQLite | Production row locking requires PostgreSQL/MySQL or another DB engine that supports `SELECT ... FOR UPDATE`. |
| P3 | Multi-currency pricing | Current checkout and plan pricing remain KES-based; international recognition does not yet mean international currencies are enabled. |

## 7. Test status

- `compileall`: passed.
- Focused pure tests: 18 passed.
- App-level tests added: 6 skipped because the current execution environment does not have Flask and Flask-SQLAlchemy installed.
- Full test suite: blocked by missing Flask/Werkzeug dependencies and missing Playwright Chromium binary.
- No live provider credentials were used; no payment was initiated; no production database was changed.

## Provider documentation checked

- IntaSend webhook contract: https://developers.intasend.com/guides/webhooks/
- IntaSend collection invoice and status fields: https://developers.intasend.com/guides/collections/overview/
- Paystack transaction verification: https://paystack.com/docs/api/transaction/
