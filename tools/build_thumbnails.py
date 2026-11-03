"""
Build gallery preview images for every CV template.

Renders each template with a fictional sample CV (no real people, no uploaded
photos), takes the top of page 1, and saves it as a PNG under
app/static/templates/<slug>.png.

Needs poppler's `pdftoppm` on the PATH (apt install poppler-utils, or
brew install poppler). Run from the project root:

    python tools/build_thumbnails.py

Then run `flask set-thumbnails` to link the images to the templates.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "app", "static", "templates")
WIDTH = 480          # px
CROP_FRACTION = 0.55 # top share of the page to keep, so the header and first section show

SAMPLE = {
    "personal_info": {
        "full_name": "Amina W. Otieno", "job_title": "Sales Supervisor",
        "email": "amina@example.com", "phone": "+254 700 000 000",
        "location": "Nairobi, Kenya", "linkedin": "linkedin.com/in/amina-otieno",
    },
    "professional_summary": "Sales supervisor with five years leading retail teams across three branches. "
                            "Grew monthly sales by 32% and cut stock-outs through weekly reorder reviews.",
    "work_experience": [
        {"job_title": "Sales Supervisor", "company": "Example Retail Ltd", "location": "Nairobi",
         "start_date": "Jan 2022", "end_date": "Present",
         "achievements": ["Led a team of 6 across 3 branches", "Grew monthly sales 32% in 8 months",
                          "Cut stock-outs by a quarter with weekly reorder checks"]},
        {"job_title": "Sales Associate", "company": "Sample Stores", "location": "Mombasa",
         "start_date": "Mar 2019", "end_date": "Dec 2021",
         "achievements": ["Handled key accounts worth KES 4M per year", "Trained 8 new staff"]},
    ],
    "education": [{"degree": "BBA Marketing", "institution": "Example University", "year": "2015 - 2019"}],
    "skills": ["Team leadership", "Inventory control", "Customer service", "Sales targets", "POS systems"],
    "languages": ["English (Fluent)", "Swahili (Native)"],
}


def _load_pdf_service():
    spec = importlib.util.spec_from_file_location(
        "pdf_service", os.path.join(ROOT, "app", "services", "pdf_service.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build():
    if not shutil.which("pdftoppm"):
        sys.exit("pdftoppm not found. Install poppler-utils (or brew install poppler).")

    pdf = _load_pdf_service()
    os.makedirs(OUT_DIR, exist_ok=True)
    work = tempfile.mkdtemp()

    built = []
    for slug, theme in sorted(pdf.SLUG_TO_THEME.items()):
        pdf_path = pdf.PDFService(theme=theme).generate_from_dict(SAMPLE)
        shutil.move(pdf_path, os.path.join(work, f"{slug}.pdf"))
        prefix = os.path.join(work, slug)
        subprocess.run(["pdftoppm", "-png", "-r", "110", "-f", "1", "-l", "1", "-singlefile",
                        os.path.join(work, f"{slug}.pdf"), prefix], check=True)

        with Image.open(prefix + ".png") as page:
            page = page.convert("RGB")
            h = int(page.height * CROP_FRACTION)
            top = page.crop((0, 0, page.width, h))
            ratio = WIDTH / top.width
            top = top.resize((WIDTH, int(top.height * ratio)), Image.LANCZOS)
            top.save(os.path.join(OUT_DIR, f"{slug}.png"), "PNG", optimize=True)
        built.append(slug)

    shutil.rmtree(work, ignore_errors=True)
    print(f"Built {len(built)} previews into {OUT_DIR}")
    for slug in built:
        print("  ", slug)


if __name__ == "__main__":
    build()
