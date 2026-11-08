"""Deploy git-tracked files to PythonAnywhere (HTTP API only, works on every plan).

What it does, in order:
  1. Works out WHICH files to upload: only files changed since the last
     successful deploy (a marker file on the server remembers that commit).
     Falls back to a full upload if there is no marker, it is unknown, or --full.
  2. Backs up the live SQLite database ON the server (never to GitHub) BEFORE
     any file is changed. If the backup fails, nothing is uploaded.
  3. Uploads the changed files, reloads the web app, then records the deployed commit.

Never uploaded: .env, databases, uploads/, instance/, tests, tools, scripts, caches.

Environment:
  PA_USERNAME, PA_API_TOKEN   required
  PA_PROJECT_DIR, PA_DOMAIN   required (e.g. /home/CvForge/Cv_Forge, cvforge.pythonanywhere.com)
  PA_HOST          optional, www.pythonanywhere.com (default) or eu.pythonanywhere.com
  PA_DB_PATH       optional, default <PA_PROJECT_DIR>/instance/cvforge.db
  PA_BACKUP_DIR    optional, default /home/<PA_USERNAME>/backups
  PA_FORCE_FULL    optional, "true" = upload everything

Usage: python scripts/pa_deploy.py [--dry-run] [--full] [--no-backup]
"""
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import requests

SKIP_PREFIXES = (".git", ".github/", "tests/", "tools/", "scripts/", "instance/", "uploads/",
                 "__pycache__/", ".pytest_cache/")
SKIP_PARTS = ("__pycache__",)
SKIP_NAMES = {".env", ".gitignore", ".mannual.diff.swp", "requirements-dev.txt"}
SKIP_SUFFIXES = (".pyc", ".db", ".sqlite", ".sqlite3", ".swp", ".log")

MARKER = ".last_deployed_sha"
KEEP_BACKUPS = 10


def should_upload(path: str) -> bool:
    name = os.path.basename(path)
    if name in SKIP_NAMES or name.startswith(".env"):
        return False
    if path.startswith(SKIP_PREFIXES) or any(p in path.split("/") for p in SKIP_PARTS):
        return False
    return not path.endswith(SKIP_SUFFIXES)


def git_z(*args):
    out = subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout
    return [p for p in out.split("\0") if p]


def commit_exists(sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True).returncode == 0


def deployable(paths):
    return [p for p in paths if should_upload(p) and os.path.isfile(p)]


def call(session, method, url, *, path=None, content=None, max_tries=12):
    """HTTP call that waits out PythonAnywhere's 429 throttling and flaky networks."""
    r = None
    for attempt in range(1, max_tries + 1):
        try:
            if path:
                with open(path, "rb") as fh:
                    r = session.request(method, url, files={"content": fh}, timeout=120)
            elif content is not None:
                r = session.request(method, url, files={"content": content}, timeout=120)
            else:
                r = session.request(method, url, timeout=120)
        except requests.RequestException as e:
            print(f"  network error ({e}); retrying in 5s [{attempt}/{max_tries}]", flush=True)
            time.sleep(5)
            continue
        if r.status_code != 429:
            return r
        m = re.search(r"available in (\d+) second", r.text)
        wait = int(m.group(1)) + 2 if m else 30
        print(f"  throttled (429); waiting {wait}s [{attempt}/{max_tries}]", flush=True)
        time.sleep(wait)
    return r


def fail(msg):
    sys.exit(msg)


def read_marker(session, api, remote):
    r = call(session, "GET", f"{api}/files/path{remote}/{MARKER}")
    if r is not None and r.status_code == 200:
        sha = r.text.strip()
        return sha if re.fullmatch(r"[0-9a-f]{40}", sha) else None
    return None


def backup_database(session, api, user, remote, stamp):
    db_path = os.environ.get("PA_DB_PATH", "").strip() or f"{remote}/instance/cvforge.db"
    backup_dir = (os.environ.get("PA_BACKUP_DIR", "").strip() or f"/home/{user}/backups").rstrip("/")
    r = call(session, "GET", f"{api}/files/path{db_path}")
    if r is None or r.status_code != 200:
        fail(f"BACKUP FAILED: could not read database at {db_path} "
             f"(HTTP {getattr(r, 'status_code', 'n/a')}). Nothing was uploaded. "
             f"Set PA_DB_PATH if the database lives elsewhere.")
    data = r.content
    if not data.startswith(b"SQLite format 3\x00"):
        fail(f"BACKUP FAILED: {db_path} is not a valid SQLite database. Nothing was uploaded.")
    dest = f"{backup_dir}/predeploy-{stamp}.db"
    r = call(session, "POST", f"{api}/files/path{dest}", content=data)
    if r is None or r.status_code not in (200, 201):
        fail(f"BACKUP FAILED: could not save to {dest} "
             f"(HTTP {getattr(r, 'status_code', 'n/a')}). Nothing was uploaded.")
    print(f"Database backed up: {dest} ({len(data) / 1024:.0f} KB)")
    # keep only the newest backups (best effort)
    try:
        t = call(session, "GET", f"{api}/files/tree/?path={backup_dir}")
        if t is not None and t.status_code == 200:
            old = sorted(p for p in t.json() if os.path.basename(p).startswith("predeploy-"))
            for p in old[:-KEEP_BACKUPS]:
                call(session, "DELETE", f"{api}/files/path{p}")
                print(f"  pruned old backup {os.path.basename(p)}")
    except Exception as e:  # never fail a deploy over pruning
        print(f"  (could not prune old backups: {e})")


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    force_full = "--full" in argv or os.environ.get("PA_FORCE_FULL", "").lower() == "true"
    skip_backup = "--no-backup" in argv

    head = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    everything = deployable(git_z("ls-files", "-z"))

    env = {k: os.environ.get(k, "").strip() for k in
           ("PA_USERNAME", "PA_API_TOKEN", "PA_PROJECT_DIR", "PA_DOMAIN")}
    if dry and not all(env.values()):
        print(f"Dry run (no server access): would upload up to {len(everything)} files")
        return 0
    missing = [k for k, v in env.items() if not v]
    if missing:
        fail(f"Missing or empty: {', '.join(missing)}")
    user, token = env["PA_USERNAME"], env["PA_API_TOKEN"]
    remote, domain = env["PA_PROJECT_DIR"].rstrip("/"), env["PA_DOMAIN"]
    host = os.environ.get("PA_HOST") or "www.pythonanywhere.com"
    api = f"https://{host}/api/v0/user/{user}"
    session = requests.Session()
    session.headers["Authorization"] = f"Token {token}"

    print(f"Host: {host} | user: {user} | project dir: {remote} | domain: {domain}")
    try:
        pre = session.get(f"{api}/files/path{remote}/", timeout=30)
    except requests.RequestException as e:
        fail(f"Could not reach {host}: {e}")
    hints = {
        401: "API token or username is wrong (token must belong to this username, on this host).",
        403: "Token not allowed for this path. Check PA_PROJECT_DIR and PA_USERNAME.",
        404: "Folder not found on PythonAnywhere. Fix PA_PROJECT_DIR (full path), "
             "or set PA_HOST to eu.pythonanywhere.com if your account is on the EU server.",
    }
    if pre.status_code != 200:
        fail(f"Preflight failed: HTTP {pre.status_code}. {hints.get(pre.status_code, pre.text[:200])}")
    print("Preflight OK")

    # ---- decide what to upload -------------------------------------------------
    base = None if force_full else read_marker(session, api, remote)
    deleted = []
    if base == head and not force_full:
        print(f"Server already at {head[:7]}. Nothing to deploy.")
        return 0
    if base and commit_exists(base):
        files = deployable(git_z("diff", "-z", "--name-only", "--diff-filter=ACMR", base, "HEAD"))
        deleted = [p for p in git_z("diff", "-z", "--name-only", "--diff-filter=D", base, "HEAD")
                   if should_upload(p)]
        print(f"Incremental deploy {base[:7]} -> {head[:7]}: {len(files)} changed file(s)")
    else:
        files = everything
        why = "forced" if force_full else ("no marker on server" if not base else "last deployed commit unknown")
        print(f"Full deploy ({why}): {len(files)} file(s)")

    if dry:
        for f in files:
            print("  ", f)
        return 0

    if not files:
        print("No deployable files changed (docs/tests only). Skipping upload and reload.")
        call(session, "POST", f"{api}/files/path{remote}/{MARKER}", content=head.encode())
        return 0

    # ---- back up BEFORE touching anything --------------------------------------
    if skip_backup:
        print("WARNING: --no-backup given, skipping database backup")
    else:
        backup_database(session, api, user, remote,
                        f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{head[:7]}")

    # ---- upload ----------------------------------------------------------------
    for i, path in enumerate(files, 1):
        r = call(session, "POST", f"{api}/files/path{remote}/{path}", path=path)
        if r is None or r.status_code not in (200, 201):
            fail(f"Upload failed for {path}: HTTP {getattr(r, 'status_code', 'n/a')} "
                 f"{getattr(r, 'text', '')[:200]}\n"
                 f"Progress is safe: re-run and it will resume (marker not updated).")
        if i % 10 == 0 or i == len(files):
            print(f"Uploaded {i}/{len(files)}", flush=True)

    r = call(session, "POST", f"{api}/webapps/{domain}/reload/")
    if r is None or r.status_code != 200:
        fail(f"Reload failed: HTTP {getattr(r, 'status_code', 'n/a')} {getattr(r, 'text', '')[:200]}")
    print(f"Reloaded {domain}")

    call(session, "POST", f"{api}/files/path{remote}/{MARKER}", content=head.encode())
    if deleted:
        print("Note: these files were deleted in git but NOT removed from the server:")
        for p in deleted:
            print("  ", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())

