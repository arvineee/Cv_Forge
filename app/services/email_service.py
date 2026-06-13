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

