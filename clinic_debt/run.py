from app import create_app, db
from app.models import User, Patient, Debt, Payment
from werkzeug.security import generate_password_hash
import os

app = create_app(os.environ.get("FLASK_ENV", "development"))


@app.shell_context_processor
def make_shell_context():
    return dict(db=db, User=User, Patient=Patient, Debt=Debt, Payment=Payment)


@app.cli.command("seed")
def seed():
    """Seed the database with a default admin user."""
    if not User.query.filter_by(email="admin@clinic.ke").first():
        admin = User(
            name     = "Admin",
            email    = "admin@clinic.ke",
            password = generate_password_hash("admin123"),
            role     = "admin",
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin seeded → admin@clinic.ke / admin123")
    else:
        print("ℹ️  Admin already exists.")


if __name__ == "__main__":
    app.run(debug=True,port=5050)
