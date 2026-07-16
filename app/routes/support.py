"""
CVForge AI - Support Blueprint

AI-powered support page using Gemini via ai_service.support_answer(),
grounded in a static knowledge block so it doesn't invent pricing or
features (see AIService.SUPPORT_KNOWLEDGE).

Rate limiting matters more here than on the other AI features: this page
doesn't require login (support should be reachable by someone who can't
get into their account), which means it's the one AI endpoint reachable
by a completely anonymous visitor — an easy target for someone to script
and burn through your Gemini quota. Limited by IP using the same
ActivityLog-based limiter pattern as auth.py, tighter than the per-user
limits elsewhere.
"""
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import current_user
from app.models import db, ActivityLog, AIUsage
from app.ai_service import get_ai_service

support_bp = Blueprint("support", __name__)

MAX_QUESTION_LENGTH = 500
IP_LIMIT_PER_WINDOW = 8
IP_WINDOW_MINUTES = 15


def _ip_rate_limited() -> bool:
    ip = request.remote_addr
    if not ip:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=IP_WINDOW_MINUTES)
    count = ActivityLog.query.filter(
        ActivityLog.action == "support_question",
        ActivityLog.ip_address == ip,
        ActivityLog.created_at >= cutoff,
    ).count()
    return count >= IP_LIMIT_PER_WINDOW


@support_bp.route("/support")
def index():
    return render_template("support/index.html")


@support_bp.route("/support/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Please enter a question."}), 400
    if len(question) > MAX_QUESTION_LENGTH:
        return jsonify({"error": f"Question is too long (max {MAX_QUESTION_LENGTH} characters)."}), 400

    if _ip_rate_limited():
        return jsonify({"error": "Too many questions right now. Please wait a few minutes, or use the contact form below for a human."}), 429

    # Logged-in users also get their own per-user AI limit check, same as
    # the other AI features, so support chat can't be used to bypass
    # daily limits on a free account either.
    user_id = None
    if current_user.is_authenticated:
        user_id = current_user.id
        if not current_user.is_premium:
            daily = AIUsage.get_daily_count(current_user.id, "support_chat")
            limit = current_app.config.get("GEMINI_FREE_USER_DAILY_LIMIT", 3)
            if daily >= limit:
                return jsonify({"error": f"Daily support-chat limit reached ({limit}/day). Upgrade to Pro for unlimited access, or use the contact form below."}), 429

    try:
        ai = get_ai_service()
        answer = ai.support_answer(question=question, user=current_user if current_user.is_authenticated else None,
                                    user_id=user_id)
    except Exception as e:
        current_app.logger.error(f"Support AI error: {e}")
        return jsonify({"error": "Support assistant is temporarily unavailable. Please use the contact form below."}), 503

    db.session.add(ActivityLog(
        user_id=user_id, action="support_question",
        ip_address=request.remote_addr,
        details={"question": question[:200]},
    ))
    if user_id:
        AIUsage.log_usage(user_id, "support_chat", question[:200])
    db.session.commit()

    return jsonify({"answer": answer})

