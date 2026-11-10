"""
CVForge AI - Database Models
Fixed: timezone-aware datetimes, clean AIUsage.log_usage classmethod,
PricingPlan model, removed monkey-patch, fixed relationship order_by,
Template gets accent_color field.

Adds: ManualPaymentClaim (webhook-missed payment verification) and
BroadcastEmail (audit log of admin announcements).
"""
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib

db = SQLAlchemy()


def utcnow():
    """Naive UTC — SQLite strips tzinfo; keeping naive avoids comparison errors."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_aware(dt):
    """Attach UTC tzinfo to a naive datetime from the DB before comparing."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True)

    google_id = db.Column(db.String(255), unique=True, nullable=True, index=True)
    oauth_provider = db.Column(db.String(50), nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_token = db.Column(db.String(255), nullable=True)
    # FIX: the verification email says "expires in 24 hours" but nothing
    # ever enforced that — verify_email() never checked an expiry. This
    # column + the check in auth.verify_email() make that claim true.
    verification_token_expires = db.Column(db.DateTime(timezone=True), nullable=True)
    reset_token = db.Column(db.String(255), nullable=True)
    reset_token_expires = db.Column(db.DateTime(timezone=True), nullable=True)

    plan = db.Column(db.String(20), default="free", nullable=False)
    plan_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    profile = db.relationship("Profile", backref="user", uselist=False, lazy="joined", cascade="all, delete-orphan")
    settings = db.relationship("UserSettings", backref="user", uselist=False, lazy="joined", cascade="all, delete-orphan")
    resumes = db.relationship("Resume", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    cover_letters = db.relationship("CoverLetter", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    subscriptions = db.relationship("Subscription", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    ai_usages = db.relationship("AIUsage", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    activity_logs = db.relationship("ActivityLog", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    notifications = db.relationship("Notification", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_premium(self) -> bool:
        if self.plan in ("pro", "premium") and self.plan_expires_at:
            return _make_aware(self.plan_expires_at) > datetime.now(timezone.utc)
        return False

    @property
    def has_paid_plan(self) -> bool:
        """Any active paid tier (basic, pro or premium), unexpired.

        Matches the download gate in routes/cv.py. Use this for upsell prompts.
        is_premium stays as-is because it gates Pro-only features.
        """
        # Any non-free slug counts, so plans an admin creates later (e.g. a weekly
        # pass) are treated as paid instead of silently failing the download gate.
        if not self.plan or self.plan == "free":
            return False
        if not self.plan_expires_at:
            return False
        return _make_aware(self.plan_expires_at) > datetime.now(timezone.utc)

    @property
    def full_name(self) -> str:
        parts = filter(None, [self.first_name, self.last_name])
        return " ".join(parts) or self.email.split("@")[0]

    @property
    def display_name(self) -> str:
        return self.full_name

    def get_active_subscription(self):
        return (
            self.subscriptions
            .filter_by(status="active")
            .order_by(Subscription.end_date.desc())
            .first()
        )

    def __repr__(self):
        return f"<User {self.email}>"


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    phone = db.Column(db.String(30), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    linkedin_url = db.Column(db.String(500), nullable=True)
    portfolio_url = db.Column(db.String(500), nullable=True)
    github_url = db.Column(db.String(500), nullable=True)
    job_title = db.Column(db.String(150), nullable=True)
    years_experience = db.Column(db.Integer, nullable=True)
    preferred_language = db.Column(db.String(10), default="en")
    dark_mode = db.Column(db.Boolean, default=False)
    email_notifications = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<Profile user_id={self.user_id}>"


# ── Admin-editable pricing plans ────────────────────────────────

class PricingPlan(db.Model):
    __tablename__ = "pricing_plans"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    price_kes = db.Column(db.Integer, nullable=False, default=0)
    billing_period = db.Column(db.String(20), default="month")
    is_active = db.Column(db.Boolean, default=True)
    is_popular = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    features = db.Column(db.JSON, nullable=True)
    daily_cv_limit = db.Column(db.Integer, default=3)
    daily_cover_letter_limit = db.Column(db.Integer, default=3)
    daily_ats_limit = db.Column(db.Integer, default=5)
    allow_docx = db.Column(db.Boolean, default=False)
    allow_version_history = db.Column(db.Boolean, default=False)
    allow_career_coach = db.Column(db.Boolean, default=False)
    allow_public_link = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def __repr__(self):
        return f"<PricingPlan {self.slug} KES {self.price_kes}>"


class Resume(db.Model):
    __tablename__ = "resumes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    template_id = db.Column(db.Integer, db.ForeignKey("templates.id"), nullable=True)
    title = db.Column(db.String(255), nullable=False, default="Untitled Resume")
    slug = db.Column(db.String(255), nullable=True, index=True)
    status = db.Column(db.String(20), default="draft")
    ats_score = db.Column(db.Integer, nullable=True)
    ats_report = db.Column(db.JSON, nullable=True)
    personal_info = db.Column(db.JSON, nullable=True)
    professional_summary = db.Column(db.Text, nullable=True)
    work_experience = db.Column(db.JSON, nullable=True)
    education = db.Column(db.JSON, nullable=True)
    skills = db.Column(db.JSON, nullable=True)
    certifications = db.Column(db.JSON, nullable=True)
    projects = db.Column(db.JSON, nullable=True)
    references = db.Column(db.JSON, nullable=True)
    languages = db.Column(db.JSON, nullable=True)
    awards = db.Column(db.JSON, nullable=True)
    custom_sections = db.Column(db.JSON, nullable=True)
    source = db.Column(db.String(30), default="builder")
    original_filename = db.Column(db.String(255), nullable=True)
    original_file_path = db.Column(db.String(500), nullable=True)
    is_public = db.Column(db.Boolean, default=False)
    public_token = db.Column(db.String(64), unique=True, nullable=True)
    download_count = db.Column(db.Integer, default=0)
    last_downloaded_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # No order_by in relationship — add .order_by() in each query
    versions = db.relationship("ResumeVersion", backref="resume", lazy="dynamic", cascade="all, delete-orphan")
    job_matches = db.relationship("JobMatch", backref="resume", lazy="dynamic", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "ats_score": self.ats_score,
            "personal_info": self.personal_info,
            "professional_summary": self.professional_summary,
            "work_experience": self.work_experience,
            "education": self.education,
            "skills": self.skills,
            "certifications": self.certifications,
            "projects": self.projects,
            "references": self.references,
            "languages": self.languages,
            "awards": self.awards,
            "custom_sections": self.custom_sections,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Resume {self.title} user={self.user_id}>"


class ResumeVersion(db.Model):
    __tablename__ = "resume_versions"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False, default=1)
    label = db.Column(db.String(100), nullable=True)
    snapshot = db.Column(db.JSON, nullable=False)
    ats_score = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    created_by = db.Column(db.String(50), default="user")

    def __repr__(self):
        return f"<ResumeVersion resume={self.resume_id} v{self.version_number}>"


class CoverLetter(db.Model):
    __tablename__ = "cover_letters"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=True)
    title = db.Column(db.String(255), nullable=False, default="Untitled Cover Letter")
    job_title = db.Column(db.String(255), nullable=True)
    company_name = db.Column(db.String(255), nullable=True)
    job_description = db.Column(db.Text, nullable=True)
    tone = db.Column(db.String(30), default="professional")
    content = db.Column(db.Text, nullable=False)
    download_count = db.Column(db.Integer, default=0)
    is_archived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self):
        return f"<CoverLetter {self.title}>"


class Template(db.Model):
    __tablename__ = "templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), nullable=False)
    thumbnail_url = db.Column(db.String(500), nullable=True)
    preview_url = db.Column(db.String(500), nullable=True)
    is_premium = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    use_count = db.Column(db.Integer, default=0)
    accent_color = db.Column(db.String(7), default="#2563eb")
    font_style = db.Column(db.String(30), default="modern")
    config = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    resumes = db.relationship("Resume", backref="template", lazy="dynamic")

    def __repr__(self):
        return f"<Template {self.name}>"


class Subscription(db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), default="KES")
    status = db.Column(db.String(20), default="pending")
    payment_reference = db.Column(db.String(255), nullable=True, index=True)
    lipana_transaction_id = db.Column(db.String(255), nullable=True)
    start_date = db.Column(db.DateTime(timezone=True), nullable=True)
    end_date = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    payments = db.relationship("Payment", backref="subscription", lazy="dynamic")

    def activate(self, transaction_id: str = None, days: int = 30):
        self.status = "active"
        self.start_date = utcnow()
        self.end_date = self.start_date + timedelta(days=days)
        if transaction_id:
            self.lipana_transaction_id = transaction_id

    def __repr__(self):
        return f"<Subscription user={self.user_id} plan={self.plan} status={self.status}>"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True)
    amount = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(10), default="KES")
    status = db.Column(db.String(20), default="pending")
    payment_method = db.Column(db.String(30), nullable=True)
    lipana_transaction_id = db.Column(db.String(255), unique=True, nullable=True, index=True)
    lipana_checkout_request_id = db.Column(db.String(255), nullable=True)
    lipana_payment_link_id = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    raw_webhook = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self):
        return f"<Payment {self.lipana_transaction_id} {self.status}>"


class AIUsage(db.Model):
    __tablename__ = "ai_usage"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    feature = db.Column(db.String(50), nullable=False)
    prompt_hash = db.Column(db.String(64), nullable=True, index=True)
    cached_response = db.Column(db.Text, nullable=True)
    tokens_used = db.Column(db.Integer, nullable=True)
    requests_used = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    @classmethod
    def log_usage(cls, user_id: int, feature: str, prompt: str = ""):
        """Add a usage record. Caller must commit the session."""
        db.session.add(cls(
            user_id=user_id,
            feature=feature,
            prompt_hash=cls.hash_prompt(prompt),
            requests_used=1,
        ))

    @classmethod
    def get_daily_count(cls, user_id: int, feature: str = None) -> int:
        # Use naive UTC to match what SQLite actually stores
        today_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
        q = cls.query.filter(cls.user_id == user_id, cls.created_at >= today_start)
        if feature:
            q = q.filter_by(feature=feature)
        return q.count()

    @classmethod
    def get_total_daily_count(cls) -> int:
        today_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(hour=0, minute=0, second=0, microsecond=0)
        return cls.query.filter(cls.created_at >= today_start).count()

    @classmethod
    def find_cached(cls, prompt_hash: str, feature: str):
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
        return cls.query.filter(
            cls.prompt_hash == prompt_hash,
            cls.feature == feature,
            cls.cached_response.isnot(None),
            cls.created_at >= cutoff,
        ).first()

    def __repr__(self):
        return f"<AIUsage user={self.user_id} feature={self.feature}>"


class JobMatch(db.Model):
    __tablename__ = "job_matches"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=True)
    job_title = db.Column(db.String(255), nullable=True)
    company_name = db.Column(db.String(255), nullable=True)
    job_description = db.Column(db.Text, nullable=False)
    match_score = db.Column(db.Integer, nullable=True)
    ats_score = db.Column(db.Integer, nullable=True)
    missing_keywords = db.Column(db.JSON, nullable=True)
    matched_keywords = db.Column(db.JSON, nullable=True)
    skills_gap = db.Column(db.JSON, nullable=True)
    suggestions = db.Column(db.JSON, nullable=True)
    full_report = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<JobMatch score={self.match_score}>"


class ATSReport(db.Model):
    __tablename__ = "ats_reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.id"), nullable=True)
    score = db.Column(db.Integer, nullable=False)
    grade = db.Column(db.String(5), nullable=True)
    issues = db.Column(db.JSON, nullable=True)
    strengths = db.Column(db.JSON, nullable=True)
    suggestions = db.Column(db.JSON, nullable=True)
    keyword_analysis = db.Column(db.JSON, nullable=True)
    format_analysis = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def __repr__(self):
        return f"<ATSReport score={self.score}>"


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<ActivityLog {self.action} user={self.user_id}>"


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(30), default="info")
    is_read = db.Column(db.Boolean, default=False)
    action_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Notification {self.title} user={self.user_id}>"


class UserSettings(db.Model):
    __tablename__ = "user_settings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    email_on_payment = db.Column(db.Boolean, default=True)
    email_on_expiry = db.Column(db.Boolean, default=True)
    email_newsletter = db.Column(db.Boolean, default=True)
    public_profile = db.Column(db.Boolean, default=False)
    allow_analytics = db.Column(db.Boolean, default=True)
    theme = db.Column(db.String(20), default="light")
    default_template_id = db.Column(db.Integer, nullable=True)
    # Pro-upgrade nudge cadence — reuses email_newsletter as the opt-out
    # flag (a dedicated "marketing emails" toggle would be more precise,
    # but this already exists and is the closest fit rather than adding
    # a redundant field).
    last_nudge_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)
    # FIX: default=0 is Python/ORM-side only — Alembic autogenerate had no
    # server-level default to backfill existing rows with when this column
    # was added, so `flask db upgrade` failed on SQLite with "Cannot add a
    # NOT NULL column with default value NULL". server_default gives it an
    # actual DB-level default so both fresh installs and future ALTER
    # TABLEs against existing rows work.
    nudge_count = db.Column(db.Integer, default=0, server_default="0", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PageVisit(db.Model):
    """
    Lightweight visit log for the admin visitor-tracking view.
    Deliberately minimal — not a full analytics engine. IP is stored
    truncated (last octet zeroed for IPv4) rather than in full, as a
    reasonable middle ground between "admin can see traffic patterns"
    and "don't retain precise personal location data indefinitely" —
    worth reviewing against Kenya's Data Protection Act 2019 obligations
    for your actual use case before relying on this as sufficient
    compliance on its own.
    """
    __tablename__ = "page_visits"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    path = db.Column(db.String(255), nullable=False, index=True, default='/')
    method = db.Column(db.String(10), nullable=False, default="GET")
    ip_truncated = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    referrer = db.Column(db.String(500), nullable=True)
    session_id = db.Column(db.String(64), nullable=True, index=True)  # for unique-visitor counting
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<PageVisit {self.path} user={self.user_id}>"


# ── Offers (time-limited discounts overlaid on plan prices) ───────
# Offers never mutate PricingPlan.price_kes. The effective price is
# computed at read/checkout time (see app/services/pricing.py), so when
# an offer expires, sells out, or is voided, the base price returns
# automatically with nothing to undo.

EAT = timezone(timedelta(hours=3))  # Africa/Nairobi, no DST


class Offer(db.Model):
    __tablename__ = "offers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)            # internal label
    public_label = db.Column(db.String(120), nullable=False)    # shown to customers
    discount_type = db.Column(db.String(10), nullable=False, default="percent")  # percent | fixed
    discount_value = db.Column(db.Integer, nullable=False)
    # NULL = applies to every paid plan; otherwise a list of plan slugs.
    plan_slugs = db.Column(db.JSON, nullable=True)
    starts_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ends_at = db.Column(db.DateTime(timezone=True), nullable=True)
    max_redemptions = db.Column(db.Integer, nullable=True)
    # Manual kill switch. False = voided, regardless of dates.
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    redemptions = db.relationship("OfferRedemption", backref="offer", lazy="dynamic",
                                  cascade="all, delete-orphan")

    def applies_to(self, plan_slug: str) -> bool:
        return not self.plan_slugs or plan_slug in self.plan_slugs

    @property
    def starts_at_aware(self):
        return _make_aware(self.starts_at)

    @property
    def ends_at_aware(self):
        return _make_aware(self.ends_at)

    @staticmethod
    def _fmt_local(dt, fmt):
        return _make_aware(dt).astimezone(EAT).strftime(fmt) if dt else ""

    @property
    def ends_at_label(self) -> str:
        return self._fmt_local(self.ends_at, "%d %b %Y, %H:%M EAT")

    @property
    def starts_at_input(self) -> str:
        return self._fmt_local(self.starts_at, "%Y-%m-%dT%H:%M")

    @property
    def ends_at_input(self) -> str:
        return self._fmt_local(self.ends_at, "%Y-%m-%dT%H:%M")

    def __repr__(self):
        return f"<Offer {self.name} {self.discount_type}={self.discount_value}>"


class OfferRedemption(db.Model):
    """
    One row per checkout that used an offer. Status moves:
      pending   -> created at checkout, holds a seat in max_redemptions
      redeemed  -> payment confirmed by webhook
      released  -> payment failed, seat returned
    """
    __tablename__ = "offer_redemptions"

    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offers.id"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    base_amount = db.Column(db.Integer, nullable=False)
    charged_amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<OfferRedemption offer={self.offer_id} {self.status}>"


# ── Feedback ──────────────────────────────────────────────────────

class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(20), nullable=False, default="general")
    rating = db.Column(db.Integer, nullable=True)            # 1-5, optional
    message = db.Column(db.Text, nullable=False)
    page = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="new")  # new | reviewed | resolved
    admin_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = db.relationship("User", backref=db.backref("feedback_items", lazy="dynamic"))

    def __repr__(self):
        return f"<Feedback {self.category} {self.status}>"


# ── Manual payment claims ────────────────────────────────────────
# When a webhook is missed (network, provider retry exhausted, or a
# real payment that never reached us), the user pastes their M-Pesa
# confirmation message here and an admin verifies it manually.
# Approving a claim reuses the exact same _handle_payment_success()
# path as a real webhook, so subscription/plan/payment/offer rows stay
# consistent regardless of how the payment was verified.

class ManualPaymentClaim(db.Model):
    __tablename__ = "manual_payment_claims"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True)
    reference = db.Column(db.String(255), nullable=True, index=True)
    pasted_message = db.Column(db.Text, nullable=False)
    contact_phone = db.Column(db.String(30), nullable=True)

    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | approved | rejected
    admin_note = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)

    user = db.relationship("User", foreign_keys=[user_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])
    subscription = db.relationship("Subscription")

    def __repr__(self):
        return f"<ManualPaymentClaim user={self.user_id} {self.status}>"


# ── Admin broadcast emails ────────────────────────────────────────
# Kept as a small log so admins can see what they sent, to whom, and
# how many succeeded. Body is stored as plain text; the email template
# escapes it. Not meant to be a full campaign system.

class BroadcastEmail(db.Model):
    __tablename__ = "broadcast_emails"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    audience = db.Column(db.String(20), nullable=False, default="all")
    recipient_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    sent_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    sender = db.relationship("User", foreign_keys=[sent_by])

    def __repr__(self):
        return f"<BroadcastEmail '{self.subject}' to {self.recipient_count}>"
