# CVForge AI

AI-powered CV/resume builder for the Kenyan market — CV parsing and AI revamp, ATS scoring, cover letter generation, PDF/DOCX export, and M-Pesa + card payments. Flask, deployed on PythonAnywhere.

## Quick Setup

```bash
pip install -r requirements.txt
pip install intasend-python   # for M-Pesa / card payments
cp .env.example .env          # fill in your keys — see Environment Variables below

# Initialize DB and seed default data
flask db-init

# Apply migrations (required after pulling recent changes —
# new PageVisit table, new UserSettings/User columns)
flask db upgrade

# Create your admin account
flask create-admin

# Run
flask run
```

## Environment Variables

| Variable | Required for | Notes |
|---|---|---|
| `SECRET_KEY` | Everything | Flask session/CSRF signing |
| `SQLALCHEMY_DATABASE_URI` | Everything | Defaults to local SQLite |
| `GEMINI_API_KEY` | AI features | CV assist, revamp, ATS, support chat |
| `GEMINI_MODEL` | AI features | Verify against Google's current model list before deploying |
| `GEMINI_DAILY_LIMIT` / `GEMINI_FREE_USER_DAILY_LIMIT` | AI features | Platform-wide / per-free-user daily caps |
| `INTASEND_SECRET_KEY` / `INTASEND_PUBLISHABLE_KEY` | Payments | From `sandbox.intasend.com` (testing) or `payment.intasend.com` (live) — these are **separate accounts**, not a toggle |
| `INTASEND_ENV` | Payments | `sandbox` or `production` — must match which dashboard your keys came from |
| `INTASEND_WEBHOOK_CHALLENGE` | Payments | Static string you set in the IntaSend webhook config — must match exactly |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_DEFAULT_SENDER` | Email | Verification, password reset, Pro nudge emails. **SMTP is blocked on PythonAnywhere's free tier** — see Known Issues |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google login | OAuth credentials |
| `UPLOAD_FOLDER` | CV uploads | Absolute or relative path for uploaded CV files |

## CLI Commands

| Command | Description |
|---|---|
| `flask db-init` | Create tables + seed plans & templates |
| `flask create-admin` | Create an admin user interactively |
| `flask create-user` | Create any user with options |
| `flask create-user --admin --plan pro` | Create pro admin non-interactively |
| `flask promote-admin user@email.com` | Grant admin to existing user |
| `flask set-plan user@email.com pro` | Set plan (free/pro/premium) |
| `flask set-plan user@email.com pro --days 365` | Set plan for 1 year |
| `flask reset-password user@email.com` | Reset a user's password |
| `flask list-users` | List all users |
| `flask list-users --plan pro` | Filter by plan |
| `flask list-users --admin-only` | List admins only |
| `flask seed-plans` | Seed default pricing plans |
| `flask seed-templates` | Seed 12 default CV templates |
| `flask stats` | Print platform stats |
| `flask send-nudges` | Email free-tier users an occasional Pro-upgrade reminder (capped, opt-out respected) — schedule daily via PythonAnywhere Tasks |
| `flask prune-visits` | Delete visitor-tracking rows older than 90 days |

## Admin Panel Routes

- `/admin/` — Dashboard
- `/admin/users` — User management (includes impersonate, audit-logged)
- `/admin/pricing` — Edit pricing plans (name, price, features, limits)
- `/admin/templates` — Manage CV templates (add/edit/enable/disable)
- `/admin/payments` — Payment history (M-Pesa + card)
- `/admin/visitors` — Site visitor tracking: page views, unique visitors, top pages, per-day breakdown

## Key Features

- **CV Builder** — manual entry or upload an existing PDF/DOCX to auto-fill
- **AI Revamp** (Gemini) — rewrites summary, work experience, and skills; preserves job titles and bullet structure rather than flattening to prose
- **ATS Checker** — score a saved CV, or upload a file directly with no job description required for a general audit; add a job description for a targeted match analysis
- **Cover Letter Generator** — tone-adjustable, resume-aware
- **Export** — PDF (all plans) and DOCX (Pro only); DOCX generator has full section parity with PDF (certifications, achievements, languages, interests, awards, projects, publications, volunteer, references)
- **Payments** — M-Pesa (STK Push) and card, both via IntaSend; card uses IntaSend's hosted Checkout, M-Pesa is inline. Both share one webhook handler.
- **AI Support Chat** — Gemini-powered, grounded in a static product-facts block so it won't invent pricing or features; rate-limited by IP since it's reachable without login
- **Admin visitor tracking** — lightweight page-view log with truncated IPs, not a full analytics replacement
- **Free-tier nudge emails** — capped, respects newsletter opt-out, run via scheduled CLI command

## Deployment

`deploy_update.sh` pulls the latest code from GitHub onto PythonAnywhere without clobbering your live `.env`, database, or migrations:

```bash
./deploy_update.sh                 # pull, restore protected files, migrate, reload
./deploy_update.sh --restore-only  # emergency rollback to latest backup
```

See the script's header comment for the full backup/restore behavior and configuration variables.

## Known Issues / Caveats

- **PythonAnywhere free tier blocks outbound SMTP** — verification, password reset, and nudge emails will fail with `Network is unreachable` until you either upgrade your PythonAnywhere plan or switch `email_service.py` to an HTTP-based email API.
- **SQLite strips tzinfo on read-back**, even on `DateTime(timezone=True)` columns. The app's convention is naive UTC via `models.utcnow()` on write, and `models._make_aware()` before any comparison against a DB-read datetime. Follow this pattern for any new expiry/timestamp field, or you'll hit `TypeError: can't compare offset-naive and offset-aware datetimes`.
- **`with_for_update()` row locking in the webhook handler is a no-op on SQLite** — it only actually prevents concurrent double-processing on Postgres/MySQL. The `status == "active"` idempotency check still helps in the meantime.
- **IntaSend sandbox and live are separate accounts** (`sandbox.intasend.com` vs `payment.intasend.com`), not a dashboard toggle. Mismatched keys/env produce a confusing `authentication_failed: Invalid token for sandbox environment` error rather than a clear "wrong account" message — `IntaSendService` logs its resolved mode (`SANDBOX`/`LIVE`) on every init to make this easier to catch.
- **`GEMINI_MODEL`** — verify the configured model id is still current for your `google-generativeai` SDK version before deploying; `google-generativeai` itself is deprecated in favor of `google-genai` (still functional, no further updates).

## Prior Audit Summary

An earlier pass fixed: unified AI service imports, missing `cv.restore_version` route, a broken `{% include %}`-in-comment template bug, missing-field crashes on public CV pages, XSS-safe cover letter rendering, timezone-aware usage counting, webhook HMAC verification, CSRF-protected admin impersonation, deprecated `.query.get()` calls, a redundant `is_pro` flag, explicit version ordering, an admin-editable `PricingPlan` model, and `BytesIO`-based cover letter downloads. Full CLI tooling (`create-user`, `seed-plans`, `seed-templates`, `stats`, etc.) and 12 seeded CV templates were also added in that pass.

