from flask import jsonify, request
from flask_login import login_required, current_user
from datetime import date
from app import db
from app.models import Patient, Debt, Payment
from app.api import api_bp


def ok(data=None, msg="", code=200):
    return jsonify({"ok": True, "message": msg, "data": data}), code


def err(msg, code=400):
    return jsonify({"ok": False, "message": msg}), code


# ─── PATIENTS ─────────────────────────────────────────────────────────────────
@api_bp.route("/patients", methods=["GET"])
@login_required
def get_patients():
    q       = request.args.get("q", "").strip()
    status  = request.args.get("status", "all")
    patients = Patient.query
    if q:
        patients = patients.filter(Patient.name.ilike(f"%{q}%"))
    patients = patients.order_by(Patient.name).all()
    if status != "all":
        patients = [p for p in patients if any(d.status == status for d in p.debts)]
    return ok([p.to_dict() for p in patients])


@api_bp.route("/patients/<int:pid>", methods=["GET"])
@login_required
def get_patient(pid):
    p = Patient.query.get_or_404(pid)
    data = p.to_dict()
    data["debts"] = [d.to_dict() for d in p.debts]
    return ok(data)


@api_bp.route("/patients", methods=["POST"])
@login_required
def create_patient():
    d = request.get_json() or {}
    if not d.get("name") or not d.get("phone"):
        return err("name and phone are required")
    p = Patient(name=d["name"], phone=d["phone"],
                email=d.get("email"), id_number=d.get("id_number"),
                gender=d.get("gender"), address=d.get("address"),
                notes=d.get("notes"))
    db.session.add(p)
    db.session.commit()
    return ok(p.to_dict(), "Patient created", 201)


@api_bp.route("/patients/<int:pid>", methods=["PATCH"])
@login_required
def update_patient(pid):
    p = Patient.query.get_or_404(pid)
    d = request.get_json() or {}
    for field in ("name", "phone", "email", "id_number", "gender", "address", "notes"):
        if field in d:
            setattr(p, field, d[field] or None)
    db.session.commit()
    return ok(p.to_dict(), "Patient updated")


@api_bp.route("/patients/<int:pid>", methods=["DELETE"])
@login_required
def delete_patient(pid):
    if not current_user.is_admin:
        return err("Admin required", 403)
    p = Patient.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return ok(msg="Patient deleted")


# ─── DEBTS ────────────────────────────────────────────────────────────────────
@api_bp.route("/debts", methods=["GET"])
@login_required
def get_debts():
    status = request.args.get("status", "all")
    debts  = Debt.query.all()
    if status != "all":
        debts = [d for d in debts if d.status == status]
    return ok([d.to_dict() for d in debts])


@api_bp.route("/debts/<int:did>", methods=["GET"])
@login_required
def get_debt(did):
    d = Debt.query.get_or_404(did)
    data = d.to_dict()
    data["payments"] = [p.to_dict() for p in d.payments]
    return ok(data)


@api_bp.route("/patients/<int:pid>/debts", methods=["POST"])
@login_required
def create_debt(pid):
    Patient.query.get_or_404(pid)
    d = request.get_json() or {}
    try:
        total   = float(d.get("total_amount", 0))
        due     = date.fromisoformat(d.get("due_date", ""))
        service = d.get("service", "").strip()
    except Exception:
        return err("Invalid data. Provide service, total_amount (float), due_date (YYYY-MM-DD)")
    if not service or total <= 0:
        return err("service and positive total_amount required")
    debt = Debt(patient_id=pid, service=service, total_amount=total,
                due_date=due, notes=d.get("notes"), created_by=current_user.id)
    db.session.add(debt)
    db.session.commit()
    return ok(debt.to_dict(), "Debt created", 201)


@api_bp.route("/debts/<int:did>", methods=["DELETE"])
@login_required
def delete_debt(did):
    if not current_user.is_admin:
        return err("Admin required", 403)
    debt = Debt.query.get_or_404(did)
    db.session.delete(debt)
    db.session.commit()
    return ok(msg="Debt deleted")


# ─── PAYMENTS ─────────────────────────────────────────────────────────────────
@api_bp.route("/debts/<int:did>/payments", methods=["POST"])
@login_required
def create_payment(did):
    debt = Debt.query.get_or_404(did)
    d    = request.get_json() or {}
    try:
        amount = float(d.get("amount", 0))
        pdate  = date.fromisoformat(d.get("date", str(date.today())))
    except Exception:
        return err("Invalid amount or date")
    if amount <= 0:
        return err("Amount must be positive")
    if amount > debt.balance:
        return err(f"Amount exceeds balance of {debt.balance:.2f}")
    payment = Payment(debt_id=did, amount=amount,
                      method=d.get("method", "Cash"),
                      reference=d.get("reference"), note=d.get("note"),
                      date=pdate, recorded_by=current_user.id)
    db.session.add(payment)
    db.session.commit()
    return ok({**payment.to_dict(), "new_balance": debt.balance, "status": debt.status},
              "Payment recorded", 201)


@api_bp.route("/payments/<int:pid>", methods=["DELETE"])
@login_required
def delete_payment(pid):
    if not current_user.is_admin:
        return err("Admin required", 403)
    p = Payment.query.get_or_404(pid)
    db.session.delete(p)
    db.session.commit()
    return ok(msg="Payment deleted")


# ─── SUMMARY STATS ────────────────────────────────────────────────────────────
@api_bp.route("/stats", methods=["GET"])
@login_required
def stats():
    all_debts = Debt.query.all()
    return ok({
        "patients":      Patient.query.count(),
        "total_billed":  sum(d.total_amount for d in all_debts),
        "total_paid":    sum(d.total_paid   for d in all_debts),
        "total_balance": sum(d.balance      for d in all_debts),
        "overdue_count": sum(1 for d in all_debts if d.status == "overdue"),
        "paid_count":    sum(1 for d in all_debts if d.status == "paid"),
    })
