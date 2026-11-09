"""On/off switches for payment providers (Paystack, IntaSend).

Turning a provider off only stops NEW checkouts from starting. Nothing is
disconnected: API keys, webhooks, callbacks and status polling stay active, so
payments that are already in flight still confirm normally. Turn it back on at
any time from Admin -> Payment methods.

State lives in instance/payment_settings.json, so it survives deploys (the
deploy script never uploads instance/) and needs no database migration.
Default for every provider is ON. A provider can also start OFF via the env
vars PAYSTACK_ENABLED=false / INTASEND_ENABLED=false until it is switched in
the admin page.
"""
import json
import os
import tempfile

PROVIDERS = {
    "paystack": {"label": "Paystack", "env": "PAYSTACK_ENABLED",
                 "covers": "Cards and M-Pesa (checkout page)"},
    "intasend": {"label": "IntaSend", "env": "INTASEND_ENABLED",
                 "covers": "M-Pesa STK push"},
}
FILENAME = "payment_settings.json"

_cache = {"path": None, "mtime": None, "data": {}}


def settings_path():
    from flask import current_app
    return os.path.join(current_app.instance_path, FILENAME)


def _env_default(provider):
    raw = os.environ.get(PROVIDERS[provider]["env"], "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _read(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _cache["path"] == path and _cache["mtime"] == mtime:
        return _cache["data"]
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    _cache.update(path=path, mtime=mtime, data=data)
    return data


def is_enabled(provider, path=None):
    """True if new checkouts may start with this provider. Unknown names are off."""
    if provider not in PROVIDERS:
        return False
    value = _read(path or settings_path()).get(provider)
    return value if isinstance(value, bool) else _env_default(provider)


def all_status(path=None):
    return {name: is_enabled(name, path) for name in PROVIDERS}


def set_enabled(provider, enabled, path=None):
    """Persist one switch atomically; the other providers' values are kept."""
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown payment provider: {provider}")
    path = path or settings_path()
    data = dict(_read(path))
    data[provider] = bool(enabled)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    _cache.update(path=None, mtime=None, data={})
