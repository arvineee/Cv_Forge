"""
CVForge AI - Feedback Blueprint

Public feedback form. Works logged in or out. Logged-in users are linked to
their account. Anonymous users may leave an optional email for a reply.

Spam controls: a honeypot field (bots fill it, humans don't see it) and a
per-IP limit based on ActivityLog, the same pattern as support.py.
"""
import re
from datetime import timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app.models import db, Feedback, ActivityLog, utcnow

feedback_bp = Blueprint("feedback", __name__)

CATEGORIES = [
    ("general", "General comment"),
    ("bug", "Something is broken"),
    ("feature", "Feature request"),
    ("pricing", "Pricing or offers"),
    ("cv", "CV or AI output quality"),
]
MIN_MESSAGE = 10
MAX_MESSAGE = 2000
IP_LIMIT_PER_HOUR = 5
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ip_rate_limited() -> bool:
    ip = request.remote_addr
    if not ip:
        return False
    cutoff = utcnow() - timedelta(hours=1)
    count = ActivityLog.query.filter(
        ActivityLog.action == "feedback_submit",
        ActivityLog.ip_address == ip,
        ActivityLog.created_at >= cutoff,
    ).count()
    return count >= IP_LIMIT_PER_HOUR


@feedback_bp.route("/feedback", methods=["GET", "POST"])
def index():

    if request.method == "POST":
        # Honeypot: real users never see or fill this field. If it has a value
        # it's a bot, so show a normal thank-you and store nothing.
        if request.form.get("website", "").strip():
            flash("Thank you! Your feedback has been sent.", "success")
            return redirect(url_for("feedback.index"))

        if _ip_rate_limited():
            flash("You've sent a lot of feedback in the last hour. Please try again later.", "error")
            return redirect(url_for("feedback.index"))

        category = request.form.get("category", "general")
        if category not in {c for c, _ in CATEGORIES}:
            category = "general"

        rating_raw = request.form.get("rating", "").strip()
        rating = int(rating_raw) if rating_raw.isdigit() and 1 <= int(rating_raw) <= 5 else None

        message = request.form.get("message", "").strip()
        if len(message) < MIN_MESSAGE:
            flash(f"Please write at least {MIN_MESSAGE} characters so we can act on it.", "error")
            return redirect(url_for("feedback.index"))
        if len(message) > MAX_MESSAGE:
            flash(f"Please keep feedback under {MAX_MESSAGE} characters.", "error")
            return redirect(url_for("feedback.index"))

        email = request.form.get("email", "").strip()[:255] or None
        if email and not EMAIL_RE.match(email):
            flash("That email address doesn't look right. Leave it blank or fix it.", "error")
            return redirect(url_for("feedback.index"))
        if current_user.is_authenticated and not email:
            email = current_user.email

        item = Feedback(
            user_id=current_user.id if current_user.is_authenticated else None,
            email=email,
            category=category,
            rating=rating,
            message=message,
            page=(request.form.get("page") or request.referrer or "")[:255] or None,
        )
        db.session.add(item)
        db.session.add(ActivityLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action="feedback_submit", resource_type="feedback",
            ip_address=request.remote_addr, details={"category": category},
        ))
        db.session.commit()
        flash("Thank you! Your feedback helps us make CVForge better.", "success")
        return redirect(url_for("feedback.index"))

    page = "feedback/dashboard.html" if current_user.is_authenticated else "feedback/public.html"
    return render_template(page, categories=CATEGORIES)
