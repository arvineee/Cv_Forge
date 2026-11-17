"""Configuration fallback tests; intentionally do not import the Flask app."""
import importlib
import os

import config


def test_blank_optional_environment_values_use_safe_defaults(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv("DATABASE_URL", "")
        patch.setenv("GEMINI_MODEL", "")
        patch.setenv("GOOGLE_REDIRECT_URI", "")
        loaded = importlib.reload(config).Config
        assert loaded.SQLALCHEMY_DATABASE_URI.startswith("sqlite:///")
        assert loaded.SQLALCHEMY_DATABASE_URI.endswith("/instance/cvforge.db")
        assert loaded.GEMINI_MODEL == "gemini-3.5-flash-lite"
        assert loaded.GOOGLE_REDIRECT_URI == "https://cvforge.site/auth/google/callback"
    importlib.reload(config)


def test_explicit_environment_values_override_defaults(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv("DATABASE_URL", "postgresql://example.invalid/cvforge")
        patch.setenv("GEMINI_MODEL", "custom-model-id")
        patch.setenv("GOOGLE_REDIRECT_URI", "https://example.com/auth/google/callback")
        loaded = importlib.reload(config).Config
        assert loaded.SQLALCHEMY_DATABASE_URI == "postgresql://example.invalid/cvforge"
        assert loaded.GEMINI_MODEL == "custom-model-id"
        assert loaded.GOOGLE_REDIRECT_URI == "https://example.com/auth/google/callback"
    importlib.reload(config)
