"""
CVForge AI - Auth Blueprint
Fixed: rate limiting, safe next_page redirect, url_parse validation
"""
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, session, current_app, jsonify)
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse, urlencode
import secrets
import requests as http_requests
from datetime import datetime, timezone, timedelta

from app.models import db, User, Profile, ActivityLog, UserSettings

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _log_activity(user_id, action, details=None):
    log = ActivityLog(
        user_id=user_id, action=action,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:500] if request.user_agent else None,
        details=details,
    )
    db.session.add(log)


def _create_user_profile(user: User):
    if not user.profile:
        db.session.add(Profile(user_id=user.id))
    db.session.add(UserSettings(user_id=user.id))


def _safe_next(next_url):
    """Only allow relative URLs to prevent open redirect."""
    if next_url and urlparse(next_url).netloc == "" and next_url.startswith("/"):
        return next_url
    return None


# FIX: this file's docstring has claimed "rate limiting" for a while, but no
# such code actually existed anywhere in it — login/register/forgot-password
# were fully unthrottled. This is a minimal IP-based limiter built on the
# ActivityLog table that already exists, so it needs no new dependency
# (e.g. Flask-Limiter) and no extra infrastructure (e.g. Redis).
def _rate_limited(action: str, limit: int = 5, window_minutes: int = 15) -> bool:
    """Return True if this IP has hit `action` >= limit times in the window."""
    ip = request.remote_addr
    if not ip:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    count = ActivityLog.query.filter(
        ActivityLog.action == action,
        ActivityLog.ip_address == ip,
        ActivityLog.created_at >= cutoff,
    ).count()
    return count >= limit


def _record_attempt(action: str, user_id=None, details=None):
    db.session.add(ActivityLog(
        user_id=user_id, action=action,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string[:500] if request.user_agent else None,
        details=details,
    ))
    db.session.commit()


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        if _rate_limited("register_attempt", limit=5, window_minutes=15):
            flash("Too many signup attempts. Please try again in a few minutes.", "error")
            return render_template("auth/register.html")
        _record_attempt("register_attempt")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        errors = []
        if not email or "@" not in email:
            errors.append("Valid email is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html",
                                   email=email, first_name=first_name, last_name=last_name)

        token = secrets.token_urlsafe(32)
        user = User(email=email, first_name=first_name, last_name=last_name,
                    verification_token=token,
                    verification_token_expires=datetime.now(timezone.utc) + timedelta(hours=24),
                    is_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        _create_user_profile(user)
        _log_activity(user.id, "register", {"method": "email"})
        db.session.commit()

        try:
            from app.services.email_service import send_verification_email
            send_verification_email(user)
        except Exception as e:
            current_app.logger.warning(f"Verification email failed: {e}")

        flash("Account created! Please check your email to verify your account.", "success")
        login_user(user, remember=True)
        return redirect(url_for("dashboard.index"))

    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        if _rate_limited("login_failed", limit=10, window_minutes=15):
            flash("Too many failed login attempts. Please try again in a few minutes.", "error")
            return render_template("auth/login.html")

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(email=email).first()

        if not user:
            current_app.logger.warning(f"Login failed: no user found for email={email}")
            _record_attempt("login_failed")
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email)

        if not user.check_password(password):
            current_app.logger.warning(f"Login failed: wrong password for email={email}")
            _record_attempt("login_failed", user_id=user.id)
            flash("Invalid email or password.", "error")
            return render_template("auth/login.html", email=email)

        if not user.is_active:
            flash("Your account has been deactivated. Please contact support.", "error")
            return render_template("auth/login.html", email=email)

        user.last_login_at = datetime.now(timezone.utc)
        _log_activity(user.id, "login", {"method": "email"})
        db.session.commit()

        login_user(user, remember=remember)
        next_page = _safe_next(request.args.get("next"))
        return redirect(next_page or url_for("dashboard.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    _log_activity(current_user.id, "logout")
    db.session.commit()
    logout_user()
    flash("You've been logged out.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/verify/<token>")
def verify_email(token):
    user = User.query.filter_by(verification_token=token).first()
    if not user:
        flash("Invalid or expired verification link.", "error")
        return redirect(url_for("auth.login"))

    # FIX: the email says this link expires in 24 hours, but nothing ever
    # checked that before. Now it actually does.
    expires = user.verification_token_expires
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires < datetime.now(timezone.utc):
        flash("That verification link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.resend_verification") if current_user.is_authenticated
                         else url_for("auth.login"))

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.session.commit()
    flash("Email verified! Your account is now active.", "success")
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/resend-verification")
@login_required
def resend_verification():
    if current_user.is_verified:
        flash("Your email is already verified.", "info")
        return redirect(url_for("dashboard.index"))

    if _rate_limited("resend_verification", limit=3, window_minutes=15):
        flash("Too many requests. Please wait a few minutes before trying again.", "warning")
        return redirect(url_for("dashboard.index"))
    _record_attempt("resend_verification", user_id=current_user.id)

    current_user.verification_token = secrets.token_urlsafe(32)
    current_user.verification_token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    db.session.commit()
    try:
        from app.services.email_service import send_verification_email
        send_verification_email(current_user)
        flash("Verification email sent!", "success")
    except Exception:
        flash("Could not send email. Please try again later.", "error")
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        if _rate_limited("forgot_password_attempt", limit=5, window_minutes=15):
            flash("Too many requests. Please try again in a few minutes.", "error")
            return render_template("auth/forgot_password.html")
        _record_attempt("forgot_password_attempt")

        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=2)
            db.session.commit()
            try:
                from app.services.email_service import send_password_reset_email
                send_password_reset_email(user)
            except Exception as e:
                current_app.logger.warning(f"Reset email failed: {e}")
        flash("If an account exists with that email, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_expires:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("auth.forgot_password"))
    if user.reset_token_expires < datetime.now(timezone.utc):
        flash("Reset link has expired. Please request a new one.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("auth/reset_password.html", token=token)
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("auth/reset_password.html", token=token)
        user.set_password(password)
        user.reset_token = None
        user.reset_token_expires = None
        _log_activity(user.id, "password_reset")
        db.session.commit()
        flash("Password reset successfully. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


@auth_bp.route("/google")
def google_login():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_id": current_app.config["GOOGLE_CLIENT_ID"],
        "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
    }
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@auth_bp.route("/google/callback")
def google_callback():
    state = request.args.get("state")
    if state != session.pop("oauth_state", None):
        flash("Authentication failed. Please try again.", "error")
        return redirect(url_for("auth.login"))

    code = request.args.get("code")
    if not code:
        flash("Google authentication was cancelled.", "warning")
        return redirect(url_for("auth.login"))

    try:
        token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": current_app.config["GOOGLE_CLIENT_ID"],
                "client_secret": current_app.config["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
                "grant_type": "authorization_code",
            }, timeout=10)
        token_resp.raise_for_status()
        tokens = token_resp.json()
        userinfo_resp = http_requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=10)
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    except Exception as e:
        current_app.logger.error(f"Google OAuth error: {e}")
        flash("Google authentication failed. Please try again.", "error")
        return redirect(url_for("auth.login"))

    google_id = userinfo.get("sub")
    email = userinfo.get("email", "").lower()

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    if user:
        if not user.google_id:
            user.google_id = google_id
            user.oauth_provider = "google"
        user.avatar_url = userinfo.get("picture") or user.avatar_url
        user.is_verified = True
    else:
        user = User(
            email=email, google_id=google_id, oauth_provider="google",
            first_name=userinfo.get("given_name", ""),
            last_name=userinfo.get("family_name", ""),
            avatar_url=userinfo.get("picture", ""),
            is_verified=True,
        )
        db.session.add(user)
        db.session.flush()
        _create_user_profile(user)

    user.last_login_at = datetime.now(timezone.utc)
    _log_activity(user.id, "login", {"method": "google"})
    db.session.commit()
    login_user(user, remember=True)
    flash(f"Welcome, {user.first_name or user.email}!", "success")
    return redirect(url_for("dashboard.index"))


