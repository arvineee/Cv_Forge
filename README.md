# CVForge AI

## Quick Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # fill in your keys

# Initialize DB and seed default data
flask db-init

# Create your admin account
flask create-admin

# Run
flask run
```

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

## Admin Panel Routes

- `/admin/` — Dashboard
- `/admin/users` — User management
- `/admin/pricing` — Edit pricing plans (name, price, features, limits)
- `/admin/templates` — Manage CV templates (add/edit/enable/disable)
- `/admin/payments` — Payment history

## Fixes Applied (from audit)

1. ✅ Import path unified: all routes use `from app.ai_service import get_ai_service`
2. ✅ `cv.restore_version` route added
3. ✅ `pricing.html` no longer uses broken `{% include %}` with extending template
4. ✅ `cv/public.html` uses `.get()` — no crash on missing fields
5. ✅ `dashboard/index.html` created
6. ✅ `cover_letter/view.html` XSS-safe via Alpine `x-text` (no `|safe` on user content)
7. ✅ `AIUsage.get_daily_count` timezone-aware UTC
8. ✅ Webhook HMAC signature verification added
9. ✅ Admin impersonate is POST (CSRF-protected)
10. ✅ `User.query.get()` replaced with `db.session.get()`
11. ✅ `is_pro` removed (redundant); only `is_premium` used
12. ✅ `ResumeVersion` relationship has no `order_by` — use explicit `.order_by()` in queries
13. ✅ `PricingPlan` model added — admin-editable, drives billing pages
14. ✅ `Template.accent_color` field added
15. ✅ `billing/index.html` created (was missing)
16. ✅ Cover letter download uses `BytesIO` (not `StringIO`)
17. ✅ Monkey-patch in `ai_service.py` removed; `AIUsage.log_usage` is a clean classmethod
18. ✅ CLI commands: create-user, create-admin, promote-admin, set-plan, reset-password, list-users, seed-plans, seed-templates, stats, db-init
19. ✅ 12 CV templates seeded via `flask seed-templates`
20. ✅ `next_page` redirect validated via `urlparse().netloc == ""`
# Cv_Forge
