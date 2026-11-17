# CVForge Sprint 006 — Growth, Conversion & Retention

## Scope

Improve acquisition attribution, signup-cohort conversion, repeat usage and existing retention workflows. Preserve the working CVForge features and the two current payment providers: Paystack and IntaSend.

## Implemented

### Acquisition attribution
- Added first-touch UTM capture for source, medium, campaign, content and term.
- Captures an external referrer hostname and first landing path without persisting the full referrer URL or query string in registration attribution.
- Sanitizes stored page-visit referrers to host/path only, removing query strings/fragments and redacting secret token paths.
- Captures a stable, hashed browser session ID.
- Adds the attribution snapshot to email and Google registration events using the existing `ActivityLog.details` JSON field.
- No new database columns or migrations.

### Growth and conversion reporting
- Added shared `app/services/growth_analytics.py` report logic.
- Reconciled activation reporting on `first_cv_completed`.
- Added signup-cohort conversion for first CV start, completion, first download and successful payment after registration.
- Corrected paid conversion so pre-existing customers' period payments are not divided by new registrations.
- Added active users, repeat-active users, repeat-usage rate and returning users.
- Added first-touch source/medium and campaign breakdowns.
- Added 7-, 30- and 90-day controls to the conversion report.
- Kept gross revenue separated by currency and provider.

### Retention and conversion fixes
- Enforced a four-successful-send lifetime cap for Pro upgrade nudges per user.
- Preserved the three-day signup grace period, seven-day cooldown and newsletter opt-out.
- Incremented the nudge count only after successful mailer handoff.
- Made the email helper return a truthful success/failure result.
- Fixed the nudge CLI/scheduler result contract.
- Added separate profile preferences for CV progress service reminders, product/Pro marketing emails and account-linked analytics.
- New user settings default product/Pro marketing email preference to opted out; existing saved preferences are preserved.
- Admin product broadcasts now always respect the marketing opt-out for every audience filter, and the broadcast footer points users to account preferences.
- When account-linked analytics is disabled, removed first-touch registration attribution/session linkage and unlinked prior PageVisit rows from that account while preserving anonymous traffic totals.
- Separated marketing opt-out from the dedicated CV progress reminder preference.
- Sends the most relevant eligible abandoned-CV reminder stage first when a scheduled run is delayed.
- Made the direct first-CV action the primary empty-dashboard action.

### Migration and provider safety
- No schema changes or migration files generated.
- Existing `.gitignore` migration exclusions are preserved.
- PythonAnywhere deploy migration exclusions are preserved.
- No payment provider added, removed or replaced. Paystack and IntaSend remain the only supported providers.

## Validation

- Python `compileall`: passed.
- Jinja syntax parse: passed for 85 templates.
- New Sprint 006 integration tests: 11 added; skipped in this environment because Flask and Flask-SQLAlchemy are unavailable.
- Dependency-light regression subset: **37 passed** (ATS-lite, CV diff, deployment migration protection, Sprint 005 payment integrity, template parsing and CV example content).
- Full application test suite: cannot complete in this environment because Flask dependencies are missing; some existing app integration tests error at import for the same reason.
- No production database, provider credentials, live payments or deployment environment were accessed.

## Known limitations

- UTM source attribution applies to new registrations after deployment; no historical backfill.
- CAC cannot be calculated until campaign spend is recorded.
- Revenue is gross, not net of fees/refunds/chargebacks or variable product costs.
- Repeat-active is a directional multi-day usage metric, not formal day-7/day-30 cohort retention.
- SMTP handoff is not confirmed inbox delivery.
