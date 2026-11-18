# Sprint 005 — Career Workspace

Adds a private job-application tracker to CVForge. Users can save job opportunities, record company/title/link/location/employment type/salary/deadline/notes, associate a CV, update status, and delete records. Statuses: saved, applied, interview, offer, rejected, withdrawn.

## Database migration required
This sprint adds `job_applications`; it is not safe to deploy without applying the schema change. Back up the production database first.

The archive does not contain a migrations repository, so do not assume `flask db migrate` is ready to run. Use the reviewed SQL matching your actual database engine: `migrations_manual/001_create_job_applications.sql` for PostgreSQL or `migrations_manual/001_create_job_applications_sqlite.sql` for SQLite. Back up first, verify the existing table/column names, execute once, and confirm both indexes exist. If you maintain Flask-Migrate separately, generate and review a migration in that repository instead. Do not run `db.create_all()` as a substitute on a live database.

## Security and behaviour
- All read/update/delete queries are scoped to `current_user.id`.
- POST actions are protected by Flask-WTF CSRF.
- A selected CV must belong to the current user.
- External job links are restricted to HTTP/HTTPS URLs.
- This is a tracker, not a job board or automatic application submission service.

## Validation
Run the project's full test suite and smoke-test create/update/delete, cross-user access denial, date validation, mobile layout, and CSRF in staging before production.
