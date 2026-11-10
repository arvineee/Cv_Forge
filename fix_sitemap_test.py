#!/usr/bin/env python3
"""
Run from the cvforge project root:   python fix_sitemap_test.py

Fixes tests/test_international.py::test_sitemap_lists_public_pages_only
(both classes). The test checked for '/admin' as a raw substring of the
sitemap XML, which now matches /cv-examples/administrative-assistant.
This rewrites those assertNotIn(...) calls to compare URL *path segments*
instead. A .bak copy is saved first. Safe to run twice.
"""
import ast
import re
import shutil
import sys
from pathlib import Path

TARGET = Path("tests/test_international.py")
MARKER = "# --- sitemap path helper (added by fix_sitemap_test.py) ---"

HELPER = f'''
{MARKER}
def _assert_path_not_in_sitemap(case, prefix, xml, msg=None):
    """Fail only if a <loc> path equals `prefix` or sits under it as a whole
    path segment ('/admin' matches /admin and /admin/x, not /administrative-x)."""
    import re as _re
    from urllib.parse import urlparse as _urlparse
    prefix = str(prefix).rstrip("/") or "/"
    paths = [_urlparse(u).path for u in _re.findall(r"<loc>([^<]+)</loc>", xml)]
    bad = [p for p in paths if p == prefix or p.startswith(prefix + "/")]
    case.assertFalse(bad, msg or f"{{prefix}} unexpectedly in sitemap: {{bad}}")
# --- end helper ---
'''

CALL = re.compile(
    r"self\.assertNotIn\(\s*([^,()\n]+?)\s*,\s*([^,()\n]+?)\s*(?:,\s*([^()\n]+?)\s*)?\)"
)


def main():
    if not TARGET.exists():
        sys.exit(f"Run this from the project root; {TARGET} not found.")
    src = TARGET.read_text(encoding="utf-8")
    if MARKER in src:
        print("Already patched - nothing to do.")
        return

    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    funcs = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "test_sitemap_lists_public_pages_only"
    ]
    if not funcs:
        sys.exit("test_sitemap_lists_public_pages_only not found; no changes made.")

    changed = 0
    # patch bottom-up so line numbers stay valid
    for fn in sorted(funcs, key=lambda n: -n.lineno):
        start, end = fn.lineno - 1, fn.end_lineno
        body = "".join(lines[start:end])

        def repl(m):
            a, b, c = m.group(1), m.group(2), m.group(3)
            # only rewrite checks made against the sitemap / xml text
            if "robots" in b.lower():
                return m.group(0)
            return f"_assert_path_not_in_sitemap(self, {a}, {b}" + (f", {c}" if c else "") + ")"

        new_body, n = CALL.subn(repl, body)
        if n:
            lines[start:end] = [new_body]
            changed += n

    if not changed:
        sys.exit(
            "Found the test but no simple assertNotIn(...) to rewrite.\n"
            "Paste the test function to me and I'll adapt the script."
        )

    out = "".join(lines)
    # insert helper after the last top-level import block
    tree2 = ast.parse(out)
    last_import = max(
        (n.end_lineno for n in tree2.body if isinstance(n, (ast.Import, ast.ImportFrom))),
        default=0,
    )
    ol = out.splitlines(keepends=True)
    ol.insert(last_import, HELPER)
    out = "".join(ol)
    ast.parse(out)  # sanity: must still be valid Python

    shutil.copy(TARGET, TARGET.with_suffix(".py.bak"))
    TARGET.write_text(out, encoding="utf-8")
    print(f"Patched {changed} assertion(s) in {TARGET} (backup: {TARGET}.bak)")
    print("Now run:  python -m pytest tests/test_international.py -q")


if __name__ == "__main__":
    main()

