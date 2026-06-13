"""
CVForge AI - Application Factory
Includes Flask-WTF CSRF protection, Flask-Limiter rate limiting,
errorhandler for 403/404/500, and CLI commands for admin management.
"""
import click
from flask import Flask, render_template, abort
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate

from app.models import db, User, Profile, UserSettings, PricingPlan, Template

login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()


def create_app(config_object=None):
    app = Flask(__name__)

    # ── Config ────────────────────────────────────────────────────
    if config_object:
        app.config.from_object(config_object)
    else:
        from config import Config
        app.config.from_object(Config)

    # ── Extensions ────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "error"

    # ── Blueprints ────────────────────────────────────────────────
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.cv import cv_bp
    from app.routes.cover_letter import cover_letter_bp
    from app.routes.ats import ats_bp
    from app.routes.billing import billing_bp
    from app.routes.admin import admin_bp
    from app.routes.webhooks import webhooks_bp
    from app.routes.templates_gallery import templates_gallery_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(cv_bp, url_prefix="/cv")
    app.register_blueprint(cover_letter_bp, url_prefix="/cover-letter")
    app.register_blueprint(ats_bp, url_prefix="/ats")
    app.register_blueprint(billing_bp, url_prefix="/billing")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")
    app.register_blueprint(templates_gallery_bp, url_prefix="/templates")
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    # ── Error handlers ────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f"500 error: {e}")
        return render_template("errors/500.html"), 500

    # ── CLI commands ──────────────────────────────────────────────
    _register_cli(app)

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─────────────────────────────────────────────────────────────────
# CLI COMMANDS
# ─────────────────────────────────────────────────────────────────

def _register_cli(app: Flask):

    @app.cli.command("create-user")
    @click.option("--email", prompt="Email address", help="User email")
    @click.option("--password", prompt=True, hide_input=True,
                  confirmation_prompt=True, help="Password")
    @click.option("--first-name", default="", prompt="First name (optional, press Enter to skip)")
    @click.option("--last-name", default="", prompt="Last name (optional, press Enter to skip)")
    @click.option("--admin", is_flag=True, default=False, help="Grant admin privileges")
    @click.option("--plan", default="free", type=click.Choice(["free", "pro", "premium"]),
                  help="Subscription plan")
    @click.option("--verify", is_flag=True, default=True, help="Mark email as verified")
    def create_user(email, password, first_name, last_name, admin, plan, verify):
        """Create a new user account from the CLI."""
        if User.query.filter_by(email=email.lower().strip()).first():
            click.secho(f"✗ User with email '{email}' already exists.", fg="red")
            return

        user = User(
            email=email.lower().strip(),
            first_name=first_name.strip() or None,
            last_name=last_name.strip() or None,
            is_admin=admin,
            is_verified=verify,
            plan=plan,
        )
        user.set_password(password)

        if plan != "free":
            from datetime import datetime, timezone, timedelta
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        db.session.add(user)
        db.session.flush()
        db.session.add(Profile(user_id=user.id))
        db.session.add(UserSettings(user_id=user.id))
        db.session.commit()

        click.secho(f"\n✓ User created successfully!", fg="green")
        click.echo(f"  ID:      {user.id}")
        click.echo(f"  Email:   {user.email}")
        click.echo(f"  Name:    {user.full_name}")
        click.echo(f"  Plan:    {user.plan}")
        click.echo(f"  Admin:   {user.is_admin}")
        click.echo(f"  Verified:{user.is_verified}")

    @app.cli.command("create-admin")
    @click.option("--email", prompt="Admin email")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--first-name", default="Admin", prompt="First name")
    @click.option("--last-name", default="User", prompt="Last name")
    def create_admin(email, password, first_name, last_name):
        """Shortcut to create an admin user with premium plan."""
        if User.query.filter_by(email=email.lower().strip()).first():
            click.secho(f"✗ User '{email}' already exists.", fg="red")
            return

        from datetime import datetime, timezone, timedelta
        user = User(
            email=email.lower().strip(),
            first_name=first_name,
            last_name=last_name,
            is_admin=True,
            is_verified=True,
            plan="premium",
            plan_expires_at=datetime.now(timezone.utc) + timedelta(days=36500),  # 100 years
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        db.session.add(Profile(user_id=user.id))
        db.session.add(UserSettings(user_id=user.id))
        db.session.commit()
        click.secho(f"\n✓ Admin '{user.email}' created (ID {user.id}).", fg="green")

    @app.cli.command("promote-admin")
    @click.argument("email")
    def promote_admin(email):
        """Grant admin privileges to an existing user by email."""
        user = User.query.filter_by(email=email.lower()).first()
        if not user:
            click.secho(f"✗ No user found with email '{email}'.", fg="red")
            return
        user.is_admin = True
        db.session.commit()
        click.secho(f"✓ {user.email} is now an admin.", fg="green")

    @app.cli.command("set-plan")
    @click.argument("email")
    @click.argument("plan", type=click.Choice(["free", "pro", "premium"]))
    @click.option("--days", default=30, help="Days until plan expires")
    def set_plan(email, plan, days):
        """Set a user's subscription plan."""
        user = User.query.filter_by(email=email.lower()).first()
        if not user:
            click.secho(f"✗ No user found with email '{email}'.", fg="red")
            return
        from datetime import datetime, timezone, timedelta
        user.plan = plan
        if plan != "free":
            user.plan_expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        else:
            user.plan_expires_at = None
        db.session.commit()
        click.secho(f"✓ {user.email} plan set to '{plan}' ({days} days).", fg="green")

    @app.cli.command("reset-password")
    @click.argument("email")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def reset_password(email, password):
        """Reset a user's password from the CLI."""
        user = User.query.filter_by(email=email.lower()).first()
        if not user:
            click.secho(f"✗ No user found with email '{email}'.", fg="red")
            return
        user.set_password(password)
        db.session.commit()
        click.secho(f"✓ Password reset for {user.email}.", fg="green")

    @app.cli.command("list-users")
    @click.option("--plan", default=None, type=click.Choice(["free", "pro", "premium"]))
    @click.option("--admin-only", is_flag=True, default=False)
    def list_users(plan, admin_only):
        """List all users in the database."""
        q = User.query
        if plan:
            q = q.filter_by(plan=plan)
        if admin_only:
            q = q.filter_by(is_admin=True)
        users = q.order_by(User.created_at.desc()).all()
        if not users:
            click.echo("No users found.")
            return
        click.echo(f"\n{'ID':<6} {'Email':<35} {'Name':<25} {'Plan':<10} {'Admin':<6} {'Active'}")
        click.echo("-" * 95)
        for u in users:
            click.echo(f"{u.id:<6} {u.email:<35} {u.full_name:<25} {u.plan:<10} {str(u.is_admin):<6} {u.is_active}")
        click.echo(f"\nTotal: {len(users)}")

    @app.cli.command("seed-plans")
    def seed_plans():
        """Seed default pricing plans into the database."""
        if PricingPlan.query.count() > 0:
            click.secho("Plans already exist. Use the admin panel to edit them.", fg="yellow")
            return
        plans = [
            PricingPlan(
                slug="free", name="Free", price_kes=0, billing_period="forever",
                sort_order=1, is_active=True, is_popular=False,
                features=["3 AI CV generations/day", "3 ATS checks/day", "5 templates",
                          "PDF download", "Public CV link"],
                daily_cv_limit=3, daily_cover_letter_limit=3, daily_ats_limit=3,
                allow_docx=False, allow_version_history=False, allow_career_coach=False,
            ),
            PricingPlan(
                slug="pro", name="Pro", price_kes=799, billing_period="month",
                sort_order=2, is_active=True, is_popular=True,
                features=["Unlimited AI generations", "All 15+ templates", "PDF & DOCX download",
                          "Version history", "ATS optimizer", "Priority support"],
                daily_cv_limit=999, daily_cover_letter_limit=999, daily_ats_limit=999,
                allow_docx=True, allow_version_history=True, allow_career_coach=False,
            ),
            PricingPlan(
                slug="premium", name="Premium", price_kes=1499, billing_period="month",
                sort_order=3, is_active=True, is_popular=False,
                features=["Everything in Pro", "AI Career Coach", "Salary estimator",
                          "LinkedIn bio generator", "Early access to new features",
                          "Dedicated support"],
                daily_cv_limit=999, daily_cover_letter_limit=999, daily_ats_limit=999,
                allow_docx=True, allow_version_history=True, allow_career_coach=True,
            ),
        ]
        db.session.bulk_save_objects(plans)
        db.session.commit()
        click.secho("✓ 3 default pricing plans created.", fg="green")

    @app.cli.command("seed-templates")
    def seed_templates():
        """Seed default CV templates into the database."""
        if Template.query.count() > 0:
            click.secho("Templates already exist. Use admin panel to manage them.", fg="yellow")
            return
        templates = [
            Template(slug="classic-navy", name="Classic Navy", category="professional",
                     description="Clean, timeless design with navy accents. Best for corporate roles.",
                     is_premium=False, sort_order=1, accent_color="#1e3a5f", font_style="classic"),
            Template(slug="modern-blue", name="Modern Blue", category="professional",
                     description="Contemporary layout with blue accents. Great for tech and finance.",
                     is_premium=False, sort_order=2, accent_color="#2563eb", font_style="modern"),
            Template(slug="minimal-gray", name="Minimal Gray", category="minimal",
                     description="Ultra-clean minimal design. ATS-optimized, zero clutter.",
                     is_premium=False, sort_order=3, accent_color="#374151", font_style="minimal"),
            Template(slug="creative-teal", name="Creative Teal", category="creative",
                     description="Bold creative layout with teal accents. Ideal for designers and marketers.",
                     is_premium=True, sort_order=4, accent_color="#0d9488", font_style="modern"),
            Template(slug="executive-black", name="Executive Black", category="executive",
                     description="Premium executive design. Dark header, serif typography.",
                     is_premium=True, sort_order=5, accent_color="#111827", font_style="classic"),
            Template(slug="emerald-fresh", name="Emerald Fresh", category="professional",
                     description="Fresh green palette. Modern and approachable for all industries.",
                     is_premium=False, sort_order=6, accent_color="#059669", font_style="modern"),
            Template(slug="purple-bold", name="Purple Bold", category="creative",
                     description="Bold purple design for creative professionals who stand out.",
                     is_premium=True, sort_order=7, accent_color="#7c3aed", font_style="modern"),
            Template(slug="warm-terracotta", name="Warm Terracotta", category="creative",
                     description="Earthy warm tones. Unique and memorable for creative roles.",
                     is_premium=True, sort_order=8, accent_color="#b45309", font_style="classic"),
            Template(slug="clean-white", name="Clean White", category="minimal",
                     description="Pure white, high contrast. Maximum ATS compatibility.",
                     is_premium=False, sort_order=9, accent_color="#1f2937", font_style="minimal"),
            Template(slug="rose-modern", name="Rose Modern", category="creative",
                     description="Elegant rose accent with modern typography. Great for HR and education.",
                     is_premium=True, sort_order=10, accent_color="#e11d48", font_style="modern"),
            Template(slug="tech-dark", name="Tech Dark", category="technical",
                     description="Dark theme with code-inspired typography. Built for developers.",
                     is_premium=True, sort_order=11, accent_color="#06b6d4", font_style="modern"),
            Template(slug="two-column-pro", name="Two Column Pro", category="professional",
                     description="Two-column layout maximizes space. Ideal for senior professionals.",
                     is_premium=True, sort_order=12, accent_color="#4f46e5", font_style="modern"),
        ]
        db.session.bulk_save_objects(templates)
        db.session.commit()
        click.secho(f"✓ {len(templates)} templates seeded.", fg="green")

    @app.cli.command("db-init")
    def db_init():
        """Create all tables and seed default data. Run once on fresh install."""
        click.echo("Creating database tables...")
        db.create_all()
        click.secho("✓ Tables created.", fg="green")

        from flask import current_app
        ctx_app = current_app._get_current_object()
        runner = ctx_app.test_cli_runner()
        runner.invoke(args=["seed-plans"])
        runner.invoke(args=["seed-templates"])
        click.secho("\n✓ Database initialized. Run 'flask create-admin' to create your admin account.", fg="green")

    @app.cli.command("stats")
    def stats():
        """Print quick platform statistics."""
        from app.models import Resume, CoverLetter, AIUsage
        click.echo("\n── CVForge Platform Stats ──────────────────")
        click.echo(f"  Users:         {User.query.count()}")
        click.echo(f"  Pro/Premium:   {User.query.filter(User.plan.in_(['pro','premium'])).count()}")
        click.echo(f"  Resumes:       {Resume.query.count()}")
        click.echo(f"  Cover Letters: {CoverLetter.query.count()}")
        click.echo(f"  AI calls today:{AIUsage.get_total_daily_count()}")
        click.echo("────────────────────────────────────────────\n")
