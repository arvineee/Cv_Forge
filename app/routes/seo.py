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


@seo_bp.app_context_processor
def _inject_site_url():
    from app.services.site_content import PAYMENT_CARD_NOTE, PRICING_FAQS
    return {
        "site_url": site_base_url(),
        "payment_card_note": PAYMENT_CARD_NOTE,
        "pricing_faqs": PRICING_FAQS,
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
        "Allow: /guide",
        "Allow: /pricing",
        "Allow: /about",
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


