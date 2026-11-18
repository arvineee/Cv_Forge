from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from functools import wraps
from app import db
from app.models import User, Patient, Debt, Payment
from app.admin import admin_bp


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)
    return decorated


# ─── ADMIN PANEL ──────────────────────────────────────────────────────────────
@admin_bp.route("/")
@login_required
@admin_required
def panel():
    stats = {
        "users":    User.query.count(),
        "patients": Patient.query.count(),
        "debts":    Debt.query.count(),
        "payments": Payment.query.count(),
    }
    return render_template("admin/panel.html", stats=stats)


# ─── USER MANAGEMENT ──────────────────────────────────────────────────────────
@admin_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/user/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_user(uid):
    user = User.query.get_or_404(uid)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "danger")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        state = "activated" if user.is_active else "deactivated"
        flash(f"Account for {user.name} {state}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/user/<int:uid>/role", methods=["POST"])
@login_required
@admin_required
def change_role(uid):
    user = User.query.get_or_404(uid)
    role = request.form.get("role", "staff")
    if user.id == current_user.id:
        flash("You cannot change your own role.", "danger")
    else:
        user.role = role
        db.session.commit()
        flash(f"{user.name} role changed to {role}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/user/<int:uid>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(uid):
    user = User.query.get_or_404(uid)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User '{user.name}' deleted.", "warning")
    return redirect(url_for("admin.users"))


# ─── FULL DEBT LEDGER ─────────────────────────────────────────────────────────
@admin_bp.route("/ledger")
@login_required
@admin_required
def ledger():
    debts = Debt.query.order_by(Debt.due_date.asc()).all()
    return render_template("admin/ledger.html", debts=debts)


# ─── ALL PAYMENTS ─────────────────────────────────────────────────────────────
@admin_bp.route("/payments")
@login_required
@admin_required
def payments():
    page = request.args.get("page", 1, type=int)
    pag  = Payment.query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=30)
    return render_template("admin/payments.html", pag=pag)
