# CVForge Admin Dashboard Refresh

## What changed
- Replaced the basic admin landing page with a responsive, professional platform overview.
- Added a branded welcome panel and prominent links to user management and growth reporting.
- Added KPI cards for total users, paid subscribers, successful KES revenue, and CV document totals.
- Added 7-day new-registration count, draft CV count, AI usage, pending payment claims, and due upgrade reminders.
- Added latest registrations and recent payment activity panels.
- Grouped all existing administration routes into a consistent management-tools grid.
- Preserved existing admin endpoints and access controls.

## Backend changes
- The admin index now performs read-only aggregate/list queries against existing `User`, `Resume`, and `Payment` tables.
- Successful revenue on the overview is filtered to KES so the displayed currency is not a misleading sum of multiple currencies.
- No new models, tables, migrations, credentials, or production data changes were introduced.

## Verification
- `python -m py_compile app/routes/admin.py` passed.
- Jinja parser validation of `app/templates/admin/index.html` passed.
- Full Flask integration tests should still be run in GitHub Actions/staging with the project's configured dependencies and test database.
