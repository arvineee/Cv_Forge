# CVForge Founder Execution Audit — Sprint 001

**Strategic milestone:** 10,000 registered users with sustainable revenue  
**Market sequence:** Kenya first, then selected African markets, then global expansion  
**Funding model:** Bootstrapped; reinvest customer revenue  
**Audit basis:** Uploaded `cvforge.zip` source snapshot, dated files mostly 8–16 November 2026

## Executive assessment

CVForge is not a blank project. The snapshot contains a substantial Flask application with authentication, profile management, CV builder and wizard, CV upload/revamp, ATS analysis, job-description matching, cover letters, templates, billing, payment webhooks, admin operations, visitor tracking, SEO routes, feedback and support.

The next phase should strengthen the existing product and instrument the funnel before adding a full job marketplace or rewriting the architecture. Keep the Flask application as a modular monolith until measured scale justifies service separation.

## Verified inventory in the uploaded snapshot

- Flask application factory and blueprints for authentication, dashboard, CVs, cover letters, ATS, billing, administration, webhooks, templates, API, support, SEO, feedback and guides.
- SQLAlchemy models for users, profiles, resumes, resume versions, cover letters, templates, subscriptions, payments, AI usage, job matches, ATS reports, activity logs, notifications, settings, visitor tracking, offers, feedback, payment claims and broadcast email logs.
- The two configured checkout providers are Paystack (cards) and IntaSend (M-Pesa). Legacy Lipana-named database fields and a legacy Lipana webhook handler remain in the source for compatibility; they are not a configured checkout provider.
- Existing tests under `tests/`.
- Existing `JobMatch` model is a saved job-description comparison record; it is not a complete public job board or employer ATS.
- Pricing plan schema currently stores `price_kes`; subscriptions and payments have a currency field, but the plan catalog itself is not a full multi-currency price-book implementation.

## Critical findings

### P0 — Credential and release-artifact exposure

The uploaded archive contains a tracked `.env`, a populated local `SECRET_KEY`, a local SQLite database, compiled Python caches, Git metadata/history and editor artifacts. Git history also contains an earlier commit explicitly removing a hardcoded Gemini key. Treat credentials ever committed to this repository/history as potentially exposed.

Actions:
1. Rotate the Flask `SECRET_KEY` and invalidate existing sessions.
2. Revoke/rotate any Gemini API key ever committed, plus OAuth client secret, mail credentials, payment API keys and webhook secrets if they have ever appeared in repository history, logs or shared archives.
3. Remove `.env`, database files, bytecode, editor files and generated archives from Git tracking.
4. If the repository was pushed to a remote, clean the full Git history with an approved history-rewrite process and coordinate the force-push; removing `.env` from the latest commit alone does not erase old commits.
5. Never distribute the original archive again. Use a clean source export without `.git`, `.env`, `instance/`, caches or user data.

No credential values are reproduced in this report.

### P0 — Runtime validation is incomplete

Python syntax compilation succeeds. The first full pytest run could not collect two modules because Flask and Werkzeug are not installed in the audit environment. Installing dependencies was blocked by unavailable package-index network access. A dependency-light subset passed: **33 passed, 7 skipped, 66 subtests passed**. This is not a full application test pass.

Before deployment, run the complete test suite in the project's supported Python environment after installing the locked production and development dependencies.

### P1 — Gemini SDK migration

The source uses the deprecated `google-generativeai` package and `google.generativeai` imports. This sprint updates the wrapper to the supported `google-genai` client API and updates the dependency. The wrapper preserves system instructions, generation configuration, response extraction and AI usage logging. The SDK call has not yet been integration-tested against a live Gemini project because dependencies and API credentials are unavailable in this environment.

The configured default is moved to `gemini-3.5-flash-lite`; verify model access and cost in the production Google AI project before rollout. Existing deployment environment variables override the code default and must be updated explicitly if they still specify the previous model.

### P1 — International billing model

`PricingPlan` has a `price_kes` field while `Subscription` and `Payment` have currency fields. This is insufficient for a robust multi-currency catalog, localized tax handling, refunds and provider reconciliation. Introduce immutable price records by plan, currency, billing interval and region; store the exact charged amount/currency/provider reference on each transaction. Do not rewrite existing payment rows or infer historical currency values.

### P1 — Payment reliability

Review all provider webhook flows for signature/challenge validation, amount/currency matching, idempotency under concurrent delivery, duplicate event handling, event audit retention and reconciliation of unmatched transactions. Validate the production database engine: SQLite does not enforce the same row-lock semantics as PostgreSQL/MySQL. Do not log full payment payloads or personal data unnecessarily.

### P1 — Analytics and growth instrumentation

Existing visitor tracking and AI usage tables are not a complete product analytics funnel. Add privacy-conscious events for: landing view, registration started/completed, email verified, CV creation started/completed, CV downloaded, ATS check completed, checkout started, payment succeeded/failed, first return visit and subscription renewed/cancelled. Add country/device/source attribution with consent and retention controls. Report weekly cohort conversion, activation, paid conversion, churn and acquisition cost.

### P1 — Customer retention product

Build a Career Workspace as the next meaningful feature: saved job opportunities, application stages, deadlines, notes and interview preparation. Do not launch a public job marketplace until there is a verified source of job listings and employer demand. Start with a private tracker that gives candidates repeat value immediately.

### P2 — Employer product

Design employer accounts and permissions only after validating candidate usage and interviewing employers. The first employer pilot should be narrow: verified company profile, job posting, applicant list, candidate review and status updates. Avoid a large recruitment suite before at least a handful of employers agree to pilot it.

## Changes made in this sprint

- Migrated the AI service wrapper from `google-generativeai` to the `google-genai` SDK interface.
- Updated `requirements.txt` to depend on `google-genai`.
- Updated the default model to `gemini-3.5-flash-lite` and refreshed related configuration/documentation comments.
- Strengthened `.gitignore` for environment files, local databases, Git metadata, bytecode, caches, editor files and archives while allowing `.env.example`.
- Removed `.env`, the local database and tracked compiled caches from the Git index in this working copy. The local `.env` file is retained on disk but excluded from release packaging.

## First 90-day execution priorities

### Days 1–14: Secure and baseline

- Rotate secrets and clean remote repository history if applicable.
- Confirm the actual production code revision and compare it with this uploaded snapshot.
- Install dependencies in the supported deployment environment and run the full test suite.
- Test registration, email verification, CV creation, CV upload/revamp, ATS, downloads, checkout, webhooks and subscription renewal end-to-end.
- Establish baseline funnel and revenue metrics.

### Days 15–30: Improve activation and trust

- Fix the highest-friction onboarding and mobile issues found through session review and user interviews.
- Add product event tracking and an internal founder dashboard.
- Add payment reconciliation and support workflows.
- Interview at least 30 target users and 10 institutions/employers.

### Days 31–60: Career Workspace MVP

- Build saved opportunities and application tracking.
- Add deadlines, notes, status history and reminders.
- Connect job matches to a user's CV versions without exposing CV data publicly.
- Run a closed beta and measure weekly active use and repeat visits.

### Days 61–90: Monetize and distribute

- Test a useful free tier and paid upgrades based on actual feature value.
- Launch referral tracking and targeted profession/country landing pages.
- Run university and career-office pilots.
- Validate employer demand before committing to the employer ATS build.

## 10,000-user milestone scorecard

Treat these as planning targets, not forecasts:

- 10,000 registered users.
- 3,000 activated users who complete a meaningful CV or career task.
- 500 paying customers as an initial commercial target to test willingness to pay.
- At least 30% of newly activated users return within 30 days (baseline and refine this target after measurement).
- Positive contribution margin after payment fees, AI usage, refunds and variable support costs.
- A repeatable acquisition channel with measured customer acquisition cost.

## Release gate

Do not deploy the SDK migration or other changes until:

1. A staging environment has `google-genai` installed.
2. A smoke test confirms each AI feature and JSON response path.
3. Payment provider sandbox tests pass, including duplicate and invalid webhooks.
4. The full test suite passes.
5. A backup and rollback are verified.
6. The production `.env` is rotated and is not part of the deployment archive.


## Sprint 002 — Founder growth dashboard

Implemented `/admin/growth` using existing `User`, `ActivityLog`, and `Payment` tables. It reports new registrations, same-period CV activation among the new signup cohort, same-period paying customers among that cohort, successful revenue grouped by currency, and daily registration counts. It adds no database tables or migration requirement. The dashboard is restricted by the existing `admin_required` decorator.

Validation: Python source compilation passed. Full Flask integration tests and a production database smoke test remain required in a dependency-complete staging environment.


## Sprint 003 — Activation and first-CV completion

Implemented distinct `cv_completed` and `cv_first_download` activity events using the existing `ActivityLog` table. A CV completion milestone is recorded only when the user reaches the review step and the CV has a name, work experience or education, and at least one skill. First download is recorded only after PDF/DOCX generation succeeds. The user dashboard now displays a getting-started checklist for the most recently updated CV.

No database schema changes or migrations were introduced. No automated follow-up emails were added; existing email-newsletter preferences and consent should be respected before any lifecycle campaign is introduced.

Validation: Python compilation passed and the two changed Jinja templates parsed successfully. The selected Flask integration tests could not run because Flask is not installed in this execution environment (`ModuleNotFoundError: flask`). A dependency-complete staging test and production database smoke test remain required.

## Sprint 004 — Career insights and repeat-use loop

Extended the member dashboard with a career-insights panel sourced only from the signed-in user's saved ATS reports. It shows the latest score, point change versus the preceding report, missing keywords from the latest analysis, up to three improvement suggestions, and a compact recent-score history. The panel links directly to the ATS checker so users can run a new job-specific analysis and measure progress.

The keyword guidance explicitly tells users to include terms only when they reflect genuine skills or experience. This is a product guidance panel, not a promise of hiring outcomes or a claim that keyword matching alone predicts ATS results. It reuses existing `ATSReport` data and introduces no database migration or external service.

Validation: Python compilation passed for the application and all 83 Jinja templates parsed successfully. Full Flask integration tests, browser/mobile checks, and production database tests remain required in a dependency-complete staging environment.


## Sprint 006 — Job Match workspace (18 November 2026)

- Added authenticated `/career/match` GET/POST flow to compare a user's own saved CV against a pasted vacancy description.
- Uses the existing `get_ai_service().ats_check(...)` service and existing ATS daily usage cap; job description is capped at 8,000 characters.
- Persists analysis to the pre-existing `JobMatch` model and records an `ActivityLog` event.
- Displays match estimate, ATS score, matched/missing keywords, potential skills gaps, recommendations and recent analysis history.
- Adds a CSRF-protected action to save an analysed opportunity into the existing `JobApplication` tracker.
- Adds Job Match to the dashboard navigation.
- No new table, migration, dependency, external job-board scraper or third-party integration.
- Updated deployment documentation for the user's stated VPS deployment at `https://cvforge.site`; historical PythonAnywhere helper scripts are explicitly marked as not applicable to production.
- Validation in this environment: Python syntax and Jinja parsing; full Flask integration tests and live VPS tests remain to be run in the production-equivalent environment.


## Sprint 007 — Job Discovery (18 November 2026)

- Added authenticated `/career/jobs` vacancy search with keyword, country and location filters.
- Added RSS/Atom ingestion through `flask sync-job-feeds`; feeds must be configured by the operator and their HTTPS hostnames must be explicitly allow-listed.
- Added a `JobOpportunity` catalogue model and manual SQLite/PostgreSQL migration scripts.
- Added deduplication using a stable SHA-256 key based on feed source name and GUID/ID (or link); entries no longer present in a successfully fetched feed are deactivated.
- Added CSRF-protected save-to-Career-Workspace action and direct CV Match prefill from a discovered vacancy.
- Added Ubuntu VPS feed configuration, manual verification and cron instructions. No sample feed URL is represented as a verified source; `.env.example` values are placeholders.
- Security controls: HTTPS only for feed fetches, hostname allow-list, reject redirects, public-DNS-address check, 2 MB feed response cap, bounded item count and network timeouts.
- No AI usage is triggered by browsing/syncing jobs and no email alerts are sent.
- Requires migration `002_create_job_opportunities_*` matching the production database engine. Existing Sprint 005 `job_applications` migration remains a prerequisite.
- Validation performed in this environment: Python compilation, Jinja template parsing, SQL migration syntax review, archive hygiene. Full Flask/database integration tests, real feed verification, browser tests and live Ubuntu VPS tests remain outstanding.
