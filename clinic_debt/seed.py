#!/usr/bin/env python
"""Standalone seed script — run with: python seed.py"""
from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models import User

app = create_app("development")

with app.app_context():
    db.create_all()
    if not User.query.filter_by(email="admin@clinic.ke").first():
        admin = User(
            name     = "Admin",
            email    = "admin@clinic.ke",
            password = generate_password_hash("admin123"),
            role     = "admin",
        )
        db.session.add(admin)
        db.session.commit()
        print("✅  Admin created → admin@clinic.ke / admin123")
        print("⚠️   Change your password after first login!")
    else:
        print("ℹ️   Admin already exists — nothing to do.")
