# CVForge Sprint 008 — Personalised Job Alerts

## Delivered
- Authenticated `/career/job-alerts` page to create, pause, activate and delete up to 10 saved searches.
- Deterministic keyword matching against imported job title, company and description, with optional country and location filters.
- Matching vacancies create in-app notifications.
- Unique delivery records prevent the same vacancy being alerted twice for one saved search.
- `flask process-job-alerts --dry-run` previews matches; `flask process-job-alerts` creates notifications.
- No AI calls, email sending, or external data requests occur during alert processing.

## Matching limitations
This is a keyword filter, not a semantic suitability score. A match means at least one keyword token is present, with optional country/location filters. It does not verify employer legitimacy, vacancy status, qualifications, or eligibility. Users should inspect the original listing.

## Database migration
After Sprint 005 and Sprint 007 migrations, apply exactly one file: PostgreSQL `migrations_manual/003_create_job_alerts_postgresql.sql`; SQLite `migrations_manual/003_create_job_alerts_sqlite.sql`. Back up the database first. Do not use `db.create_all()` as a production migration.

## Ubuntu VPS deployment
1. Back up the production database and current application directory.
2. Deploy source while preserving `.env`, database files, uploads and persistent data.
3. Apply the matching SQL migration.
4. Restart the Flask/Gunicorn service.
5. Run `flask process-job-alerts --dry-run` and inspect counts.
6. Run `flask process-job-alerts` once.
7. After successful verification, schedule after feed sync, for example:

```cron
30 */4 * * * cd /srv/cvforge/current && /srv/cvforge/venv/bin/flask process-job-alerts >> /var/log/cvforge/job-alerts.log 2>&1
```

Replace paths with the actual Ubuntu deployment paths.

## Privacy
Alerts are user-created and in-app only. This sprint sends no job-alert emails and does not change newsletter or marketing consent settings.
