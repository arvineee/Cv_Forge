from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from config import config

db      = SQLAlchemy()
login   = LoginManager()
migrate = Migrate()
csrf    = CSRFProtect()

login.login_view              = "auth.login"
login.login_message           = "Please log in to access this page."
login.login_message_category  = "warning"


def create_app(env="default"):
    app = Flask(__name__)
    app.config.from_object(config[env])

    db.init_app(app)
    login.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app.auth.routes  import auth_bp
    from app.main.routes  import main_bp
    from app.admin.routes import admin_bp
    from app.api.routes   import api_bp

    app.register_blueprint(auth_bp,  url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(api_bp,   url_prefix="/api/v1")

    from datetime import date

    @app.context_processor
    def inject_globals():
        return {"now_date": str(date.today())}

    with app.app_context():
        db.create_all()

    return app
