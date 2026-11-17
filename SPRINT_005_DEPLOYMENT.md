# Sprint 005 deployment checklist

Sprint 005 makes application-code changes only. It introduces **no database migration**.

## Before deployment

- [ ] Back up the production database using the existing PythonAnywhere backup/deploy procedure.
- [ ] Confirm `PAYSTACK_SECRET_KEY` and `PAYSTACK_WEBHOOK_SECRET` are set for the intended Paystack environment.
- [ ] Confirm `INTASEND_SECRET_KEY`, `INTASEND_PUBLISHABLE_KEY`, `INTASEND_WEBHOOK_CHALLENGE`, and `INTASEND_ENV` are set for the intended IntaSend environment.
- [ ] Confirm Paystack webhook points to `/webhooks/paystack`.
- [ ] Confirm IntaSend collection webhook points to `/webhooks/intasend` and uses the configured challenge.
- [ ] Confirm no production `.env`, database, `instance/`, or migration directory is included in the deployment package.

## After deployment

- [ ] Confirm the public pricing page still offers the intended Paystack and IntaSend methods.
- [ ] Run one Paystack sandbox transaction and verify the subscription activates once.
- [ ] Run one IntaSend sandbox M-Pesa transaction and verify the invoice amount, currency and reference match before activation.
- [ ] Run a failed/cancelled sandbox attempt and confirm it does not activate a subscription.
- [ ] Confirm admin payment history shows the correct provider and transaction reference.
- [ ] Confirm admin growth revenue separates Paystack and IntaSend records and currencies.
- [ ] Confirm the production migration directory and its contents are unchanged.

## No migration command

Do not run `flask db upgrade`, `flask db-init`, or any schema migration as part of this Sprint 005 application deployment. If a future sprint requires a schema change, it must be reviewed, backed up and applied through a separate controlled migration procedure.
