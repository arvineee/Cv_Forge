"""Read-only unit-economics baseline using existing CVForge tables.

No schema changes are required. Gross collections are kept separate by
currency; payment-provider fees, refunds, acquisition spend and model costs
are explicitly reported as unknown until their source data is integrated.
"""
from datetime import timedelta
from sqlalchemy import func
from app.models import AIUsage, Payment, db, utcnow


def build_unit_economics_report(days=30):
    days = days if days in (7, 30, 90) else 30
    cutoff = utcnow() - timedelta(days=days)
    gross_rows = (db.session.query(Payment.currency, func.sum(Payment.amount),
                                   func.count(Payment.id))
                  .filter(Payment.status == "success", Payment.created_at >= cutoff)
                  .group_by(Payment.currency).all())
    gross = [{"currency": c or "KES", "amount": int(a or 0), "payments": int(n or 0)}
             for c, a, n in gross_rows]
    provider_rows = (db.session.query(Payment.payment_method, Payment.currency,
                                      func.sum(Payment.amount), func.count(Payment.id))
                     .filter(Payment.status == "success", Payment.created_at >= cutoff)
                     .group_by(Payment.payment_method, Payment.currency).all())
    providers = [{"provider": p or "unknown", "currency": c or "KES",
                  "gross": int(a or 0), "payments": int(n or 0)}
                 for p, c, a, n in provider_rows]
    ai_rows = (db.session.query(AIUsage.feature, func.count(AIUsage.id),
                                func.sum(AIUsage.tokens_used),
                                func.sum(AIUsage.requests_used))
               .filter(AIUsage.created_at >= cutoff)
               .group_by(AIUsage.feature).all())
    ai_features = [{"feature": f or "unknown", "records": int(n or 0),
                    "tokens": int(t or 0), "requests": int(r or 0)}
                   for f, n, t, r in ai_rows]
    ai_records = sum(x["records"] for x in ai_features)
    token_records = sum(1 for x in ai_features if x["tokens"] > 0)
    return {
        "days": days, "gross_by_currency": gross, "provider_breakdown": providers,
        "ai_by_feature": ai_features,
        "ai_requests": sum(x["requests"] for x in ai_features),
        "ai_records": ai_records,
        "token_coverage_pct": round(token_records * 100 / ai_records, 1) if ai_records else 0,
        "unknown_costs": [
            "Payment processor fees and settlement deductions",
            "Refunds, chargebacks and reversals not represented as negative ledger entries",
            "Paid acquisition spend (CAC cannot be calculated without campaign spend)",
            "AI provider costs (token usage is not consistently recorded)",
            "Contribution margin and customer lifetime value",
        ],
    }
