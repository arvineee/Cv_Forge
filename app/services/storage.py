"""
Shared helpers for file storage.
"""
import os

from flask import current_app


def resolve_upload_folder() -> str:
    """
    Absolute path of the upload directory, created if missing.

    UPLOAD_FOLDER may be absolute or relative to the project root. A relative
    value is resolved against the project directory, not the working directory,
    so it behaves the same under gunicorn on PythonAnywhere.
    """
    folder = current_app.config["UPLOAD_FOLDER"]
    if not os.path.isabs(folder):
        folder = os.path.join(current_app.root_path, "..", folder)
    folder = os.path.abspath(folder)
    os.makedirs(folder, exist_ok=True)
    return folder
