# CVForge merge: `cvforge.zip` (A) + `cvforge-sprint-008-job-alerts.zip` (B)

## How it was merged
The two archives were not independent. B is the earlier A codebase (commit `1fdbc5a` in A's git history) plus the career track
(Job Match, Job Discovery, Applications, Job Alerts). I used that commit as the common base and did a real three-way merge,
so neither side's changes were overwritten: only-A changes kept A's, only-B changes kept B's, and files both edited were merged.

Result: 171 identical, 38 A-only edits, 1 B-only edit, 4 clean auto-merges, 5 hand-resolved conflicts,
24 files only in A, 16 only in B. Full per-file list: `MERGE_MANIFEST.md`.

## What each side contributed
- **A (conversion/growth/payments track):** conversion tracking + abandoned-CV reminders, growth analytics, unit economics,
  payment integrity, entitlements, onboarding page, admin conversion/unit-economics pages, systemd scheduler, sprint 003-007 docs, extra tests.
- **B (career track):** Job Match, Job Applications, Job Discovery (RSS/Atom), Job Alerts + in-app Notifications, 6 new models,
  SQL migrations 001-003, VPS deployment runbook and setup docs.

## The 5 conflicts and how they were resolved
| File | Resolution |
|---|---|
| `app/cli.py` | Both sides only added commands, so all are registered: `send-cv-reminders`, `cv-conversion-report`, `sync-job-feeds`, `process-job-alerts`. |
| `app/routes/cv.py` | Both sides instrument the first-CV funnel with different event names. Both are now written: A's `first_cv_*` events (growth reports) and B's `cv_completed` / `cv_first_download` (dashboard checklist). `_log_once` dedupes, so nothing double-counts. |
| `app/routes/dashboard.py` | Imports unioned; A's `/onboarding` kept alongside all of B's `/career/*` routes. |
| `app/templates/dashboard/index.html` | A's "first CV" hero and unfinished-drafts banner kept; B's getting-started checklist kept but only shown once the user has a CV (the hero already covers the empty state). |
| `README.md` | B's VPS deployment text is now the primary one (A's own `deploy.yml` also deploys to the VPS). A's PythonAnywhere text is kept under "Historical". A's Sprint 003/005/006 sections and B's Sprint 004/006/007/008 sections are all kept. CLI and admin-route tables updated. |

Sprint numbers collide between the two tracks (e.g. both have a "Sprint 003" and "Sprint 006"), so README headings are tagged *(conversion track)*, *(growth track)* or *(career track)*.

## Left out on purpose
`.env` (real credentials), `instance/cvforge.db` (local database), `.mannual.diff.swp`, four `.bak` files, `patch.py`
(one-off; its fixes are already in A's sources), `__pycache__`, `.pytest_cache`, `.git`.
**A's git history tracks `.env`, so rotate every key that was in it** (Gemini, Google OAuth, Lipana/Paystack/IntaSend, mail).

## Added by the merge
- Optional systemd timers `cvforge-job-feeds` and `cvforge-job-alerts` (same schedule as B's cron entries, :15 and :30 every 4 hours).
  `install.sh` installs them but does not enable them, matching B's "dry-run first" guidance.
- The 14 sprint documents that were deleted from A's working tree but still in its git history were restored.

## Verification done / not done
- Done: every `.py` compiles; no conflict markers; every `from app... import` resolves; all 113 `url_for` targets match a route;
  every line B or A added is still present except those deliberately reworked above.
- **Not done: the test suite was not run** (the sandbox has no network to install Flask). Run `python -m pytest -q` before deploying.
- B added **no tests** for job match/discovery/applications/alerts, so those features have no automated coverage.

## Before deploying
1. Apply B's migrations for your DB engine (`migrations_manual/001`-`003`); they create `job_applications`, `job_opportunities`, `job_alerts` tables.
2. Set `JOB_FEEDS_JSON` and `JOB_FEED_ALLOWED_DOMAINS` (see `.env.example`) before running `flask sync-job-feeds`.
3. `deploy.yml` calls `~/Cv_Forge/deploy.sh` on the server; that script is not in either archive, so check it matches the release layout.
