from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User
from app.auth import auth_bp


# ─── LOGIN ────────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()
        if user and user.is_active and check_password_hash(user.password, password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.name}!", "success")
            return redirect(next_page or url_for("main.dashboard"))
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


# ─── REGISTER ─────────────────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if not current_user.is_admin:
        flash("Only admins can create new accounts.", "danger")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role     = request.form.get("role", "staff")

        errors = []
        if not name:              errors.append("Name is required.")
        if not email:             errors.append("Email is required.")
        if len(password) < 6:    errors.append("Password must be at least 6 characters.")
        if User.query.filter_by(email=email).first():
            errors.append("Email already registered.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            user = User(
                name     = name,
                email    = email,
                password = generate_password_hash(password),
                role     = role,
            )
            db.session.add(user)
            db.session.commit()
            flash(f"Account for {name} created successfully.", "success")
            return redirect(url_for("admin.users"))

    return render_template("auth/register.html")


# ─── LOGOUT ───────────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ─── PROFILE ──────────────────────────────────────────────────────────────────
@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name     = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        if name:
            current_user.name = name
        if password and len(password) >= 6:
            current_user.password = generate_password_hash(password)
            flash("Password updated.", "success")
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html")
