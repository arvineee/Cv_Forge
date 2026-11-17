# CVForge Sprint 003 — First CV Conversion

## Implemented

- Added a first-session onboarding page at `/onboarding`; first-time users without a CV are directed there after login.
- Added direct `Start my first CV` and `See how it works` calls to action on the empty dashboard.
- Added an unfinished-CV section to the dashboard so draft resumes can be resumed directly.
- Added debounced autosave to guided wizard forms (900 ms after input/change), with visible save/error status. Existing step submission remains the canonical continue action.
- Added idempotent account and per-resume events using the existing `activity_logs` table: `cv_started`, `first_cv_started`, `cv_completed`, `first_cv_completed`, and `first_cv_downloaded`.
- A CV is marked `complete` once it has a name, contact email, and at least one substantive content section, and the user reaches review or downloads it.
- Added session-linked email/Google registration events and an admin first-CV conversion report at `/admin/conversion`, showing unique landing sessions, matched landing-to-registration rate, and a 30-day registration cohort through first-CV start, completion and download.
- Added `send-cv-reminders` for 24-hour and 72-hour abandoned-draft reminders. It respects account activity, verification and existing email preference settings, sends at most one reminder per user per 24 hours, and stops for completed drafts.
- Added a profile preference for CV progress reminder emails.
- Added tests for conversion event idempotency and completion criteria.

## Database and compatibility

- No new model columns or tables were added. Existing `ActivityLog`, `Resume`, `Profile` and `UserSettings` records are reused.
- No migration is required for this sprint.
- Existing authentication, payment gateways, plan/download gates, resume generation and upload storage were not intentionally changed.
- No production `.env`, live database, or user upload directory is included in this package.

## Validation

- `python -m compileall -q app tests`: passed.
- `python -m pytest -q tests/test_cv_diff.py tests/test_seo_keywords.py`: 14 passed.
- Full pytest suite could not be executed in this build environment because Flask/Werkzeug dependencies are not installed and package installation is unavailable. Run the complete suite in CI/staging after installing `requirements.txt`.

## Important measurement note

`first_cv_downloaded` records that CVForge generated the file and returned the download response. The server cannot prove that the user's device successfully saved or opened the file.
