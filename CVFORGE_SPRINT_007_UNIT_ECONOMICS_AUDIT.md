# CVForge Sprint 007 — Unit Economics & International Readiness

## Objective
Make profitability measurable without rewriting working CVForge features or changing the production database schema.

## Implemented
- Added a read-only admin unit-economics report at `/admin/unit-economics`.
- Added 7/30/90-day views.
- Reports successful gross collections by currency, never adding unlike currencies.
- Breaks gross collections down by existing payment method/provider and currency.
- Reports AI usage by feature, request count, recorded tokens and token-data coverage.
- Explicitly lists missing cost inputs instead of presenting gross collections as profit.
- Added a link from the admin dashboard.
- Added regression tests for currency-safe reporting, missing cost disclosure and reporting-window validation.

## Findings / limitations
The existing schema does not provide a complete source of truth for processor fees, settlement deductions, refunds/chargebacks, marketing spend, or consistently recorded AI tokens. Consequently this sprint does not claim CAC, net revenue, contribution margin, LTV or profitability. These require reliable source data and reconciliation before calculations can be trusted.

## Preserved
- Paystack and IntaSend only.
- Existing payment and subscription flows.
- Existing growth dashboard and acquisition attribution.
- Existing schema and migration history; no migrations added or modified.
- Existing deployment migration protection.

## Validation
Python compilation passed. Full application tests require the project's Flask dependencies and should be run in staging. No production deployment or live payment test was performed.
