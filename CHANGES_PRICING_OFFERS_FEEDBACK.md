# Pricing, Offers and Feedback

## What changed

### Pricing
- Plan durations now follow the plan's billing period: `week` = 7 days,
  `month` = 30 days, `year` = 365 days. Previously every payment was hardcoded
  to 30 days in both `Subscription.activate()` and the webhook.
- The admin plan form has a "Weekly pass (7 days)" option, next to Monthly and
  Yearly. Free is labelled "Free (no payment)".
- Every price on the site is read from the `pricing_plans` table. The landing
  page, pricing page, billing page, CV wizard upgrade box, and upgrade emails
  all use the same source as checkout. Previously the upgrade email hardcoded
  "From KES 50" and the seed data disagreed with the live catalogue.

### Offers (admin: /admin/offers)
- Create time-limited discounts: percent (1–90) or a fixed KES amount.
- Apply to all paid plans, or only selected plans.
- Optional start and end time (entered in Nairobi time), optional seat limit.
- **Void** stops an offer immediately. **Restore** brings it back, subject to
  its dates and seat limit.
- Prices never change in the database. Offers are an overlay computed on each
  request, so when an offer expires, sells out, or is voided, the base price
  returns automatically with no cron job and nothing to undo.
- Checkout recalculates the price on the server. The browser never sends an
  amount, so a voided offer cannot be charged, even from a stale page.
- Each offer-backed checkout creates an `offer_redemptions` row:
  `pending` holds a seat, `redeemed` on payment success, `released` on failure.
  Pending seats stop counting after 30 minutes, so abandoned checkouts do not
  block an offer.

### Feedback (users: /feedback, admin: /admin/feedback)
- Public form, works logged in or out. Categories: general, bug, feature,
  pricing, CV/AI quality. Optional 1–5 rating and optional email for anonymous users.
- Spam controls: honeypot field and a limit of 5 submissions per IP per hour.
- Admin can filter by status and category, see the average rating, set
  status (new / reviewed / resolved), and add an internal note.
- "Feedback" is in the user sidebar. "User Feedback" and "Offers & Discounts"
  are in the admin dashboard.

## Deploying

No existing column was altered. Three new tables are created: `offers`,
`offer_redemptions`, `feedback`.

    flask db-init        # safe on an existing DB: creates only missing tables,
                         # and seeding is skipped when plans already exist

If you use Flask-Migrate migrations in your own repo, generate one instead
(`flask db migrate -m "offers, feedback"`) and then `flask db upgrade`.

Then restart the web app.

## Tests
- `tests/test_offers_logic.py`: 17 tests of discount math, expiry, scheduled
  start, voiding, sell-out, restore, per-plan scoping, best-offer selection,
  free-plan protection, banner visibility, and Nairobi-to-UTC time parsing.
  These run without the database.
- Not covered by automated tests: database queries, the checkout routes, the
  webhook handlers, and the admin forms. Test them with the flows below before
  going live.

## Manual test checklist (run in sandbox first)
1. Create "Test 30% off Pro", ends in 5 minutes. Pricing page shows strikethrough and badge.
2. Start checkout. Confirm the amount sent to IntaSend is the discounted price.
3. Wait for expiry (or void it). Pricing page and checkout return to base price.
4. Set max seats to 1. Complete one payment, then confirm the offer shows "Sold out".
5. Confirm a successful payment's subscription lasts the plan's length (7/30/365 days).
6. Submit feedback logged out and logged in. Check it appears in /admin/feedback.
