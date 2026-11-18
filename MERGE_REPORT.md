# CVForge branch merge report

## Source archives inspected
- `cvforge.zip` — used as the base snapshot because it contains the later conversion, onboarding, payment-integrity, growth analytics, unit-economics, and scheduler additions.
- `cvforge-sprint-008-job-alerts.zip` — integrated for Sprint 008 job discovery, job matching, career workspace, and personalised job alerts.

## Inventory
- `cvforge.zip`: 244 regular project files after excluding local secrets, databases, bytecode, editor backups, and test caches.
- Sprint 008 archive: 235 regular project files after the same exclusions.
- 219 paths are shared; 48 shared files have different contents.
- 16 files exist only in the Sprint 008 archive.
- 25 files exist only in `cvforge.zip`.
- Final merged project: 260 regular files.

## Merge policy
- For shared files, the `cvforge.zip` implementation is retained where it contains the later cross-sprint work (conversion, payments, growth, onboarding, and unit economics).
- Sprint 008 career endpoints were merged into the newer dashboard route module instead of replacing its onboarding and profile-consent behaviour.
- Sprint 008 job ORM models were added to the newer model module without replacing its payment aliases, settings defaults, or other later model changes.
- Sprint 008 CLI commands were added alongside the newer CV reminder and conversion-report commands.
- Sprint 008 feed configuration was added to the newer configuration and environment-example files.
- Sprint-only services, templates, SQL migrations, setup notes, and Sprint 008 documentation were included.
- Base-only services, scheduler assets, tests, and admin/dashboard templates were retained.

## Sprint 008 files/features included
- Job description matching against a user's saved CVs.
- Job discovery from explicitly configured RSS/Atom sources.
- Career application tracker with saved/applied/interview/offer/rejected/withdrawn states.
- Personalised in-app job alerts and idempotent alert delivery records.
- Job discovery and alert services, career templates, and six database-specific migration scripts.
- `sync-job-feeds` and `process-job-alerts` CLI commands.

## Existing branch work retained
- First-time onboarding and unfinished-CV dashboard work.
- CV conversion tracking, reminders, and conversion reporting.
- Payment integrity and entitlement services.
- Growth analytics and unit economics.
- Existing payment, authentication, CV builder, ATS, admin, and scheduler code.

## Validation performed
- 89 Python files compiled successfully with Python's `compile()` check.
- Static merge assertions passed for job models, routes, services, templates, migrations, CLI registration, onboarding, conversion, payment integrity, growth, and unit-economics files.
- `pytest` was attempted but collection stopped because Flask is not installed in the execution environment (`ModuleNotFoundError: No module named 'flask'`). Therefore the application test suite has **not** been confirmed passing.

## Excluded local/private files
- `.env`
- local SQLite database files
- Python bytecode and `__pycache__`
- `.pytest_cache`
- editor backup/swap files

## Deployment note
Back up the active database and review/apply the included Sprint 008 SQL migrations for the database engine in use before enabling the job features. Configure `JOB_FEEDS_JSON` and `JOB_FEED_ALLOWED_DOMAINS` in the runtime environment with trusted HTTPS feed sources. Do not copy secrets from a local `.env` file into source control.
