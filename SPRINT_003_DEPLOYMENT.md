# Sprint 003 staging and deployment

## 1. Back up production first

Before deployment, create separate timestamped backups of:

- The live database (use the database provider's backup/export procedure; do not copy a live SQLite file while it is being written).
- The complete user upload directory, including uploaded source CVs and profile images.
- The current application release and production configuration as a protected backup.

Keep backups outside the application directory and verify that the database backup can be opened. Do not include secrets in Git or the release ZIP.

## 2. Rotate exposed credentials

Review credentials that were ever committed, shared, or included in older archives. Rotate the Flask `SECRET_KEY`, database password, Paystack/Lipana/IntaSend keys, Google/Gemini credentials and SMTP password as applicable. Update the hosting environment variables securely. Do not paste production secrets into chat or commit them to the repository.

## 3. Stage without replacing production state

1. Deploy the ZIP to a separate staging directory or staging app.
2. Create a separate staging database and upload directory.
3. Configure staging credentials through environment variables.
4. Keep the existing production `.env`, database and uploads untouched.
5. Install dependencies from `requirements.txt` and run `python -m pytest -q`.
6. Test registration, email verification, first login/onboarding, new CV creation, all wizard steps, autosave after typing, refresh/resume, review completion, PDF/DOCX payment gates, successful download and profile email preference.
7. Test reminder dry-run first: `flask send-cv-reminders --dry-run`.
8. Check the admin funnel at `/admin/conversion` and CLI report: `flask cv-conversion-report --days 30`.

## 4. Scheduled reminders

After staging email delivery and opt-out behavior are verified, add a daily PythonAnywhere scheduled task:

```bash
cd /home/CvForge/Cv_Forge && /home/CvForge/Cv_Forge/venv/bin/flask send-cv-reminders
```

Adjust the paths to the actual PythonAnywhere project and virtualenv. Start with `--dry-run` and inspect the counts before enabling sending. The command is deliberately not run in web workers or on application startup.

## 5. Production release

Only after staging passes:

- Take a fresh production backup.
- Deploy application code while preserving the live `.env`, database and upload directory.
- Restart the web app.
- Smoke-test login, dashboard, CV creation, payment checkout and downloads.
- Monitor logs and conversion events.

No database migration is required by Sprint 003.
