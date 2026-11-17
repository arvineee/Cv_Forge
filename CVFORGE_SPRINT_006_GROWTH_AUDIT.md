# CVForge Sprint 006 — Growth, Conversion & Retention Audit

## Executive summary

Sprint 006 continues from the Sprint 005 source package. It strengthens the existing growth instrumentation and reminder workflows without replacing the Flask application, adding an analytics vendor, changing payment providers, or changing the production database schema.

The work is aligned to CVForge's business milestone: **10,000 registered users with sustainable revenue**, while keeping the product internationally usable and building toward a future employer marketplace. This sprint measures the quality of acquisition and repeat product use rather than optimizing for registrations alone.

## Existing functionality preserved

- Existing visitor tracking and the `PageVisit` table.
- Existing `ActivityLog` registration and first-CV events.
- Existing `/admin/growth`, `/admin/conversion`, `/admin/visitors` and `/admin/nudges` routes.
- Existing first-session onboarding, CV wizard, autosave, draft recovery and abandoned-CV reminder workflow.
- Existing Paystack and IntaSend payment flows and Sprint 005 revenue summaries.
- Existing pricing, subscription and feature-entitlement implementation.

## Findings addressed

| Priority | Finding | Sprint 006 action |
|---|---|---|
| P1 | Registration records did not retain campaign attribution. | Capture first-touch UTM source, medium, campaign, content, term, landing path and external referrer hostname in the signed browser session; copy an allow-listed snapshot into existing `ActivityLog.details` on email or Google registration. |
| P1 | Growth dashboard activation used `cv_create`, while the first-CV funnel used `first_cv_completed`. | Standardize activation on the existing first meaningful CV completion event. Show start, completion and first download separately. |
| P1 | Paid conversion was a period ratio that could count payments from existing users against new registrations. | Measure the selected signup cohort's successful payments occurring after each user's registration. Label this as cohort conversion to date. |
| P1 | No useful repeat-usage measure was shown. | Add active users, repeat-active users (activity on at least two distinct days), repeat-usage rate and returning users from existing activity events. |
| P1 | Upgrade nudge count was not incremented or enforced despite the UI/CLI describing a four-email lifetime cap. | Enforce a four-successful-send lifetime cap, retain the seven-day cooldown and three-day signup grace period, and increment only after the mailer accepts the message. |
| P1 | The scheduled nudge CLI expected a `total` result field that the service did not return. | Return a consistent result summary and update CLI/scheduler reporting. |
| P1 | The Pro nudge email helper returned no delivery result and swallowed SMTP failures. | Return `True` only when handed to the configured mailer; return `False` when unconfigured or failed. This is SMTP handoff, not proof of inbox delivery. |
| P2 | Marketing newsletter opt-out also suppressed the separate CV progress service reminder, the preferences were not exposed in the profile UI, and admin broadcasts could bypass the newsletter opt-out. | Added separate profile controls: Pro nudges and all admin product broadcasts use `email_newsletter` (new settings default to opted out); unfinished-CV service reminders use `Profile.email_notifications`; account-linked analytics use `allow_analytics`. Existing saved preferences are not overwritten. |
| P2 | A delayed reminder run could send the 24-hour stage before the more relevant 72-hour stage. | Send the latest eligible reminder stage first, while retaining the cooldown and per-stage idempotency checks. |
| P2 | Dashboard first-CV CTA was secondary to the explanatory onboarding page. | Make the direct first-CV action primary and keep the explainer available as a secondary path. |

## Revised analytics architecture

The application remains a modular Flask monolith.

- `app/services/acquisition_tracking.py`: captures first-touch campaign data in the existing signed session and produces a strict allow-listed registration snapshot.
- `app/services/visitor_tracking.py`: keeps the existing privacy-conscious page-view queue and invokes first-touch capture on eligible GET requests.
- `app/services/growth_analytics.py`: builds the common cohort report from `User`, `ActivityLog`, `PageVisit` and `Payment`.
- `app/routes/auth.py`: attaches acquisition metadata to both email and Google registration events.
- `app/routes/admin.py`: serves the same growth and conversion pages using the shared report.
- `app/services/nudge_service.py` and `app/services/email_service.py`: enforce opt-in, cadence, lifetime cap and truthful mailer result handling.

No third-party analytics service is introduced. No new tables, columns, indexes, constraints or migrations are introduced.

## Metric definitions

- **New registrations:** user accounts created in the selected 7-, 30- or 90-day window.
- **Started first CV:** distinct cohort users with `first_cv_started`.
- **Activated users:** distinct cohort users with `first_cv_completed`; this is the existing meaningful first-draft completion event.
- **Downloaded first CV:** distinct cohort users with `first_cv_downloaded`.
- **Paying customers:** distinct cohort users with at least one successful payment timestamped after account creation, measured to date.
- **Paid conversion:** paying cohort users divided by new cohort registrations.
- **Gross revenue:** successful payment records created in the selected reporting window, grouped by currency and provider. It is not net revenue.
- **Active users:** distinct users with a recorded login or core product event during the reporting window.
- **Repeat-active users:** active users with qualifying activity on at least two distinct calendar days in the reporting window.
- **Returning users:** users created before the reporting window who have a qualifying activity event during it.
- **Acquisition source:** first-touch `utm_source`, external referrer hostname, or `direct`.
- **Acquisition medium:** first-touch `utm_medium`, `referral`, or `direct`.
- **Homepage conversion:** registrations whose hashed browser session also has a tracked `/` page view, divided by unique homepage sessions.

## Privacy and security notes

- Campaign values are stripped of control characters and capped at 120 characters.
- The first-touch snapshot stores a referrer hostname, not the full referrer URL or query string. Page-visit referrers retain host/path only; query strings and fragments are removed, and secret token paths are redacted.
- The attribution helper copies only named allow-listed fields from the session into the registration event.
- The existing hashed analytics session identifier is reused; raw browser session identifiers are not added to registration metadata.
- When a user disables account-linked analytics in profile settings, the registration attribution/session linkage is removed and existing page-visit rows are unlinked from the account while remaining anonymous traffic records.
- No new precise location, email, IP or user-agent fields are added to the attribution snapshot.
- The profile page now exposes separate controls for CV progress service reminders, product/Pro marketing emails and account-linked usage analytics. Review the site's privacy notice and consent approach against the jurisdictions where CVForge markets its services before expanding advertising.

## Limitations that remain open

1. **Customer acquisition cost (CAC) is not yet measurable.** The application has no verified campaign-spend input or ad-platform spend integration. UTM attribution reports registrations, not campaign profitability.
2. **Net revenue and contribution margin are not yet accounting-grade.** Provider fees, refunds, reversals, chargebacks, AI costs and variable support costs are not reconciled against gross receipts.
3. **Lifetime value (LTV) is not yet reliable.** CVForge needs mature customer cohorts and net contribution data before using LTV/CAC to scale spend.
4. **Attribution is first-touch only.** It is not a multi-touch attribution model and cannot reliably attribute users who block cookies or switch devices.
5. **Historical attribution is not backfilled.** Campaign breakdowns become meaningful for signups after this release; older registrations may appear unattributed.
6. **Repeat usage is a directional product-activity measure.** It is not a strict day-7/day-30 retention cohort and should not be presented as one.
7. **Email send status means SMTP handoff.** It does not prove inbox delivery or reading. Confirm the production email provider and delivery monitoring separately.

## Strategic next step

Sprint 007 should focus on unit economics and international readiness before committing to a large employer marketplace build:

- introduce a controlled way to record campaign spend and calculate CAC;
- reconcile Paystack and IntaSend gross payments against fees, refunds and reversals;
- measure AI and variable service costs to estimate contribution margin;
- validate demand and pricing with international users before enabling a multi-currency price book;
- use source-to-activation and source-to-paid data to decide which acquisition channels deserve reinvestment.

The employer marketplace remains a later expansion, after candidate value, sustainable revenue and employer demand have been validated.
