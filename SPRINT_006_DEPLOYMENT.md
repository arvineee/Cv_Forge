# Sprint 006 deployment checklist

Sprint 006 is an application-code and template update. **It introduces no database migration.** Existing migration directories remain excluded from `.gitignore` and the PythonAnywhere deploy uploader. Do not run `flask db upgrade` for this release.

## Before deployment

- [ ] Back up the production database using the existing PythonAnywhere procedure.
- [ ] Confirm the deployed code is based on the Sprint 005 package and includes the existing payment fixes.
- [ ] Confirm `.env`, `instance/`, production database files and migration directories are not in the release archive.
- [ ] Confirm the production email configuration is valid (`MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`, and SMTP settings).
- [ ] Confirm the account's newsletter and CV progress reminder preferences are understood by the support team.
- [ ] Confirm no payment keys or webhook challenges are present in the archive.

## Deploy

1. Deploy the application code using the existing PythonAnywhere workflow.
2. Do not upload, delete or overwrite the production `migrations/` or `app/migrations/` directories.
3. Reload the web application.
4. Do not run a database migration command; no schema change is included.

## Post-deployment smoke tests

- [ ] Open the public homepage and confirm the existing hero CTA still opens registration.
- [ ] Open `/auth/register?utm_source=qa&utm_medium=test&utm_campaign=sprint006` and complete a test registration in staging.
- [ ] Confirm the resulting `register` ActivityLog details contain first-touch attribution and a hashed session ID, not a full referrer URL or raw session ID.
- [ ] Complete a first CV through the review step and confirm `first_cv_completed` is recorded once.
- [ ] Download a CV in staging and confirm `first_cv_downloaded` is recorded once.
- [ ] Check `/admin/growth` and `/admin/conversion` for cohort, source, campaign and repeat-usage data.
- [ ] Check `/admin/nudges`; candidates should exclude users who have already received four successful nudges.
- [ ] In staging, run `flask send-nudges` with a configured test mailbox and verify the CLI reports total, sent and failed counts without error.
- [ ] Run `flask send-cv-reminders --dry-run` and confirm only users who have not disabled CV progress reminders are eligible.
- [ ] Confirm Paystack and IntaSend checkout/webhooks remain unchanged and functional; this sprint does not alter either provider path.
- [ ] Confirm the production migration directory and its contents are unchanged.

## Suggested PythonAnywhere scheduled tasks

Run only after email delivery has been tested in staging and the production SMTP configuration is confirmed.

Daily Pro upgrade nudge batch (per-user seven-day cooldown and four-successful-send lifetime cap):

```bash
cd /home/CvForge/Cv_Forge && venv/bin/flask send-nudges
```

Daily unfinished-CV service reminders (respects the dedicated CV progress reminder preference):

```bash
cd /home/CvForge/Cv_Forge && venv/bin/flask send-cv-reminders --limit 200
```

Visitor log retention cleanup (90-day retention):

```bash
cd /home/CvForge/Cv_Forge && venv/bin/flask prune-visits
```

## Rollback

If the release causes an application issue, redeploy the previous application-code package and reload the app. Do not roll back, replace or delete production migration directories or database data as part of an application-code rollback.
