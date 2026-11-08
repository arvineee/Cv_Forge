"""Upload the git-tracked project files to PythonAnywhere and reload the web app.

Used by .github/workflows/deploy.yml. Uses only the PythonAnywhere HTTP API,
so it works on every plan (no SSH needed).

Safety: only files tracked by git are uploaded, and secrets, databases,
uploads and caches are always skipped, so production data and the server's
own .env are never overwritten.

Environment:
  PA_USERNAME     PythonAnywhere username
  PA_API_TOKEN    API token (Account > API token)
  PA_PROJECT_DIR  Remote project folder, e.g. /home/cvforge/cvforge
  PA_DOMAIN       Web app domain, e.g. cvforge.pythonanywhere.com
  PA_HOST         Optional. www.pythonanywhere.com (default) or eu.pythonanywhere.com

Usage: python scripts/pa_deploy.py [--dry-run]
"""
import os
import re
import subprocess
import sys
import time

import requests

SKIP_PREFIXES = (".git", ".github/", "tests/", "tools/", "scripts/", "instance/", "uploads/",
                 "__pycache__/", ".pytest_cache/")
SKIP_PARTS = ("__pycache__",)
SKIP_NAMES = {".env", ".gitignore", ".mannual.diff.swp", "requirements-dev.txt"}
SKIP_SUFFIXES = (".pyc", ".db", ".sqlite", ".sqlite3", ".swp", ".log")


def should_upload(path: str) -> bool:
    name = os.path.basename(path)
    if name in SKIP_NAMES or name.startswith(".env"):
        return False
    if path.startswith(SKIP_PREFIXES) or any(p in path.split("/") for p in SKIP_PARTS):
        return False
    return not path.endswith(SKIP_SUFFIXES)


def tracked_files():
    out = subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True).stdout
    return [p for p in out.splitlines() if p and should_upload(p) and os.path.isfile(p)]


def post_with_retry(session, url, path=None, max_tries=12):
    """POST (optionally uploading `path`), waiting out PythonAnywhere's 429 throttling."""
    r = None
    for attempt in range(1, max_tries + 1):
        try:
            if path:
                with open(path, "rb") as fh:
                    r = session.post(url, files={"content": fh}, timeout=60)
            else:
                r = session.post(url, timeout=60)
        except requests.RequestException as e:
            print(f"  network error ({e}); retrying in 5s [{attempt}/{max_tries}]")
            time.sleep(5)
            continue
        if r.status_code != 429:
            return r
        m = re.search(r"available in (\d+) second", r.text)
        wait = int(m.group(1)) + 2 if m else 30
        print(f"  throttled (429); waiting {wait}s [{attempt}/{max_tries}]", flush=True)
        time.sleep(wait)
    return r


def main():
    dry = "--dry-run" in sys.argv
    files = tracked_files()
    if dry:
        print(f"Would upload {len(files)} files:")
        for f in files:
            print("  ", f)
        return 0

    env = {k: os.environ.get(k, "").strip() for k in
           ("PA_USERNAME", "PA_API_TOKEN", "PA_PROJECT_DIR", "PA_DOMAIN")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        sys.exit(f"Missing or empty: {', '.join(missing)}")
    user, token = env["PA_USERNAME"], env["PA_API_TOKEN"]
    remote, domain = env["PA_PROJECT_DIR"].rstrip("/"), env["PA_DOMAIN"]
    host = os.environ.get("PA_HOST") or "www.pythonanywhere.com"
    api = f"https://{host}/api/v0/user/{user}"
    session = requests.Session()
    session.headers["Authorization"] = f"Token {token}"

    print(f"Host: {host} | user: {user} | project dir: {remote} | domain: {domain} | files: {len(files)}")
    try:
        pre = session.get(f"{api}/files/path{remote}/", timeout=30)
    except requests.RequestException as e:
        sys.exit(f"Could not reach {host}: {e}")
    hints = {
        401: "API token or username is wrong (token must belong to this username, on this host).",
        403: "Token not allowed for this path. Check PA_PROJECT_DIR and PA_USERNAME.",
        404: "Folder not found on PythonAnywhere. Fix PA_PROJECT_DIR (full path, e.g. /home/<user>/<folder>), "
             "or set PA_HOST to eu.pythonanywhere.com if your account is on the EU server.",
    }
    if pre.status_code != 200:
        sys.exit(f"Preflight failed: HTTP {pre.status_code}. "
                 f"{hints.get(pre.status_code, pre.text[:200])}")
    print("Preflight OK")

    for i, path in enumerate(files, 1):
        r = post_with_retry(session, f"{api}/files/path{remote}/{path}", path=path)
        if r is None or r.status_code not in (200, 201):
            sys.exit(f"Upload failed for {path}: HTTP {getattr(r, 'status_code', 'n/a')} {getattr(r, 'text', '')[:200]}")
        if i % 25 == 0 or i == len(files):
            print(f"Uploaded {i}/{len(files)}")

    r = post_with_retry(session, f"{api}/webapps/{domain}/reload/")
    if r is None or r.status_code != 200:
        sys.exit(f"Reload failed: HTTP {getattr(r, 'status_code', 'n/a')} {getattr(r, 'text', '')[:200]}")
    print(f"Reloaded {domain}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

