# Sprint 007 Deployment Checklist

1. Back up the production database using the normal platform procedure.
2. Deploy the application code using the existing protected deployment workflow.
3. Do not run `flask db upgrade` for this sprint: no schema migration is included.
4. Install/confirm the existing `requirements.txt` dependencies in the deployment environment.
5. Run `python -m unittest tests.test_sprint007_unit_economics` and the existing regression suite.
6. Sign in as an administrator and open `/admin/unit-economics`.
7. Confirm payment totals remain separated by currency and provider.
8. Confirm the report labels gross collections and missing cost inputs accurately.
9. Confirm Paystack checkout and IntaSend checkout/webhooks in provider sandbox or staging before production release.

No live payment, production database, environment secret or migration history was modified while preparing this package.
