# CVForge Sprint 004 — Audit and Reliability Baseline

## Completed in this working copy

- Added `CVFORGE_SPRINT_004_ARCHITECTURE_AUDIT.md` covering architecture, existing functionality, database/security assessment, bugs and technical debt, customer journey, conversion measurement, revised architecture, implementation plan and 10,000-user scorecard.
- Fixed the landing-to-registration attribution mismatch: registration events now use the same hashed browser-session identifier as `PageVisit` records.
- Added an integration test for the shared hashed session identifier. It requires the full Flask test dependencies and was not runnable in this environment.
- Added a local SQLite fallback when `DATABASE_URL` is missing or blank; the app factory ensures the instance directory exists.
- Made blank `GEMINI_MODEL` and `GOOGLE_REDIRECT_URI` environment values fall back to safe defaults rather than empty strings.
- Added `migrations/` and `app/migrations/` to `.gitignore` per the production deployment policy. The PythonAnywhere deployer independently skips any directory named `migrations`, including already-tracked files, so ordinary code deploys cannot overwrite production migration history.
- Added `intasend-python` to `requirements.txt` so the payment SDK is part of the declared runtime dependency set.
- Updated README database configuration and migration caveats.
- Added pure configuration fallback tests.

## Validation

- Python compilation passed.
- Focused dependency-light tests: 16 passed.
- Full suite remains blocked in this local environment because Flask and Werkzeug are not installed. Run the full suite in CI/staging before release.

## Not changed

- No production database, credentials, payment records, customer data or live deployment were accessed or modified.
- No schema migration was generated. The current source archive has no migration history; a baseline must be reconciled against the actual production schema before any migration is applied.
- Payment webhook amount/currency validation, entitlement enforcement and subscription order snapshots remain Sprint 005 priorities and must be sandbox-tested before release.


## Follow-up correction

- CVForge currently uses only Paystack and IntaSend as checkout providers. Legacy Lipana-named database columns and a dormant webhook route are identified as compatibility debt, not as an active payment integration.
- Added deployment regression tests proving root and nested migration directories are excluded while normal application code remains deployable.
