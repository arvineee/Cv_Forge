# CVForge Sprint 005 — Payment & Revenue Infrastructure

## Scope

Sprint 005 hardens the existing Paystack and IntaSend payment paths, improves subscription activation integrity, connects existing plan limits to runtime checks, and improves revenue visibility. It does not add another payment provider.

## Implemented

### Paystack
- Local order checks now validate the reference, payment/subscription relationship, user, amount, currency, and stored order snapshot before contacting Paystack.
- Server-side verification checks successful status, reference, amount in minor units, currency, customer email when present, and transaction ID.
- Provider transaction IDs are namespaced (`paystack:<id>`) before persistence to avoid collisions with IDs from the other provider.
- Only an allow-listed verification summary is stored; the full Paystack transaction response is not copied into `Payment.raw_webhook`.

### IntaSend
- Removed the unused `/webhooks/lipana` endpoint and Lipana environment configuration. Paystack and IntaSend are the only configured providers.
- The `/webhooks/intasend` endpoint validates the configured challenge and accepts collection events.
- A `COMPLETE` or final failure webhook is not enough to fulfil or fail an order. CVForge retrieves the invoice through the IntaSend status API and checks invoice ID, `api_ref`, state, value, currency, local payment row, subscription, user, and payment method.
- IntaSend transaction IDs are namespaced (`intasend:<provider_ref>`; invoice ID is the fallback).
- Webhook challenge values and full raw payloads are not stored or logged.
- Pending-payment reconciliation uses the same server-side invoice validation path.

### Subscription and payment records
- Checkout writes an order snapshot into the existing JSON metadata field: plan slug, billing period, amount, currency, and user ID.
- Activation uses the purchased billing period snapshot rather than a potentially edited live plan period.
- Duplicate provider transaction IDs are rejected before persistence.
- Success and failure handlers protect already-successful payments from late failure events.
- Generic Python aliases (`provider_reference`, `provider_transaction_id`) map to the existing legacy database columns. No new columns or migrations are introduced.

### Plan entitlements
- Added `app/services/entitlements.py` to resolve the effective, unexpired plan and its daily limits.
- CV AI assistance, CV parsing, CV revamp, Career Coach, cover-letter generation, and ATS checks now use existing `PricingPlan` daily-limit fields where configured.
- Expired paid plans fall back to the free plan's entitlements (or the existing global fallback when no free plan row exists).
- DOCX, Career Coach, and version-history checks use plan entitlements rather than relying only on the `User.is_premium` shortcut.

### Revenue and administration
- Founder growth dashboard now breaks successful gross payment records down by currency and payment method/provider.
- Admin payment history displays the currency and a readable provider label.
- User billing history displays provider-neutral transaction/reference aliases.

### Migration/deployment safety
- No migration files were generated or modified.
- Existing migration `.gitignore` entries and deployment script exclusions are preserved.
- The PythonAnywhere deploy script continues to skip every path component named `migrations`, including root and nested migration folders.

## Validation

- Python compile check: passed.
- Focused payment-integrity, provider-settings, and deployment-protection tests: **18 passed**.
- Six app-level Sprint 005 tests were added for model aliases, plan limits, Paystack verification, IntaSend verification, amount mismatch rejection, and billing-period snapshots. They were skipped in this execution environment because Flask/Flask-SQLAlchemy are not installed.
- Full suite could not be completed in this environment: Flask/Werkzeug dependencies are missing, and Playwright's Chromium executable is unavailable.
- Provider sandbox transactions and production deployment have not been performed.

## Required pre-production checks

1. Configure Paystack webhook URL as `https://<your-domain>/webhooks/paystack`.
2. Configure IntaSend collection webhook URL as `https://<your-domain>/webhooks/intasend`, with the same challenge as `INTASEND_WEBHOOK_CHALLENGE` and the collection event enabled.
3. Confirm Paystack and IntaSend keys belong to the intended live/sandbox environments.
4. Test one successful and one failed transaction with each provider in sandbox before live rollout.
5. Back up the production database before deployment. No database migration is required for this sprint.

## Known limitations / follow-up

- Revenue figures are gross successful payment rows. Provider fees, refunds, reversals, and chargebacks are not yet reconciled into a net-settlement ledger.
- Provider reference columns are not made unique at the database layer because production schema changes are intentionally out of scope. CVForge continues to generate random order references and validates their local associations.
- `with_for_update()` provides real row locking only on databases that support it; SQLite does not enforce the lock.
- Manual payment-claim approval remains a human-admin trust path and does not pretend to be a provider API verification.
