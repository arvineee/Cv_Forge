# CVForge VPS deployment runbook

Production domain: `https://cvforge.site`

This is a safety-first runbook, not an executable one-size-fits-all script. The exact Linux user, project directory, virtualenv path, systemd unit, Nginx site name and database engine must be read from the live VPS before deployment. Never replace a production `.env`, database, `instance/` directory, uploads directory or payment-settings file with files from a source archive.

## 1. Identify the live deployment

On the VPS, inspect the currently running service and reverse proxy before changing anything:

```bash
sudo systemctl list-units --type=service | grep -Ei 'cvforge|gunicorn'
sudo nginx -T | grep -nE 'server_name|proxy_pass'
ps aux | grep -E '[g]unicorn|[u]wsgi'
```

Record the service unit, working directory, Unix user, virtualenv, database engine, upload location and current Git commit. Do not paste secret environment values into chat or logs.

## 2. Back up persistent data

Back up the database using the tool appropriate to its engine (for example `pg_dump` for PostgreSQL or a consistent SQLite backup), plus the full uploads directory and persistent `instance/` configuration. Store backups outside the web root with restrictive permissions. Confirm the backup can be read before proceeding.

## 3. Deploy the reviewed source

Use the deployment method already configured on the VPS. If deploying with Git, fetch and inspect the intended commit before checking it out. Keep secrets and user data outside the release checkout where possible. Do not use a broad `git clean -fdx` or copy a source archive over the live project.

## 4. Install dependencies and migrations

Activate the existing virtual environment and install the reviewed `requirements.txt` changes. Sprint 006 adds no dependencies and no database schema changes. Sprint 007 adds the `JobOpportunity` table: apply `migrations_manual/002_create_job_opportunities_postgresql.sql` for PostgreSQL or `migrations_manual/002_create_job_opportunities_sqlite.sql` for SQLite. Sprint 005’s `JobApplication` migration must also already be applied. Apply only the script matching the live database engine; never run the SQLite script against PostgreSQL or vice versa. See `JOB_DISCOVERY_SETUP.md` before configuring or scheduling feed ingestion.

## 5. Environment and reverse proxy

Confirm the production environment includes `SITE_URL=https://cvforge.site`, a strong stable `SECRET_KEY`, the production database URI, AI/payment/email credentials and the correct upload directory. Ensure Nginx terminates HTTPS, forwards the host and scheme, and proxies only to the local application server. Do not expose Gunicorn directly to the public internet.

## 6. Restart and smoke-test

Restart the actual service unit discovered in step 1, then inspect its status and logs. Verify at minimum:

- `https://cvforge.site` loads and canonical URLs use the same domain.
- Registration, login, email verification and password reset work.
- Existing CVs, uploads and downloads are intact.
- ATS checks and `/career/match` work for a test account.
- Saving a match to Career Workspace works.
- Paystack and M-Pesa checkout/webhook flows still work in the configured production mode.
- Admin pages and scheduled tasks still work.

Do not test live payments with real customer charges; use provider test mode or a controlled low-value internal transaction where appropriate.

## 7. Rollback

If the smoke tests fail, switch back to the previous known-good application release and restart the same service. Restore the database only if a migration or write operation changed it and only from the matching verified backup. Sprint 006 itself has no schema migration.

## Sprint 006 release note

Adds `/career/match`, a private CV-to-job analysis flow using the existing `JobMatch` table and ATS service. No migration, new external integration or public job-board scraping is introduced.


## Sprint 008 — Job alerts
Follow `SPRINT_008_JOB_ALERTS.md`. Apply migration 003 for your database engine, dry-run `flask process-job-alerts --dry-run`, then schedule the alert processor only after reviewing the output. Alerts are in-app only.
