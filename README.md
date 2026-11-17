# CVForge AI

AI-powered CV and resume builder for job seekers worldwide (built in Kenya) — guided step-by-step CV wizard with inline AI writing help, CV parsing and AI revamp, ATS scoring, cover letter generation, PDF/DOCX export, public CV sharing, and payments via Paystack (cards) and IntaSend (M-Pesa in Kenya). Flask, deployed on PythonAnywhere.

## Quick Setup

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in your keys — see Environment Variables below

# Initialize DB and seed default data
flask db-init

# Existing installations: run only after the repository's migration history
# has been initialized and reconciled with the live schema.
flask db upgrade

# Create your admin account
flask create-admin

# Run
flask run
```

> **Migration status:** this source snapshot does not include a committed `migrations/` history. `flask db upgrade` is therefore not ready to run until a baseline is generated and reconciled with the actual database schema. Use `flask db-init` only for a fresh local database; never use it as a production upgrade strategy.

## Environment Variables

| Variable | Required for | Notes |
|---|---|---|
| `SECRET_KEY` | Everything | Flask session/CSRF signing |
| `DATABASE_URL` | Everything | Optional locally (defaults to `instance/cvforge.db`); set the production database URL in the hosting environment |
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
- `/admin/growth` — Founder growth dashboard: registration, CV activation, paid-customer conversion, and successful revenue grouped by currency and payment provider
- `/admin/users` — User management (includes impersonate, audit-logged)
- `/admin/pricing` — Edit pricing plans (name, price, features, limits, and per-plan toggles for DOCX export, version history, AI Career Coach, and public CV sharing)
- `/admin/templates` — Manage CV templates (add/edit/enable/disable)
- `/admin/payments` — Payment history (Paystack and IntaSend)
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
- **Payments** — M-Pesa (STK Push) via IntaSend; debit/credit cards via Paystack hosted checkout (see `PAYSTACK_SETUP.md`). Prices and charges are in KES; no multi-currency pricing. Paystack and IntaSend are the only configured payment providers. Both providers are verified server-to-server against the stored order before subscription activation.
- **Email verification gate** — new email/password signups can't log in until they verify their email (`auth.login` blocks unverified users and offers a resend link via `auth.resend_verification`, which is email-based rather than login-gated so a stuck user can still request a new link). Google OAuth signups are pre-verified by Google and skip this gate.
- **AI Support Chat** — Gemini-powered, grounded in a static product-facts block so it won't invent pricing or features; rate-limited by IP since it's reachable without login
- **Admin visitor tracking** — lightweight page-view log with truncated IPs, not a full analytics replacement
- **Free-tier nudge emails** — capped, respects newsletter opt-out, run via scheduled CLI command

## Deployment

The GitHub Actions deployer (`scripts/pa_deploy.py`) uploads application code to PythonAnywhere while preserving production state. It explicitly skips every directory named `migrations` (including root `migrations/` and `app/migrations/`), even if a migration file is already tracked by Git. `.gitignore` also excludes those directories so new local migration files are not accidentally committed.

**Migration protection is intentional:** production migration history is managed on the deployment environment and must not be overwritten by an ordinary application-code deploy. The deployer does not upload migration files and does not delete files already present on the server. If a schema change is needed, create/review/apply it through a separate, controlled migration procedure after backing up the production database. Do not rely on `.gitignore` alone: Git continues tracking files already in its index, which is why the deploy script has its own migration-directory exclusion.

If you also want to stop tracking a migration directory in the Git repository, run the appropriate command from the repository root (this keeps your local files in place):

```bash
git rm -r --cached --ignore-unmatch migrations app/migrations
git add .gitignore
git commit -m "Keep deployment migration history out of Git uploads"
```

The command only removes files from Git's index; it does not delete the local migration directory. Confirm the paths match your repository before committing.

## Sprint 005 payment integrity

- Paystack confirmation checks the verified transaction status, reference, amount in minor units, currency, and customer email when supplied.
- IntaSend completion and failure notifications are challenge-checked, then independently confirmed against the IntaSend invoice-status API. The invoice ID, CVForge reference, amount, currency, state, local payment, and subscription must match before access changes.
- Checkout stores a compact order snapshot in the existing `Payment.raw_webhook` JSON field, including plan slug, billing period, amount, currency and user ID. The billing period used for activation therefore remains the one purchased even if an administrator edits the plan while checkout is pending.
- Payment events are idempotent, provider transaction IDs are checked for reuse, and stored event metadata is allow-listed rather than saving the full webhook body or IntaSend challenge.
- Existing `lipana_*` database column names are retained as legacy storage fields and exposed in Python as provider-neutral aliases. This avoids a production schema migration and preserves historical payment records; it does not enable Lipana as a provider.
- Plan-specific daily CV, cover-letter and ATS limits now use the existing `PricingPlan` fields. No new database columns or migrations are introduced.
- Revenue views show gross successful payment records by currency and provider. They are not net settlement reports and do not subtract provider fees, refunds or chargebacks that are not recorded in CVForge.

## Payment methods on/off

Admin -> **Payment methods** switches Paystack and IntaSend on or off for *new* checkouts. Nothing is disconnected: keys, webhooks and callbacks stay live, so payments already in progress still confirm. The state is stored in `instance/payment_settings.json` (survives deploys, no migration). With IntaSend off and Paystack on, the pay button reads "card or M-Pesa" because Paystack's checkout also offers M-Pesa (enable it on the Paystack dashboard).

## Known Issues / Caveats

- **PythonAnywhere free tier blocks outbound SMTP** — verification, password reset, and nudge emails will fail with `Network is unreachable` until you either upgrade your PythonAnywhere plan or switch `email_service.py` to an HTTP-based email API.
- **SQLite strips tzinfo on read-back**, even on `DateTime(timezone=True)` columns. The app's convention is naive UTC via `models.utcnow()` on write, and `models._make_aware()` before any comparison against a DB-read datetime. Follow this pattern for any new expiry/timestamp field, or you'll hit `TypeError: can't compare offset-naive and offset-aware datetimes`.
- **`with_for_update()` row locking in the webhook handler is a no-op on SQLite** — it only actually prevents concurrent double-processing on Postgres/MySQL. The `status == "active"` idempotency check still helps in the meantime.
- **IntaSend sandbox and live are separate accounts** (`sandbox.intasend.com` vs `payment.intasend.com`), not a dashboard toggle. Mismatched keys/env produce a confusing `authentication_failed: Invalid token for sandbox environment` error rather than a clear "wrong account" message — `IntaSendService` logs its resolved mode (`SANDBOX`/`LIVE`) on every init to make this easier to catch.
- **`GEMINI_MODEL`** — verify the configured model id is available to your Google AI project and region before deploying. The application uses Google's supported `google-genai` Python SDK.
- **Blueprint modules live under `app/routes/`** (e.g. `app/routes/cv.py`, `app/routes/dashboard.py`, `app/routes/auth.py`), not directly under `app/`. Cross-file imports between blueprints must use the full `app.routes.<module>` path — a plain `from app.cv import ...` will raise `ModuleNotFoundError` in production even though it may look fine locally depending on your `sys.path`.
- **No `"free"` plan row currently exists** in the pricing table (see CLI Commands note above) — don't assume `PricingPlan.query.filter_by(slug="free")` will resolve to anything.
- **`User.is_premium` only recognizes `"pro"`/`"premium"`**, not `"basic"` — a paying Basic subscriber is never `is_premium`. Anything gating a feature on "has the user paid at all" should use `_has_active_paid_plan()` in `cv.py`, not `is_premium`.

## Prior Audit Summary

An earlier pass fixed: unified AI service imports, missing `cv.restore_version` route, a broken `{% include %}`-in-comment template bug, missing-field crashes on public CV pages, XSS-safe cover letter rendering, timezone-aware usage counting, webhook HMAC verification, CSRF-protected admin impersonation, deprecated `.query.get()` calls, a redundant `is_pro` flag, explicit version ordering, an admin-editable `PricingPlan` model, and `BytesIO`-based cover letter downloads. Full CLI tooling (`create-user`, `seed-plans`, `seed-templates`, `stats`, etc.) and 12 seeded CV templates were also added in that pass.

A later pass added the guided CV wizard, AI Career Coach, per-plan public-link sharing, and shifted monetization from a login-time paywall to the pay-to-download model described above; fixed a missing CSRF token on the admin nudges form; and reworked the email-verification flow so unverified users can no longer log in at all (previously verification was optional after registration).



## International SEO / public site address

Set `SITE_URL` (for example `https://cvforgeai.com`) in the environment so canonical links, Open Graph URLs, the sitemap, `robots.txt` and JSON-LD always use your public domain, even when the site is also reachable on another host such as `cvforge.pythonanywhere.com`. If it is blank, the address of each incoming request is used.

Public marketing copy that is shared between a page and its structured data (FAQs, default title/description/keywords) lives in `app/services/site_content.py`. Sitemap pages and robots rules are in `app/routes/seo.py`.

## Auto-deploy (GitHub Actions → PythonAnywhere)

Every push to `main` runs the tests, then `scripts/pa_deploy.py` uploads the git-tracked app files through the PythonAnywhere API and reloads the web app (`.github/workflows/deploy.yml`). It never uploads `.env`, databases, `instance/`, `uploads/`, tests, caches or any `migrations/` directory, so production data, secrets and deployment-managed migration history stay as they are.

One-time setup in GitHub → Settings → Secrets and variables → Actions:

| Type | Name | Example |
|---|---|---|
| Secret | `PA_USERNAME` | your PythonAnywhere username |
| Secret | `PA_API_TOKEN` | PythonAnywhere → Account → API token |
| Variable | `PA_PROJECT_DIR` | `/home/<username>/<project folder>` |
| Variable | `PA_DOMAIN` | `cvforge.pythonanywhere.com` (or your custom domain) |
| Variable | `PA_HOST` | only for EU accounts: `eu.pythonanywhere.com` |

Notes: files deleted from git are not deleted on the server, and new dependencies in `requirements.txt` still need `pip install` in a PythonAnywhere console. Preview what would upload with `python scripts/pa_deploy.py --dry-run`.

## Sprint 003 — First CV conversion

This release adds first-time onboarding, direct guided-CV entry, dashboard draft recovery, debounced wizard autosave, first-CV conversion events, an admin conversion funnel (`/admin/conversion`), and opt-out-aware abandoned-CV email reminders.

No database migration is required. See `SPRINT_003_CHANGELOG.md` for the feature list and validation status, and `SPRINT_003_DEPLOYMENT.md` for backup, staging, credential-rotation and PythonAnywhere scheduled-task instructions. The reminder task is opt-in and must be scheduled deliberately with `flask send-cv-reminders` after staging email verification.

## Sprint 006 growth, conversion and retention

- First-touch UTM attribution is captured for new email and Google registrations using the existing signed browser session and `ActivityLog.details`; no new database fields are required. Stored page-visit referrers drop query strings/fragments and redact secret token paths.
- `/admin/growth` now reports signup-cohort activation and paid conversion, source/medium and campaign signups, active users, repeat-active users and gross payment records grouped by currency/provider.
- `/admin/conversion` now uses the same shared cohort report and supports 7-, 30- and 90-day windows. Activation means a user completed a meaningful first CV draft; first download is reported separately.
- Pro upgrade nudges now enforce a four-successful-send lifetime cap per user, a seven-day cooldown, a three-day signup grace period and the newsletter opt-out. The CLI and scheduler report the same result contract.
- Profile settings expose separate controls for CV progress service reminders, product/Pro marketing emails and account-linked analytics. New accounts start opted out of product/Pro marketing emails; Pro nudges and admin product broadcasts respect that opt-out. Disabling account-linked analytics removes signup attribution and anonymizes previously linked page-visit rows.
- Unfinished-CV service reminders respect the dedicated CV progress reminder preference, separate from the marketing newsletter preference.
- No database schema change or migration is included. See `CVFORGE_SPRINT_006_GROWTH_AUDIT.md`, `SPRINT_006_CHANGELOG.md` and `SPRINT_006_DEPLOYMENT.md`.

**Measurement caveat:** campaign signups are not CAC. CVForge still needs verified campaign-spend records and net contribution reporting (provider fees, refunds, reversals, AI and variable support costs) before it can make reliable profitability or LTV/CAC decisions.
