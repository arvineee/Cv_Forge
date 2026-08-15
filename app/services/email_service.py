"""
CVForge AI - Email Service
Stub that logs instead of crashing if mail is not configured.
"""
from flask import current_app, url_for


def _get_mailer():
    try:
        from flask_mail import Mail, Message
        return Mail, Message
    except ImportError:
        return None, None


def send_verification_email(user):
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Verification email skipped for {user.email}")
        return

    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        token = user.verification_token
        verify_url = url_for("auth.verify_email", token=token, _external=True)
        msg = Message(
            subject="Verify your CVForge AI account",
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
            recipients=[user.email],
            html=f"""
            <p>Hi {user.first_name or 'there'},</p>
            <p>Click the link below to verify your email address:</p>
            <p><a href="{verify_url}">{verify_url}</a></p>
            <p>This link expires in 24 hours.</p>
            <p>— CVForge AI</p>
            """,
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.warning(f"Verification email failed: {e}")


def send_password_reset_email(user):
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Password reset email skipped for {user.email}")
        return

    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        reset_url = url_for("auth.reset_password", token=user.reset_token, _external=True)
        msg = Message(
            subject="Reset your CVForge AI password",
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
            recipients=[user.email],
            html=f"""
            <p>Hi {user.first_name or 'there'},</p>
            <p>Click the link below to reset your password (expires in 2 hours):</p>
            <p><a href="{reset_url}">{reset_url}</a></p>
            <p>If you didn't request this, ignore this email.</p>
            <p>— CVForge AI</p>
            """,
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.warning(f"Password reset email failed: {e}")


def _static_nudge_content(user):
    """The original hand-written copy — used whenever AI generation is
    unavailable or fails, so a Gemini hiccup never blocks the send."""
    return {
        "subject": "Get more out of CVForge AI",
        "body_html": """
            <p>Just a quick note — Pro removes your daily AI generation limits,
            unlocks every template, adds Word (DOCX) downloads, keeps your
            version history, and gives you the AI career coach.</p>
            <p>No pressure — the free plan still works great. This is just here
            in case it's useful.</p>
            """,
    }


def send_pro_nudge_email(user):
    """
    Occasional reminder to free-tier users about what Pro unlocks.
    Called from cli.py's `flask send-nudges` command — never called
    directly from a request, so cadence/opt-out is enforced by the
    caller, not here.

    Copy is generated per-user by Gemini (see AIService.generate_nudge_email)
    so the message can reference the user's own resume/ATS activity. If AI
    generation is unavailable, fails, or returns something unusable, this
    falls back to the original static template — the send is never blocked
    on the AI call succeeding.
    """
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Pro nudge email skipped for {user.email}")
        return

    content = {}
    try:
        from app.services.ai_service import get_ai_service
        content = get_ai_service().generate_nudge_email(user, user_id=user.id) or {}
    except Exception as e:
        current_app.logger.warning(f"AI nudge generation failed, using static template: {e}")

    if not content.get("subject") or not content.get("body_html"):
        content = _static_nudge_content(user)

    try:
        from flask_mail import Mail, Message
        mail = Mail(current_app)
        billing_url = url_for("billing.plans", _external=True)
        msg = Message(
            subject=content["subject"],
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
            recipients=[user.email],
            html=f"""
            <p>Hi {user.first_name or 'there'},</p>
            {content["body_html"]}
            <p><a href="{billing_url}">See plans and pricing</a></p>
            <p>— CVForge AI</p>
            <p style="font-size:12px;color:#888;">
            Don't want these emails? Turn off "Newsletter" in your account settings.
            </p>
            """,
        )
        mail.send(msg)
    except Exception as e:
        current_app.logger.warning(f"Pro nudge email failed: {e}")



