"""CVForge AI - public CV example pages (SEO landing pages)."""
from flask import Blueprint, abort, render_template, url_for

from app.routes.seo import site_base_url
from app.services import cv_examples as data
from app.services.site_content import faq_jsonld

cv_examples_bp = Blueprint("cv_examples", __name__)

INDEX_TITLE = "CV Examples by Job: Samples and Writing Tips | CVForge"
INDEX_DESCRIPTION = (
    "Browse CV examples for nurses, developers, accountants, teachers and more. "
    "See a sample summary, experience bullets and skills, then build yours free."
)
INDEX_KEYWORDS = ("CV examples, resume examples, sample CV, CV samples, CV examples by job, "
                  "how to write a CV, CV maker, resume maker")


@cv_examples_bp.route("/")
def index():
    return render_template("cv_examples/index.html", examples=data.all_examples(),
                           page_title=INDEX_TITLE, page_description=INDEX_DESCRIPTION,
                           page_keywords=INDEX_KEYWORDS)


@cv_examples_bp.route("/<slug>")
def detail(slug):
    ex = data.get_example(slug)
    if ex is None:
        abort(404)
    base = site_base_url()
    role = ex["role"]
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": base + "/"},
                    {"@type": "ListItem", "position": 2, "name": "CV examples",
                     "item": base + url_for("cv_examples.index")},
                    {"@type": "ListItem", "position": 3, "name": f"{role} CV example",
                     "item": base + url_for("cv_examples.detail", slug=slug)},
                ],
            },
            faq_jsonld(ex["faqs"]),
        ],
    }
    keywords = (f"{role} CV example, {role} resume example, {role} CV sample, "
                f"how to write a {role} CV, {ex['short']} CV template, CV maker")
    return render_template("cv_examples/detail.html", ex=ex, disclaimer=data.DISCLAIMER,
                           related=data.related(slug), jsonld=jsonld,
                           page_title=ex["seo_title"], page_description=ex["seo_desc"],
                           page_keywords=keywords)
