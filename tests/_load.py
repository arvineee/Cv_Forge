"""
Load a module from its file path without importing the `app` package.

`app/__init__.py` imports the whole Flask stack (flask_login, flask_sqlalchemy,
...). Pure-logic tests should not need all of that installed, so they load the
single module they test directly. Tests that need the full app live in
test_app_smoke.py and import normally.
"""
import importlib.util
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load(relpath: str, name: str):
    path = os.path.join(ROOT, relpath)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
