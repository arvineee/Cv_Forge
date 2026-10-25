"""
CVForge AI - Email Service
Stub that logs instead of crashing if mail is not configured.
"""
import re
from flask import current_app, url_for
from markupsafe import escape

BRAND_NAME = "CVForge AI"
BRAND_GREEN = "#0B8F5B"
BRAND_GREEN_SOFT = "#DDF4E8"
INK = "#0E1A2B"
MUTED = "#5B6B7F"
FONT = "Arial,Helvetica,sans-serif"

# Shown under the upgrade button. Update when pricing or billing terms change.
NUDGE_PRICE_NOTE = (
    "From KES 50 a month. Pay with M-Pesa. Each subscription lasts 30 days "
    "and does not renew automatically."
)

# What Pro includes (matches AIService.SUPPORT_KNOWLEDGE).
PRO_BENEFITS = [
    ("Unlimited AI generations", "No daily cap when you rewrite, tailor or check a CV."),
    ("Every template unlocked", "Switch layouts for any industry without retyping."),
    ("Word (DOCX) downloads", "Export to Word and keep editing wherever you like."),
    ("Version history", "Go back to any earlier draft of a CV."),
    ("AI career coach", "Get direct feedback on your CV before you apply."),
]


def _get_mailer():
    try:
        from flask_mail import Mail, Message
        return Mail, Message
    except ImportError:
        return None, None


def _first_name(user):
    """HTML-safe first name for use in email greetings."""
    return escape(user.first_name or "there")


def _html_to_text(html):
    """Plain-text alternative for clients that don't render HTML.
    Keeps link targets so buttons don't disappear."""
    text = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", html, flags=re.S)
    text = re.sub(r"</(p|li|h1|h2|div|tr)>", "\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _render_email(preheader, body_html, cta_label=None, cta_url=None, footer_note=None,
                  hero_title=None, hero_text=None, cta_note=None):
    """Wrap body content in the shared CVForge email layout.

    Table-based with inline styles because many email clients ignore
    <style> blocks and modern CSS. hero_title/hero_text add an optional
    headline band under the logo (used by the marketing-style nudge).
    """
    hero = ""
    if hero_title:
        sub = (f'<p style="margin:10px 0 0;font-size:16px;line-height:1.5;color:{MUTED};">{hero_text}</p>'
               if hero_text else "")
        hero = f"""
          <tr>
            <td style="background:#EAF6F0;padding:32px 32px 28px;font-family:{FONT};">
              <h1 style="margin:0;font-size:28px;line-height:1.2;color:{INK};font-weight:700;">{hero_title}</h1>
              {sub}
            </td>
          </tr>"""

    button = ""
    if cta_label and cta_url:
        note = (f'<p style="margin:14px 0 0;font-size:13px;line-height:1.5;color:{MUTED};">{cta_note}</p>'
                if cta_note else "")
        button = f"""
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 0;">
                <tr>
                  <td style="background:{BRAND_GREEN};border-radius:8px;">
                    <a href="{cta_url}"
                       style="display:inline-block;padding:15px 30px;font-size:16px;font-weight:700;color:#ffffff;text-decoration:none;">
                      {cta_label}
                    </a>
                  </td>
                </tr>
              </table>
              {note}
              <p style="margin:14px 0 0;font-size:12px;color:{MUTED};line-height:1.5;">
                Button not working? Copy this link into your browser:<br>
                <a href="{cta_url}" style="color:{BRAND_GREEN};word-break:break-all;">{cta_url}</a>
              </p>"""

    note_html = ""
    if footer_note:
        note_html = f'<p style="margin:0 0 8px;">{footer_note}</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{BRAND_NAME}</title>
</head>
<body style="margin:0;padding:0;background:#EEF3F8;">
  <span style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</span>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#EEF3F8;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
               style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;">
          <tr>
            <td style="background:{INK};padding:20px 32px;">
              <span style="font-family:{FONT};font-size:20px;font-weight:700;color:#ffffff;">
                CV<span style="color:#4ADE9C;">Forge</span>
              </span>
            </td>
          </tr>{hero}
          <tr>
            <td style="padding:32px;font-family:{FONT};font-size:16px;line-height:1.6;color:{INK};">
              {body_html}
              {button}
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 28px;border-top:1px solid #E3EAF1;font-family:{FONT};font-size:12px;line-height:1.6;color:{MUTED};">
              {note_html}
              <p style="margin:0;">{BRAND_NAME}. Built in Kenya.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send(subject, recipient, html, text=None):
    from flask_mail import Mail, Message
    mail = Mail(current_app)
    msg = Message(
        subject=subject,
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        recipients=[recipient],
        body=text or _html_to_text(html),
        html=html,
    )
    mail.send(msg)


def send_verification_email(user):
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Verification email skipped for {user.email}")
        return

    try:
        verify_url = url_for("auth.verify_email", token=user.verification_token, _external=True)
        body = f"""
              <p style="margin:0 0 16px;">Hi {_first_name(user)},</p>
              <p style="margin:0 0 16px;">Welcome to {BRAND_NAME}. Please confirm your email address to finish setting up your account.</p>
              <p style="margin:16px 0 0;font-size:14px;color:{MUTED};">This link expires in 24 hours. If you didn't create an account, you can ignore this email.</p>"""
        html = _render_email(
            preheader="Confirm your email address to start building your CV.",
            body_html=body,
            cta_label="Verify my email",
            cta_url=verify_url,
        )
        _send("Verify your CVForge AI account", user.email, html)
    except Exception as e:
        current_app.logger.warning(f"Verification email failed: {e}")


def send_password_reset_email(user):
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Password reset email skipped for {user.email}")
        return

    try:
        reset_url = url_for("auth.reset_password", token=user.reset_token, _external=True)
        body = f"""
              <p style="margin:0 0 16px;">Hi {_first_name(user)},</p>
              <p style="margin:0 0 16px;">We received a request to reset the password on your {BRAND_NAME} account. Use the button below to choose a new one.</p>
              <p style="margin:16px 0 0;font-size:14px;color:{MUTED};">This link expires in 2 hours. If you didn't ask for a reset, no action is needed and your password will stay the same.</p>"""
        html = _render_email(
            preheader="Reset your CVForge AI password. This link expires in 2 hours.",
            body_html=body,
            cta_label="Reset my password",
            cta_url=reset_url,
        )
        _send("Reset your CVForge AI password", user.email, html)
    except Exception as e:
        current_app.logger.warning(f"Password reset email failed: {e}")


def _static_nudge_content(user=None):
    """Hand-written fallback copy, used whenever AI generation is
    unavailable or fails, so a Gemini hiccup never blocks the send.
    Same shape as AIService.generate_nudge_email(): plain-text paragraphs."""
    return {
        "subject": "Your CV, with no daily AI limits",
        "paragraphs": [
            "Your free plan covers the essentials, and many people never need more. "
            "If you are applying for several roles, though, the daily AI limit and a "
            "single download format can start to slow you down.",
            "Pro removes those limits, so you can tailor each application and keep "
            "every version of your CV in order.",
        ],
    }


def _build_nudge_email(user, content, billing_url):
    """Return (html, text) for the Pro nudge. content = {"subject", "paragraphs"}."""
    first = _first_name(user)
    paragraphs = "".join(
        f'<p style="margin:0 0 16px;">{escape(p)}</p>' for p in content["paragraphs"]
    )

    rows = "".join(
        f"""
                <tr>
                  <td width="34" valign="top" style="padding:7px 12px 7px 0;">
                    <div style="width:22px;height:22px;line-height:22px;border-radius:50%;background:{BRAND_GREEN_SOFT};color:{BRAND_GREEN};text-align:center;font-size:13px;font-weight:700;">&#10003;</div>
                  </td>
                  <td valign="top" style="padding:7px 0;font-family:{FONT};font-size:15px;line-height:1.45;color:{INK};">
                    <strong>{title}</strong><br>
                    <span style="color:{MUTED};">{desc}</span>
                  </td>
                </tr>"""
        for title, desc in PRO_BENEFITS
    )

    body = f"""
              <p style="margin:0 0 16px;">Hi {first},</p>
              {paragraphs}
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                     style="margin:24px 0 0;background:#F5F8FB;border-radius:10px;">
                <tr>
                  <td style="padding:20px 22px;">
                    <p style="margin:0 0 8px;font-family:{FONT};font-size:17px;font-weight:700;color:{INK};">What Pro adds</p>
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}
                    </table>
                  </td>
                </tr>
              </table>"""

    html = _render_email(
        preheader="Unlimited AI, every template and Word downloads. Pay with M-Pesa.",
        body_html=body,
        hero_title="Your CV, without the limits",
        hero_text="See what changes when you move from Free to Pro.",
        cta_label="See Pro plans",
        cta_url=billing_url,
        cta_note=NUDGE_PRICE_NOTE,
        footer_note=(
            "You're receiving this because you're on the free plan and subscribed to "
            "updates. To stop these emails, turn off &ldquo;Newsletter&rdquo; in your account settings."
        ),
    )

    text = "\n\n".join([
        f"Hi {user.first_name or 'there'},",
        *content["paragraphs"],
        "What Pro adds:\n" + "\n".join(f"- {t}: {d}" for t, d in PRO_BENEFITS),
        f"See Pro plans: {billing_url}\n{NUDGE_PRICE_NOTE}",
        "You're receiving this because you're on the free plan and subscribed to updates. "
        'To stop these emails, turn off "Newsletter" in your account settings.',
        f"{BRAND_NAME}. Built in Kenya.",
    ])
    return html, text


def send_pro_nudge_email(user):
    """
    Occasional reminder to free-tier users about what Pro unlocks.
    Called from cli.py's `flask send-nudges` command — never called
    directly from a request, so cadence/opt-out is enforced by the
    caller, not here.

    The personal paragraphs are written by Gemini (AIService.generate_nudge_email).
    If AI generation is unavailable, fails, or returns something unusable,
    this falls back to the static copy — the send is never blocked on the
    AI call succeeding. The log line says which copy was used, so you can
    tell from the logs whether the AI path is working.
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
        current_app.logger.warning(
            f"AI nudge generation failed ({type(e).__name__}: {e}), using static copy"
        )

    if content.get("subject") and content.get("paragraphs"):
        source = "AI"
    else:
        content = _static_nudge_content(user)
        source = "static"

    try:
        billing_url = url_for("billing.plans", _external=True)
        html, text = _build_nudge_email(user, content, billing_url)
        _send(content["subject"], user.email, html, text)
        current_app.logger.info(f"Pro nudge sent to user {user.id} using {source} copy")
    except Exception as e:
        current_app.logger.warning(f"Pro nudge email failed: {e}")
