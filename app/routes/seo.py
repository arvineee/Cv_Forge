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
from flask import Blueprint, Response, url_for, current_app
from werkzeug.routing import BuildError

seo_bp = Blueprint("seo", __name__)

# Public, indexable pages only. Each entry: (endpoint, changefreq, priority).
# Wrapped individually in try/except at build time (see sitemap() below) so
# a renamed/removed route in the future degrades gracefully instead of
# taking the whole sitemap down with a 500.
PUBLIC_PAGES = [
    ("main.index", "daily", "1.0"),
    ("auth.login", "monthly", "0.3"),
    ("auth.register", "monthly", "0.5"),
    ("billing.plans", "weekly", "0.8"),
    ("templates_gallery.index", "weekly", "0.7"),
    ("support.index", "monthly", "0.4"),
]

# Path prefixes that must never be indexed: logged-in areas, admin, and
# machine-to-machine endpoints. Kept in one place so robots.txt and any
# future noindex audit can reference the same list.
DISALLOWED_PREFIXES = [
    "/dashboard",
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


@seo_bp.route("/robots.txt")
def robots():
    lines = [
        "User-agent: *",
        *[f"Disallow: {p}" for p in DISALLOWED_PREFIXES],
        "Allow: /billing/plans",
        "Allow: /templates/",
        "",
        f"Sitemap: {url_for('seo.sitemap', _external=True)}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@seo_bp.route("/sitemap.xml")
def sitemap():
    urls = []
    for endpoint, changefreq, priority in PUBLIC_PAGES:
        try:
            loc = url_for(endpoint, _external=True)
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


