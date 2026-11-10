import os
from datetime import timedelta


class Config:
    # Core
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    # Database
    DATABASE_URL = os.environ.get("DATABASE_URL")
    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Visitor analytics uses a bounded in-process queue so page requests do
    # not wait for analytics database commits. Set false only for debugging.
    VISITOR_TRACKING_ASYNC = os.environ.get("VISITOR_TRACKING_ASYNC", "true").lower() == "true"
    VISITOR_TRACKING_QUEUE_SIZE = int(os.environ.get("VISITOR_TRACKING_QUEUE_SIZE", 2048))

    # Report-only first: configure a policy after checking real browser
    # dependencies; never enforce an untested CSP on payment/auth pages.
    CONTENT_SECURITY_POLICY_REPORT_ONLY = os.environ.get(
        "CONTENT_SECURITY_POLICY_REPORT_ONLY", ""
    ).strip()
    STATIC_ASSET_MAX_AGE = int(os.environ.get("STATIC_ASSET_MAX_AGE", 86400))

    # Session & cookies
    # PythonAnywhere runs behind a proxy — cookies must NOT require HTTPS
    # or the session will never persist between requests
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set to True ONLY if you have HTTPS (PA free tier does have HTTPS)
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"

    # CSRF
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False  # PA proxy can cause strict mode to reject valid tokens

    # PythonAnywhere sits behind a reverse proxy — trust its forwarded headers
    # so url_for() generates correct https:// URLs and CSRF origin checks pass
    PREFERRED_URL_SCHEME = "https"

    # Public site address used for canonical URLs, Open Graph URLs and the
    # sitemap (e.g. https://cvforgeai.com). Optional: when blank, the address
    # of the incoming request is used, which is the previous behaviour.
    SITE_URL = os.environ.get("SITE_URL", "").strip().rstrip("/")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "https://cvforge.pythonanywhere.com/auth/google/callback")

    # Gemini AI
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    # FIX: this default ("gemini-3.1-flash-lite") didn't match ai_service.py's
    # own hardcoded fallback ("gemini-1.5-flash"), so the two could silently
    # disagree depending on which one actually got used. Aligned to the same
    # value here — but verify against Google's current model list for your
    # google-generativeai SDK version before deploying; model names change.
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    GEMINI_DAILY_LIMIT = int(os.environ.get("GEMINI_DAILY_LIMIT", 1400))
    GEMINI_FREE_USER_DAILY_LIMIT = int(os.environ.get("GEMINI_FREE_USER_DAILY_LIMIT", 3))

    # Lipana M-Pesa
    LIPANA_API_KEY = os.environ.get("LIPANA_API_KEY", "")
    LIPANA_SECRET = os.environ.get("LIPANA_SECRET", "")
    LIPANA_WEBHOOK_SECRET = os.environ.get("LIPANA_WEBHOOK_SECRET", "")
    LIPANA_ENV = os.environ.get("LIPANA_ENV", "sandbox")

    # IntaSend — alternative to Lipana, doesn't require your own Daraja
    # production credentials. Get keys from the IntaSend dashboard.
    INTASEND_SECRET_KEY = os.environ.get("INTASEND_SECRET_KEY")
    INTASEND_PUBLISHABLE_KEY = os.environ.get("INTASEND_PUBLISHABLE_KEY")
    INTASEND_ENV = os.environ.get("INTASEND_ENV", "production")
    # The static "challenge" string you set in the IntaSend dashboard
    # webhook config — must match exactly, it's how their webhooks are
    # authenticated (not HMAC).
    INTASEND_WEBHOOK_CHALLENGE = os.environ.get("INTASEND_WEBHOOK_CHALLENGE", "")

    # Paystack hosted checkout (KES). Keep secret values in the deployment environment.
    PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")
    PAYSTACK_PUBLIC_KEY = os.environ.get("PAYSTACK_PUBLIC_KEY", "")
    PAYSTACK_WEBHOOK_SECRET = os.environ.get("PAYSTACK_WEBHOOK_SECRET", "")
    PAYSTACK_BASE_URL = os.environ.get("PAYSTACK_BASE_URL", "https://api.paystack.co")

    # Uploads — absolute path so PythonAnywhere can find it
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    )
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {"pdf", "docx"}

    # Email (optional)
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@cvforge.app")

