# AI credit wallet deployment

This release adds two tables and a new Alembic revision. Before deployment, take a database backup.

1. Deploy the code and run `flask db upgrade` from the project virtualenv.
2. Confirm Paystack and/or IntaSend is enabled under Admin → Payment methods and provider webhook URLs remain configured.
3. Test with provider test credentials first. Verify a successful transaction creates exactly one `ai_credit_transactions` purchase row and updates `ai_credit_wallets.balance`.
4. Verify pending/failed transactions do not add credits and replaying a webhook does not grant twice.
5. Test daily included allowances first, then verify an eligible extra AI request debits exactly one credit.

Credit packs are currently fixed at 30 credits / KES 199, 100 / KES 499 and 250 / KES 999 in `app/services/ai_credits.py`. Review pricing against actual AI provider costs and fees before public launch.

Do not manually edit wallet balances in SQL. The ledger is the audit trail. The current checkout remains KES-only and uses existing enabled providers.
