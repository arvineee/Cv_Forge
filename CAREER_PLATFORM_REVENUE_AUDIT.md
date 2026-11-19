# CVForge career platform update and revenue audit

## Product positioning

CVForge is presented as a career development and job-search workspace: create and improve a CV, run ATS checks, match a CV to a vacancy, create cover letters, discover vacancies, receive saved-search alerts, and manage an application pipeline.

## Existing billable foundations

The current application already has configurable `PricingPlan` records, paid subscriptions, time-limited offers, server-side checkout price calculation, payment records, payment webhooks, and admin controls for payment-provider availability.

Existing plan-controlled or metered value includes:

- AI CV writing and section assistance.
- CV parsing/import and AI Revamp.
- ATS analysis and job-description matching (both use the ATS analysis usage bucket; job matching was aligned with the same plan-aware entitlement check in this update).
- Cover-letter generation.
- AI Career Coach review, when enabled by the plan.
- DOCX export, version history, and public CV links through plan entitlements.
- Paid plan periods currently offered through the database configuration (weekly/monthly/yearly where configured).

The public free ATS checker is also a useful acquisition funnel. Keep it useful as a trial/lead-generation feature rather than unexpectedly paywalling it.

## Payment and billing facts found in the source

- Checkout amounts are resolved on the server from the active plan and any eligible live offer; the browser does not choose the amount.
- Payment records are stored with currency, method, status and provider references. Successful payments are reconciled through provider verification/webhooks; a browser redirect is not proof of payment.
- IntaSend and Paystack each have an administrator-controlled enable/disable switch. Disabling a provider blocks new checkouts but does not stop verification of payments already in flight.
- Current checkout flow is KES. Do not advertise multi-currency checkout until it is implemented end-to-end, including provider settlement, currency-aware pricing and reconciliation.
- Subscriptions cover the period paid for and do not automatically renew.
- Offers are discounts layered over base plan prices; base prices are not overwritten.

## Recommended next revenue opportunities

### 1. AI credit packs (best next addition)

Sell optional one-off credits for AI-heavy actions: CV Revamp, job-match analysis, cover-letter generation and Career Coach sessions. Keep plan allowances intact and let users buy extra credits only when needed. This requires a credit ledger, atomic deduction/refund handling, checkout metadata, webhook reconciliation and clear usage receipts; do not simply add a front-end counter.

### 2. Premium job-search tier

Keep basic vacancy discovery, the application tracker and a modest number of saved alerts accessible. Consider charging for higher-value convenience features once implemented: more saved alerts, more frequent matching, tailored job digests, email/WhatsApp delivery, saved search automation and richer match explanations. Current job alerts are in-app notifications and are not evidence of email/WhatsApp delivery.

### 3. Career application bundles

Offer bundles such as a tailored CV + job-specific match report + cover letter, or interview preparation after an application reaches interview stage. These are natural add-ons to existing workflows. The bundle must be priced and recorded as a distinct purchase before it is advertised as available.

### 4. Premium document services

The current plan entitlements already support differentiation through DOCX export, version history, public CV links and premium templates. Consider one-time template packs or a professional human CV review only after the fulfilment and support process exists.

### 5. Employer-side revenue (later-stage opportunity)

Once there is a dedicated employer workflow, consider clearly labelled featured vacancies, employer subscriptions or recruitment packages. Do not sell ranking influence invisibly, and do not present sponsored listings as organic recommendations.

## Measurement required before setting add-on prices

The existing unit-economics report can summarize successful gross collections by currency/provider and AI usage by feature. However, the code itself identifies missing or incomplete inputs: processor fees, refunds/chargebacks, paid acquisition spend and consistent AI token-cost coverage. Capture these before setting credit-pack prices or promising margins. Track conversion and repeat purchase by feature, not only total subscription revenue.

## Guardrails

- Do not charge users for a job listing itself or imply that payment guarantees an interview or job.
- Keep checkout prices authoritative on the server and reconcile every provider payment before granting value.
- Clearly disclose one-time purchases versus subscription periods; current subscriptions do not auto-renew.
- Avoid launching usage credits until duplicate webhooks, failed jobs, retries, refunds and concurrent deductions are handled safely.
- Keep payment-provider switches available to administrators for operational incidents.


## Implemented follow-up: prepaid AI credit wallet

The application now includes one-time prepaid AI credit packs (30 / 100 / 250 credits), a per-user wallet, an immutable transaction ledger, verified Paystack and IntaSend checkout fulfilment, and a wallet page under Billing. Included daily plan allowances are consumed first; eligible AI requests beyond those limits debit one credit. Credit purchases are separate from subscriptions and never change a user's plan.

Pack pricing is currently configured in `app/services/ai_credits.py` (KES 199 / 499 / 999) and should be reviewed against actual model costs and payment fees before promotion.
