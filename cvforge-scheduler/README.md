# CVForge automated jobs (systemd timers)

| Timer | Command | When |
|---|---|---|
| cvforge-nudges | `flask send-nudges` | daily 09:00 |
| cvforge-cv-reminders | `flask send-cv-reminders` | every 6 hours |
| cvforge-prune-visits | `flask prune-visits` | Sundays 03:30 |
<<<<<<< HEAD
| cvforge-job-feeds *(opt-in)* | `flask sync-job-feeds` | every 4 hours at :15 |
| cvforge-job-alerts *(opt-in)* | `flask process-job-alerts` | every 4 hours at :30 |

The two job timers are installed but **not enabled** by `install.sh`. Follow `JOB_DISCOVERY_SETUP.md` and `SPRINT_008_JOB_ALERTS.md` (apply migrations, run the dry run) and then run `sudo systemctl enable --now cvforge-job-feeds.timer cvforge-job-alerts.timer`.
=======
>>>>>>> ee431c06f8596a451011871582c1200fef239ca0

## Install
1. Upload this folder to the VPS.
2. Make sure `/var/www/cvforge/.env` holds your real settings (DATABASE_URL, MAIL_*, GEMINI key).
   If your app lives elsewhere: `sudo APP_DIR=/path/to/app APP_USER=youruser bash install.sh`
3. `sudo bash install.sh`

## Test before trusting it
- Dry run for CV reminders (sends nothing):
  `cd /var/www/cvforge && FLASK_APP=run.py venv/bin/flask send-cv-reminders --dry-run`
- Run the nudge job once: `sudo systemctl start cvforge-nudges.service`
- Logs: `journalctl -u cvforge-nudges.service -n 50 --no-pager`

## Important
- Keep ENABLE_NUDGE_SCHEDULER **off** in .env. It would run an in-process scheduler in every
  gunicorn worker and duplicate sends. The timers replace it.
- Turn off the nudge/reminder Scheduled Tasks on PythonAnywhere, or users get emails twice.
- Use a real database (PostgreSQL/MySQL) in production. The row lock that prevents double-sends
  does nothing on SQLite.
- Nudge rules already in code: free plan only, verified, opted in, registered 3+ days,
  7 days between nudges, max 4 per user.
