# CVForge Paystack setup

The Paystack integration uses hosted checkout. CVForge sends the amount from its own pricing/offer calculation to Paystack; the browser never supplies the amount and never receives the secret key.

## 1. Configure the environment

Add these environment variables to the PythonAnywhere web app (or your local `.env`, which must never be committed):

```ini
PAYSTACK_SECRET_KEY=sk_test_REPLACE_WITH_YOUR_TEST_SECRET
PAYSTACK_WEBHOOK_SECRET=whsec_REPLACE_WITH_YOUR_WEBHOOK_SIGNING_SECRET
PAYSTACK_BASE_URL=https://api.paystack.co
```

`PAYSTACK_PUBLIC_KEY` is optional and is not used by this hosted-checkout implementation. Do not paste keys into source files, GitHub, support tickets, or chat.

## 2. Paystack dashboard

1. Create/verify the Paystack business account and enable the channels/currencies approved for the account.
2. Start with Test Mode and copy the Test Secret Key into `PAYSTACK_SECRET_KEY`.
3. In the Paystack developer/API settings, create a webhook signing secret if the dashboard offers the current `Paystack-Signature` format, then put its full value (including `whsec_`) in `PAYSTACK_WEBHOOK_SECRET`.
4. Set the webhook URL to:

   `https://cvforge.pythonanywhere.com/webhooks/paystack`

5. Subscribe to `charge.success`.
6. The callback URL is passed per transaction by CVForge:

   `https://cvforge.pythonanywhere.com/billing/paystack/callback`

The webhook endpoint accepts the current timestamped `Paystack-Signature` header. It also supports the legacy `x-paystack-signature` header signed with `PAYSTACK_SECRET_KEY` for accounts that have not moved to the newer webhook signing secret. Do not remove/rotate the API secret until the dashboard is delivering the new signature and it has been verified in production.

## 3. Test before going live

- Test a successful KES checkout for each paid plan.
- Test a cancelled/abandoned checkout.
- Confirm that a success redirect alone does not activate a plan; CVForge verifies the transaction server-side.
- Confirm that the webhook is accepted and that duplicate webhook deliveries do not create duplicate subscriptions or extend the plan twice.
- Confirm that the stored transaction amount, KES currency, reference, and customer email match the pending CVForge order.
- Confirm that existing M-Pesa and IntaSend card checkout still work.

For reference, Paystack expects transaction amounts in the currency's subunit. This integration converts KES to minor units (KES × 100) and checks the same amount during verification.

## 4. Deploy

1. Upload/deploy the updated source without replacing your production database or user uploads.
2. Add the environment variables in PythonAnywhere's Web tab → Environment variables (or your WSGI environment configuration).
3. Reload the web app.
4. Complete the Test Mode checklist above.
5. Only after Paystack approves live processing, replace the test secret with the Live Secret Key and configure the corresponding live webhook signing secret. Keep test and live keys separate.

No database migration is required: the integration reuses the existing `Payment`, `Subscription`, and `payment_method` fields.
