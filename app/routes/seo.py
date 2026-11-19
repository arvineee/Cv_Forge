"""
CVForge AI - SEO Blueprint

Serves /robots.txt and /sitemap.xml so search engines can actually find
and correctly crawl the site. Neither existed before, which meant Google
had no reliable map of public pages and no explicit instruction to stay
out of logged-in-only areas (dashboard, CV editor, billing, admin, etc.).

Registration (add to app/__init__.py):

    from app.routes.seo import seo_bp
    app.register_blueprint(seo_bp)

No url_prefix — these must be served from the domain root
(https://yourdomain.com/robots.txt, https://yourdomain.com/sitemap.xml)
or crawlers won't find them.
"""
from flask import Blueprint, Response, url_for, current_app, request, has_request_context
from werkzeug.routing import BuildError

seo_bp = Blueprint("seo", __name__)


def site_base_url() -> str:
    """Public origin used in canonical URLs, og:url and the sitemap.

    Uses the SITE_URL setting when it is a full http(s) address, otherwise
    the address of the current request (the original behaviour).
    """
    configured = (current_app.config.get("SITE_URL") or "").strip().rstrip("/")
    if configured.startswith(("http://", "https://")):
        return configured
    if has_request_context():
        return request.url_root.rstrip("/")
    return ""


_asset_version_cache = {}


def _asset_version() -> str:
    """Cache-busting token derived from the newest CSS/JS file, so browsers
    pick up a new stylesheet automatically after every deploy (no hand-edited
    ?v=1 to forget)."""
    if "v" not in _asset_version_cache:
        import os
        newest = 0
        for sub in ("css", "js"):
            folder = os.path.join(current_app.static_folder or "", sub)
            if os.path.isdir(folder):
                for name in os.listdir(folder):
                    try:
                        newest = max(newest, int(os.path.getmtime(os.path.join(folder, name))))
                    except OSError:
                        pass
        _asset_version_cache["v"] = str(newest or 1)
    return _asset_version_cache["v"]


@seo_bp.app_context_processor
def _inject_site_url():
    from app.services import site_content as _sc
    from app.services.site_content import PAYMENT_CARD_NOTE, PRICING_FAQS, SEO_KEYWORDS
    return {
        "site_url": site_base_url(),
        "asset_version": _asset_version(),
        "now_year": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).year,
        "payment_card_note": PAYMENT_CARD_NOTE,
        "pricing_faqs": PRICING_FAQS,
        "seo_keywords": SEO_KEYWORDS,
        "templates_keywords": _sc.TEMPLATES_KEYWORDS,
        "pricing_keywords": _sc.PRICING_KEYWORDS,
        "register_keywords": _sc.REGISTER_KEYWORDS,
        "guide_keywords": _sc.GUIDE_KEYWORDS,
        "jobs_keywords": _sc.JOBS_KEYWORDS,
        "ats_keywords": _sc.ATS_KEYWORDS,
    }


def _absolute(endpoint: str, **values) -> str:
    """Absolute URL for an endpoint, rooted at the public site address."""
    return site_base_url() + url_for(endpoint, **values)

# Public, indexable pages only. Each entry: (endpoint, changefreq, priority).
# Wrapped individually in try/except at build time (see sitemap() below) so
# a renamed/removed route in the future degrades gracefully instead of
# taking the whole sitemap down with a 500.
#
# /billing/plans is intentionally absent: it declares /pricing as its
# canonical URL, so only /pricing is listed.
PUBLIC_PAGES = [
    ("main.index", "weekly", "1.0"),
    ("main.pricing", "weekly", "0.9"),
    ("templates_gallery.index", "weekly", "0.8"),
    ("cv_examples.index", "weekly", "0.7"),
    ("free_ats.checker", "monthly", "0.8"),
    ("dashboard.job_discovery", "daily", "0.8"),
    ("auth.register", "monthly", "0.6"),
    ("guide.index", "monthly", "0.6"),
    ("main.about", "monthly", "0.5"),
    ("support.index", "monthly", "0.4"),
    ("main.privacy", "yearly", "0.2"),
    ("main.terms", "yearly", "0.2"),
]

# Path prefixes that must never be indexed: logged-in areas, admin, and
# machine-to-machine endpoints. Kept in one place so robots.txt and any
# future noindex audit can reference the same list.
DISALLOWED_PREFIXES = [
    "/dashboard",
    "/career/",
    "/cv/",
    "/cover-letter/",
    "/ats/",
    "/billing/",       # /billing/plans is allowed back below with Allow
    "/admin/",
    "/api/",
    "/webhooks/",
    "/auth/reset-password",
    "/auth/verify",       # actual route is /auth/verify/<token> — was
                           # "/auth/verify-email", which doesn't exist
                           # and never matched, leaving tokenized
                           # verification links crawlable/indexable
    "/auth/forgot-password",
    "/support/ask",
]


@seo_bp.route("/manifest.webmanifest")
def manifest():
    """Web app manifest: makes the site installable (PWA) and TWA-ready."""
    import json
    data = {
        "name": "CVForge AI: CV Builder & Job Search",
        "short_name": "CVForge",
        "description": "Build CVs, check your ATS score, write cover letters, find jobs and track applications.",
        "id": "/",
        "start_url": "/dashboard?source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#ffffff",
        "theme_color": "#0b3d6b",
        "categories": ["business", "productivity", "education"],
        "icons": [
            {"src": url_for("static", filename="icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": url_for("static", filename="icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": url_for("static", filename="icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "New CV", "url": "/cv/start"},
            {"name": "Find jobs", "url": "/career/jobs"},
            {"name": "ATS checker", "url": "/ats/"},
        ],
    }
    return Response(json.dumps(data, indent=2), mimetype="application/manifest+json")


@seo_bp.route("/robots.txt")
def robots():
    lines = [
        "User-agent: *",
        *[f"Disallow: {p}" for p in DISALLOWED_PREFIXES],
        "Allow: /billing/plans",
        "Allow: /templates/",
        "Allow: /guide",
        "Allow: /cv-examples",
        "Allow: /free-ats-checker",
        "Allow: /pricing",
        "Allow: /about",
        "Allow: /career/jobs$",
        "",
        f"Sitemap: {_absolute('seo.sitemap')}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@seo_bp.route("/sitemap.xml")
def sitemap():
    urls = []
    for endpoint, changefreq, priority in PUBLIC_PAGES:
        try:
            loc = _absolute(endpoint)
        except BuildError:
            # Route renamed or removed since PUBLIC_PAGES was last
            # updated — skip it rather than 500ing the whole sitemap.
            current_app.logger.warning(f"sitemap: endpoint '{endpoint}' not found, skipping")
            continue
        urls.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )

    # One URL per CV example page (generated from app/services/cv_examples.py).
    from app.services.cv_examples import all_examples
    for ex in all_examples():
        try:
            loc = _absolute("cv_examples.detail", slug=ex["slug"])
        except BuildError:
            continue
        urls.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            "    <changefreq>monthly</changefreq>\n"
            "    <priority>0.6</priority>\n"
            "  </url>"
        )

    # If you later add public, shareable pages (e.g. a public CV link or
    # a template detail page), append them here the same way — loop over
    # the DB rows and build a <url> block per row, same as above.

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) +
        "\n</urlset>"
    )
    return Response(xml, mimetype="application/xml")


