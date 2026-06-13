import os
from datetime import timedelta


class Config:
    # Core
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production-use-secrets-token-hex-32")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///cvforge.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

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
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "https")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5000/auth/google/callback")

    # Gemini AI
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    GEMINI_DAILY_LIMIT = int(os.environ.get("GEMINI_DAILY_LIMIT", 1400))
    GEMINI_FREE_USER_DAILY_LIMIT = int(os.environ.get("GEMINI_FREE_USER_DAILY_LIMIT", 3))

    # Lipana M-Pesa
    LIPANA_API_KEY = os.environ.get("LIPANA_API_KEY", "")
    LIPANA_SECRET = os.environ.get("LIPANA_SECRET", "")
    LIPANA_WEBHOOK_SECRET = os.environ.get("LIPANA_WEBHOOK_SECRET", "")
    LIPANA_ENV = os.environ.get("LIPANA_ENV", "sandbox")

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
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@cvforge.app")

