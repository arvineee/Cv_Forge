"""Prepaid AI credits for usage beyond a plan's included daily allowances."""
from app.models import db, AICreditWallet, AICreditTransaction, AIUsage

CREDIT_PACKAGES = {
    "starter": {"credits": 30, "price_kes": 199, "name": "Starter", "description": "30 extra AI actions"},
    "plus": {"credits": 100, "price_kes": 499, "name": "Plus", "description": "100 extra AI actions"},
    "pro": {"credits": 250, "price_kes": 999, "name": "Power", "description": "250 extra AI actions"},
}
FEATURES = {"cv_generate", "cv_parse", "cv_revamp", "cover_letter", "ats_check", "career_coach"}

def get_wallet(user_id, create=False, lock=False):
    query = AICreditWallet.query.filter_by(user_id=user_id)
    if lock:
        query = query.with_for_update()
    wallet = query.first()
    if wallet is None and create:
        wallet = AICreditWallet(user_id=user_id, balance=0)
        db.session.add(wallet)
        db.session.flush()
    return wallet

def balance_for(user_id):
    wallet = get_wallet(user_id)
    return wallet.balance if wallet else 0

def grant_purchase(user_id, reference, credits, description):
    """Grant once per provider reference; caller commits with the payment."""
    if AICreditTransaction.query.filter_by(reference=reference).first():
        return False
    wallet = get_wallet(user_id, create=True, lock=True)
    wallet.balance += int(credits)
    db.session.add(AICreditTransaction(user_id=user_id, reference=reference, kind="purchase",
        amount=int(credits), balance_after=wallet.balance, description=description))
    return True

def can_use_credit(user_id):
    return balance_for(user_id) > 0

def spend_credit_if_over_limit(user_id, feature):
    """Spend one credit only when this successful request is beyond plan allowance."""
    if feature not in FEATURES:
        return True
    from app.services.entitlements import get_daily_limit
    from app.models import User
    user = db.session.get(User, user_id)
    if not user:
        return False
    used = AIUsage.get_daily_count(user_id, feature)
    if used < get_daily_limit(user, feature, fallback_limit=3):
        return True
    wallet = get_wallet(user_id, lock=True)
    if not wallet or wallet.balance < 1:
        return False
    wallet.balance -= 1
    db.session.add(AICreditTransaction(user_id=user_id, reference=f"usage:{feature}:{__import__('uuid').uuid4().hex}",
        kind="usage", amount=-1, balance_after=wallet.balance, description=f"Extra {feature.replace('_', ' ')}"))
    return True
