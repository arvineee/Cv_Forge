#!/usr/bin/env python3
"""CVForge CI fix. Run from the repo root (the folder that contains app/).

    python patch.py

Safe to run twice. Backs up each file as <name>.bak first.
"""
import os
import shutil
import sys

PATCHES = [
    (
        "app/routes/dashboard.py",
        [],  # handled by fix_dashboard() below
    ),
    (
        "app/services/visitor_tracking.py",
        [
            (
                "                db.session.remove()\n"
                "                for _ in batch:",
                "                with app.app_context():\n"
                "                    db.session.remove()\n"
                "                for _ in batch:",
            ),
        ],
    ),
    (
        "app/services/growth_analytics.py",
        [
            (
                "from sqlalchemy import func\n",
                "from sqlalchemy import func, select\n",
            ),
            (
                "ActivityLog.user_id.in_(cohort)",
                "ActivityLog.user_id.in_(select(cohort.c.id))",
            ),
        ],
    ),
]


def fix_dashboard(src):
    """Make now_utc naive via utcnow(), whatever the line looked like before."""
    import re
    if "now_utc=utcnow()" in src and "import utcnow" in src:
        return src
    src = re.sub(r"now_utc=[^\n]*?,[^\n]*\n", "now_utc=utcnow(),\n", src, count=1)
    if "import utcnow" not in src:
        src = src.replace("    return render_template(\"dashboard/index.html\",",
                          "    from app.models import utcnow\n"
                          "    return render_template(\"dashboard/index.html\",", 1)
    return src


def main():
    root = os.getcwd()
    if not os.path.isdir(os.path.join(root, "app")):
        sys.exit("Run this from the repo root (the folder that contains app/).")

    changed = 0
    for rel, edits in PATCHES:
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            print(f"SKIP  {rel} (not found)")
            continue
        with open(path, encoding="utf-8") as f:
            src = f.read()
        new = fix_dashboard(src) if rel.endswith("routes/dashboard.py") else src
        for old, repl in edits:
            if repl in new:
                continue  # already applied
            if old not in new:
                print(f"WARN  {rel}: could not find text to replace:\n      {old.strip()[:70]}")
                continue
            new = new.replace(old, repl, 1)
        if new == src:
            print(f"OK    {rel} (nothing to change)")
            continue
        shutil.copy2(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        changed += 1
        print(f"FIXED {rel}")

    print(f"\nDone. {changed} file(s) changed. Now run: python -m pytest -q")


if __name__ == "__main__":
    main()

