# CVForge AI

AI-powered CV/resume builder for the Kenyan market — guided step-by-step CV wizard with inline AI writing help, CV parsing and AI revamp, ATS scoring, cover letter generation, PDF/DOCX export, public CV sharing, and M-Pesa + card payments. Flask, deployed on PythonAnywhere.

## Quick Setup

```bash
pip install -r requirements.txt
pip install intasend-python   # for M-Pesa / card payments
cp .env.example .env          # fill in your keys — see Environment Variables below

# Initialize DB and seed default data
flask db-init

# Apply migrations (required after pulling recent changes —
# new PageVisit table, new UserSettings/User columns, new
# PricingPlan.allow_public_link column)
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
| `GEMINI_API_KEY` | AI features | CV assist, revamp, ATS, AI Career Coach, support chat |
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
| `flask set-plan user@email.com pro` | Set plan (slug must match an active `PricingPlan` row — see note below) |
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

> **Note on plan slugs:** there is currently no `"free"` plan row in the pricing table — the live catalog starts at `basic` (KES 50/month), then `pro`, then `premium`. New users still default to the string `"free"` on `User.plan` at signup, but since no plan row resolves for that slug, they simply have no active paid plan until they subscribe. Access to the dashboard and CV wizard is unrestricted either way — see **Pay-to-Download Model** below for what's actually gated.

## Admin Panel Routes

- `/admin/` — Dashboard
- `/admin/users` — User management (includes impersonate, audit-logged)
- `/admin/pricing` — Edit pricing plans (name, price, features, limits, and per-plan toggles for DOCX export, version history, AI Career Coach, and public CV sharing)
- `/admin/templates` — Manage CV templates (add/edit/enable/disable)
- `/admin/payments` — Payment history (M-Pesa + card)
- `/admin/visitors` — Site visitor tracking: page views, unique visitors, top pages, per-day breakdown
- `/admin/nudges` — Manually trigger the free-tier upgrade nudge email batch

## Key Features

- **Guided CV Wizard** — step-by-step, one section per page (personal info → summary → work experience → education → skills → certifications → review), with an inline "Enhance with AI" pass on the sections that benefit from it. This is now the default CV creation flow; the older single-page builder still exists underneath but isn't the primary entry point.
- **AI Revamp** (Gemini) — rewrites summary, work experience, and skills; preserves job titles and bullet structure rather than flattening to prose
- **AI Career Coach** (Premium) — at the wizard's review step, gives a direct, line-by-line critique of the finished CV: what's weak, what's missing, exactly how to fix it. Lower tiers see a rule-based (non-AI) gaps checklist at the same step instead, with an upgrade nudge.
- **Pay-to-Download Model** — the CV wizard, AI writing help, and ATS checks are all usable without paying. Payment is required at the moment of download: `cv.download()` checks for an active, unexpired paid subscription (basic/pro/premium) before releasing a PDF or DOCX. Unpaid users see a watermarked preview of their actual CV (real content, blurred bullet text, tiled "SAMPLE" overlay) next to the upgrade CTA instead of a working download link.
- **Public CV Sharing** — a shareable, no-login-required public link per CV (`cv.toggle_public`), gated behind an active paid plan (`_plan_allows_public_link()` in `cv.py`) and further controllable per-tier via each plan's `allow_public_link` flag in `/admin/pricing`. The public CV page itself doubles as a growth funnel — real name/role in the page's meta description for link-preview cards, plus a "Build your own free" CTA banner.
- **ATS Checker** — score a saved CV, or upload a file directly with no job description required for a general audit; add a job description for a targeted match analysis
- **Cover Letter Generator** — tone-adjustable, resume-aware
- **Export** — PDF and DOCX, both gated behind an active paid plan; DOCX is additionally restricted to plans with `allow_docx` set. DOCX generator has full section parity with PDF (certifications, achievements, languages, interests, awards, projects, publications, volunteer, references)
- **Payments** — M-Pesa (STK Push) and card, both via IntaSend; card uses IntaSend's hosted Checkout, M-Pesa is inline. Both share one webhook handler.
- **Email verification gate** — new email/password signups can't log in until they verify their email (`auth.login` blocks unverified users and offers a resend link via `auth.resend_verification`, which is email-based rather than login-gated so a stuck user can still request a new link). Google OAuth signups are pre-verified by Google and skip this gate.
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
- **Blueprint modules live under `app/routes/`** (e.g. `app/routes/cv.py`, `app/routes/dashboard.py`, `app/routes/auth.py`), not directly under `app/`. Cross-file imports between blueprints must use the full `app.routes.<module>` path — a plain `from app.cv import ...` will raise `ModuleNotFoundError` in production even though it may look fine locally depending on your `sys.path`.
- **No `"free"` plan row currently exists** in the pricing table (see CLI Commands note above) — don't assume `PricingPlan.query.filter_by(slug="free")` will resolve to anything.
- **`User.is_premium` only recognizes `"pro"`/`"premium"`**, not `"basic"` — a paying Basic subscriber is never `is_premium`. Anything gating a feature on "has the user paid at all" should use `_has_active_paid_plan()` in `cv.py`, not `is_premium`.

## Prior Audit Summary

An earlier pass fixed: unified AI service imports, missing `cv.restore_version` route, a broken `{% include %}`-in-comment template bug, missing-field crashes on public CV pages, XSS-safe cover letter rendering, timezone-aware usage counting, webhook HMAC verification, CSRF-protected admin impersonation, deprecated `.query.get()` calls, a redundant `is_pro` flag, explicit version ordering, an admin-editable `PricingPlan` model, and `BytesIO`-based cover letter downloads. Full CLI tooling (`create-user`, `seed-plans`, `seed-templates`, `stats`, etc.) and 12 seeded CV templates were also added in that pass.

A later pass added the guided CV wizard, AI Career Coach, per-plan public-link sharing, and shifted monetization from a login-time paywall to the pay-to-download model described above; fixed a missing CSRF token on the admin nudges form; and reworked the email-verification flow so unverified users can no longer log in at all (previously verification was optional after registration).

