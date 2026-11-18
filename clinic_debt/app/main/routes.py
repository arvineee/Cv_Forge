from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from datetime import date
from app import db
from app.models import Patient, Debt, Payment, PAYMENT_METHODS
from app.main import main_bp


# ─── DASHBOARD ────────────────────────────────────────────────────────────────
@main_bp.route("/")
@main_bp.route("/dashboard")
@login_required
def dashboard():
    all_debts    = Debt.query.all()
    total_owed   = sum(d.balance for d in all_debts)
    total_billed = sum(d.total_amount for d in all_debts)
    total_paid   = sum(d.total_paid for d in all_debts)
    overdue_list = [d for d in all_debts if d.status == "overdue"]
    cleared      = [d for d in all_debts if d.status == "paid"]

    recovery_rate = round((total_paid / total_billed * 100), 1) if total_billed else 0

    recent_payments = (Payment.query
                       .order_by(Payment.created_at.desc())
                       .limit(8).all())

    critical = (Debt.query
                .filter(Debt.due_date < date.today())
                .order_by(Debt.due_date.asc())
                .limit(5).all())

    stats = {
        "total_owed":     total_owed,
        "total_paid":     total_paid,
        "total_billed":   total_billed,
        "overdue_count":  len(overdue_list),
        "overdue_amount": sum(d.balance for d in overdue_list),
        "cleared_count":  len(cleared),
        "patient_count":  Patient.query.count(),
        "recovery_rate":  recovery_rate,
    }
    return render_template("main/dashboard.html", stats=stats,
                           recent_payments=recent_payments, critical=critical)


# ─── PATIENTS / DEBTORS ───────────────────────────────────────────────────────
@main_bp.route("/debtors")
@login_required
def debtors():
    q      = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    page   = request.args.get("page", 1, type=int)

    query = Patient.query
    if q:
        query = query.filter(
            or_(Patient.name.ilike(f"%{q}%"),
                Patient.phone.ilike(f"%{q}%"),
                Patient.email.ilike(f"%{q}%"),
                Patient.id_number.ilike(f"%{q}%"))
        )
    patients = query.order_by(Patient.name).all()

    # Filter by debt status (in Python since status is computed)
    if status != "all":
        patients = [p for p in patients if any(d.status == status for d in p.debts)]

    return render_template("main/debtors.html", patients=patients,
                           q=q, status=status)


# ─── PATIENT DETAIL ───────────────────────────────────────────────────────────
@main_bp.route("/patient/<int:pid>")
@login_required
def patient_detail(pid):
    patient = Patient.query.get_or_404(pid)
    return render_template("main/patient_detail.html", patient=patient,
                           PAYMENT_METHODS=PAYMENT_METHODS)


# ─── ADD PATIENT ──────────────────────────────────────────────────────────────
@main_bp.route("/patient/add", methods=["POST"])
@login_required
def add_patient():
    name      = request.form.get("name", "").strip()
    phone     = request.form.get("phone", "").strip()
    email     = request.form.get("email", "").strip()
    id_number = request.form.get("id_number", "").strip()
    gender    = request.form.get("gender", "")
    address   = request.form.get("address", "").strip()
    notes     = request.form.get("notes", "").strip()

    if not name or not phone:
        flash("Name and phone are required.", "danger")
        return redirect(url_for("main.debtors"))

    patient = Patient(name=name, phone=phone, email=email or None,
                      id_number=id_number or None, gender=gender,
                      address=address, notes=notes)
    db.session.add(patient)
    db.session.commit()
    flash(f"Patient '{name}' added successfully.", "success")
    return redirect(url_for("main.patient_detail", pid=patient.id))


# ─── EDIT PATIENT ─────────────────────────────────────────────────────────────
@main_bp.route("/patient/<int:pid>/edit", methods=["POST"])
@login_required
def edit_patient(pid):
    patient = Patient.query.get_or_404(pid)
    patient.name      = request.form.get("name", patient.name).strip()
    patient.phone     = request.form.get("phone", patient.phone).strip()
    patient.email     = request.form.get("email", "").strip() or None
    patient.id_number = request.form.get("id_number", "").strip() or None
    patient.gender    = request.form.get("gender", patient.gender)
    patient.address   = request.form.get("address", "").strip()
    patient.notes     = request.form.get("notes", "").strip()
    db.session.commit()
    flash("Patient record updated.", "success")
    return redirect(url_for("main.patient_detail", pid=pid))


# ─── DELETE PATIENT ───────────────────────────────────────────────────────────
@main_bp.route("/patient/<int:pid>/delete", methods=["POST"])
@login_required
def delete_patient(pid):
    if not current_user.is_admin:
        flash("Only admins can delete records.", "danger")
        return redirect(url_for("main.debtors"))
    patient = Patient.query.get_or_404(pid)
    name = patient.name
    db.session.delete(patient)
    db.session.commit()
    flash(f"Patient '{name}' and all debt records deleted.", "warning")
    return redirect(url_for("main.debtors"))


# ─── ADD DEBT ─────────────────────────────────────────────────────────────────
@main_bp.route("/patient/<int:pid>/debt/add", methods=["POST"])
@login_required
def add_debt(pid):
    patient = Patient.query.get_or_404(pid)
    try:
        total  = float(request.form.get("total_amount", 0))
        due    = date.fromisoformat(request.form.get("due_date"))
    except (ValueError, TypeError):
        flash("Invalid amount or due date.", "danger")
        return redirect(url_for("main.patient_detail", pid=pid))

    service = request.form.get("service", "").strip()
    if not service or total <= 0:
        flash("Service description and a valid amount are required.", "danger")
        return redirect(url_for("main.patient_detail", pid=pid))

    debt = Debt(patient_id=pid, service=service, total_amount=total,
                due_date=due, notes=request.form.get("notes", "").strip(),
                created_by=current_user.id)
    db.session.add(debt)
    db.session.commit()
    flash(f"Debt of KES {total:,.2f} recorded for {patient.name}.", "success")
    return redirect(url_for("main.patient_detail", pid=pid))


# ─── DELETE DEBT ──────────────────────────────────────────────────────────────
@main_bp.route("/debt/<int:did>/delete", methods=["POST"])
@login_required
def delete_debt(did):
    if not current_user.is_admin:
        flash("Only admins can delete debt records.", "danger")
        return redirect(url_for("main.debtors"))
    debt = Debt.query.get_or_404(did)
    pid  = debt.patient_id
    db.session.delete(debt)
    db.session.commit()
    flash("Debt record deleted.", "warning")
    return redirect(url_for("main.patient_detail", pid=pid))


# ─── ADD PAYMENT ──────────────────────────────────────────────────────────────
@main_bp.route("/debt/<int:did>/pay", methods=["POST"])
@login_required
def add_payment(did):
    debt = Debt.query.get_or_404(did)
    try:
        amount = float(request.form.get("amount", 0))
        pdate  = date.fromisoformat(request.form.get("date", str(date.today())))
    except (ValueError, TypeError):
        flash("Invalid payment amount or date.", "danger")
        return redirect(url_for("main.patient_detail", pid=debt.patient_id))

    if amount <= 0:
        flash("Payment amount must be greater than 0.", "danger")
        return redirect(url_for("main.patient_detail", pid=debt.patient_id))
    if amount > debt.balance:
        flash(f"Amount exceeds balance of KES {debt.balance:,.2f}.", "danger")
        return redirect(url_for("main.patient_detail", pid=debt.patient_id))

    payment = Payment(
        debt_id     = did,
        amount      = amount,
        method      = request.form.get("method", "Cash"),
        reference   = request.form.get("reference", "").strip(),
        note        = request.form.get("note", "").strip(),
        date        = pdate,
        recorded_by = current_user.id,
    )
    db.session.add(payment)
    db.session.commit()
    flash(f"Payment of KES {amount:,.2f} recorded via {payment.method}.", "success")

    # AJAX support
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "balance": debt.balance, "status": debt.status})

    return redirect(url_for("main.patient_detail", pid=debt.patient_id))


# ─── DELETE PAYMENT ───────────────────────────────────────────────────────────
@main_bp.route("/payment/<int:pid_>/delete", methods=["POST"])
@login_required
def delete_payment(pid_):
    if not current_user.is_admin:
        flash("Only admins can delete payments.", "danger")
        return redirect(url_for("main.dashboard"))
    payment = Payment.query.get_or_404(pid_)
    patient_id = payment.debt.patient_id
    db.session.delete(payment)
    db.session.commit()
    flash("Payment entry deleted.", "warning")
    return redirect(url_for("main.patient_detail", pid=patient_id))
