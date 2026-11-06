"""
CVForge AI - Email Service
Stub that logs instead of crashing if mail is not configured.

Adds: send_broadcast_email, send_claim_approved_email,
send_claim_rejected_email, send_plan_changed_email — all called from the
admin routes (broadcast, claim review, manual plan) so state changes
reach users both via in-app Notification AND email.
"""
import re
from urllib.parse import urlparse
from flask import current_app, url_for
from markupsafe import escape

BRAND_NAME = "CVForge AI"
BRAND_GREEN = "#0B8F5B"
BRAND_GREEN_SOFT = "#DDF4E8"
INK = "#0E1A2B"
MUTED = "#5B6B7F"
FONT = "Arial,Helvetica,sans-serif"


def nudge_price_note() -> str:
    """
    Price line under the upgrade button, built from the live plan table so it
    always matches what checkout charges (including any active offer).
    Falls back to a neutral line if the lookup fails.
    """
    try:
        from app.models import PricingPlan
        from app.services.pricing import annotate_plans
        cheapest = (PricingPlan.query
                    .filter(PricingPlan.is_active.is_(True), PricingPlan.price_kes > 0)
                    .order_by(PricingPlan.price_kes).first())
        if cheapest:
            annotate_plans([cheapest])
            return (f"From KES {cheapest.display_price} per {cheapest.billing_period}. "
                    f"Pay with M-Pesa. Each payment lasts {cheapest.period_days} days "
                    f"and does not renew automatically.")
    except Exception:
        pass
    return "Pay with M-Pesa or card. Each payment lasts for its plan period and does not renew automatically."


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


def send_verification_email(user, next_url=None):
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Verification email skipped for {user.email}")
        return

    try:
        verify_args = {"token": user.verification_token, "_external": True}
        if next_url and next_url.startswith("/") and not urlparse(next_url).netloc:
            verify_args["next"] = next_url
        verify_url = url_for("auth.verify_email", **verify_args)
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
        cta_note=nudge_price_note(),
        footer_note=(
            "You're receiving this because you're on the free plan and subscribed to "
            "updates. To stop these emails, turn off &ldquo;Newsletter&rdquo; in your account settings."
        ),
    )

    text = "\n\n".join([
        f"Hi {user.first_name or 'there'},",
        *content["paragraphs"],
        "What Pro adds:\n" + "\n".join(f"- {t}: {d}" for t, d in PRO_BENEFITS),
        f"See Pro plans: {billing_url}\n{nudge_price_note()}",
        "You're receiving this because you're on the free plan and subscribed to updates. "
        'To stop these emails, turn off "Newsletter" in your account settings.',
        f"{BRAND_NAME}. Built in Kenya.",
    ])
    return html, text


def send_manual_email(user):
    """One-off email pointing a user to the CVForge AI user manual.
    Returns True if it was handed to the mailer, False if mail is not
    configured (so the caller does not mark the user as emailed)."""
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Manual email skipped for {user.email}")
        return False

    guide_url = url_for("guide.index", _external=True)
    pdf_url = url_for("guide.download", _external=True)
    body = f"""
              <p style="margin:0 0 16px;">Hi {_first_name(user)},</p>
              <p style="margin:0 0 16px;">We have written a short user manual for {BRAND_NAME}. It shows you, step by step, how to build your CV, pick a template, check it against employers' screening software, and download it.</p>
              <p style="margin:0 0 16px;">Read it online, or save the PDF to your phone so you have it when you are applying for jobs.</p>
              <p style="margin:16px 0 0;font-size:14px;color:{MUTED};">Prefer the file? <a href="{pdf_url}" style="color:{BRAND_GREEN};">Download the PDF directly</a>.</p>"""
    html = _render_email(
        preheader="A short guide to building and downloading your CV.",
        body_html=body,
        cta_label="Open the user manual",
        cta_url=guide_url,
        footer_note="You are receiving this because you have a CVForge AI account.",
    )
    _send("Your CVForge AI user manual", user.email, html)
    return True


def send_pro_nudge_email(user):
    """
    Occasional reminder to free-tier users about what Pro unlocks.
    Called from nudge_service — never from a request, so cadence/opt-out
    is enforced by the caller, not here.
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


# ── Admin-triggered transactional emails ─────────────────────────

def _render_plain_body(user, body):
    """Turn a plain-text body (double-newline paragraphs) into HTML
    paragraphs, HTML-escaped. First-name greeting is prepended."""
    paragraphs = []
    for p in body.split("\n\n"):
        p = p.strip()
        if p:
            escaped = escape(p).replace("\n", "<br>")
            paragraphs.append(f'<p style="margin:0 0 16px;">{escaped}</p>')
    return f'<p style="margin:0 0 16px;">Hi {_first_name(user)},</p>' + "".join(paragraphs)


def send_broadcast_email(user, subject, body):
    """Plain-text announcement email. Returns True if handed to the
    mailer, False if mail isn't configured (so the admin broadcast
    route can report an accurate 'failed' count in dev)."""
    Mail, Message = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Broadcast '{subject}' skipped for {user.email}")
        return False

    html = _render_email(
        preheader=subject,
        body_html=_render_plain_body(user, body),
        footer_note="You're receiving this because you have a CVForge AI account.",
    )
    _send(subject, user.email, html)
    return True


def send_claim_approved_email(user, claim, admin_note=""):
    Mail, _ = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Claim approved email skipped for {user.email}")
        return

    amount_txt = ""
    if claim.subscription and claim.subscription.amount is not None:
        amount_txt = f" of KES {claim.subscription.amount}"

    note_html = f'<p style="margin:0 0 16px;color:{MUTED};">{escape(admin_note)}</p>' if admin_note else ""
    body = f"""
              <p style="margin:0 0 16px;">Hi {_first_name(user)},</p>
              <p style="margin:0 0 16px;">We verified your payment{amount_txt}
              (reference <strong>{escape(claim.reference or '')}</strong>) and your plan is now active.</p>
              {note_html}
              <p style="margin:16px 0 0;font-size:14px;color:{MUTED};">You can now download your CV and use all the features included in your plan.</p>"""
    html = _render_email(
        preheader="Your payment is confirmed and your plan is active.",
        body_html=body,
        cta_label="Go to my account",
        cta_url=url_for("billing.index", _external=True),
    )
    try:
        _send("Your CVForge AI plan is active", user.email, html)
    except Exception as e:
        current_app.logger.warning(f"Claim approved email send failed: {e}")


def send_claim_rejected_email(user, claim, admin_note=""):
    Mail, _ = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Claim rejected email skipped for {user.email}")
        return

    reason = admin_note or ("We couldn't verify a matching payment for this reference. "
                            "Please reply with your M-Pesa confirmation message so we can look again.")
    body = f"""
              <p style="margin:0 0 16px;">Hi {_first_name(user)},</p>
              <p style="margin:0 0 16px;">We looked into your payment claim for reference
              <strong>{escape(claim.reference or '')}</strong>, but we couldn't match it to a successful payment on our side.</p>
              <p style="margin:0 0 16px;">{escape(reason)}</p>
              <p style="margin:16px 0 0;font-size:14px;color:{MUTED};">If money left your account, reply to this email with the M-Pesa or bank message and we'll sort it out.</p>"""
    html = _render_email(
        preheader="We couldn't verify your payment claim yet.",
        body_html=body,
        cta_label="Open my billing page",
        cta_url=url_for("billing.index", _external=True),
    )
    try:
        _send("About your CVForge AI payment claim", user.email, html)
    except Exception as e:
        current_app.logger.warning(f"Claim rejected email send failed: {e}")


def send_plan_changed_email(user, plan_slug, days, admin_note=""):
    """Fired when an admin changes a user's plan manually."""
    Mail, _ = _get_mailer()
    if not Mail or not current_app.config.get("MAIL_USERNAME"):
        current_app.logger.info(f"[email stub] Plan-changed email skipped for {user.email}")
        return

    note_html = f'<p style="margin:0 0 16px;color:{MUTED};">{escape(admin_note)}</p>' if admin_note else ""
    body = f"""
              <p style="margin:0 0 16px;">Hi {_first_name(user)},</p>
              <p style="margin:0 0 16px;">An administrator has updated your plan to <strong>{escape(plan_slug)}</strong>
              for {days} day(s).</p>
              {note_html}
              <p style="margin:16px 0 0;font-size:14px;color:{MUTED};">You can review your plan and payment history in your billing page.</p>"""
    html = _render_email(
        preheader="Your CVForge AI plan has been updated.",
        body_html=body,
        cta_label="Open billing",
        cta_url=url_for("billing.index", _external=True),
    )
    try:
        _send("Your CVForge AI plan has been updated", user.email, html)
    except Exception as e:
        current_app.logger.warning(f"Plan-changed email send failed: {e}")
