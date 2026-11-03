# Layout templates: single-column family

## What's new
- **Centred Classic** (`centred-classic`): centred name and contact line, thin
  rules between sections.
- **Banded Sections** (`banded-sections`): left-aligned name, filled section
  headings for quick scanning.
- Both are single-column, text-based layouts. There are no photos, sidebars or
  tables for the main content, so screening software can read them.
- Existing templates are unchanged.

## Deploying
    flask seed-templates      # adds the two new templates only; safe to re-run

No database schema change.

## Tests
- `tests/test_layout_templates.py` (6 tests): both new layouts and the existing
  one render normal, long (multi-page), sparse and empty CVs.
  Catalogue slugs map to real layouts.

## Not yet done
- **Word (DOCX) output** uses one layout for every template, as before. The new
  layouts only apply to PDF.
- **Gallery thumbnails**: the new templates have no preview image yet. Render
  one from a sample CV and upload it as the template's thumbnail.
- **Sidebar, header-band and timeline families** are not built yet. These come
  next, and they need photo upload.

## Sidebar family (added in this round)
- **Sidebar Navy** and **Sidebar Slate** (`sidebar-navy`, `sidebar-slate`):
  coloured left column with contact, education, and skills. Experience and the
  rest of the CV sit in the right column. Later pages use the right column only.
- If skills or languages won't fit in the sidebar, they move to the main column
  in normal styling, so the sidebar never overflows.
- Two-column layouts can be read less reliably by some applicant tracking
  systems. The template descriptions say so, and the single-column templates
  stay the recommended choice for online applications.
- Photo upload is not included. The sidebar has no photo slot yet.

## Tests
- `tests/test_layout_templates.py` now covers all five layouts, plus a
  60-skills overflow case and an unbroken long URL.

## Deploy
    flask seed-templates      # adds any missing templates; safe to re-run

## Profile photo (added in this round)
- **Upload** on the builder's personal-info step. Requires a consent tick.
  Accepts JPEG or PNG up to 5 MB.
- **Processing:** the file's real format is checked (not just its extension).
  The photo is cropped to a square, resized to 400 px, and re-saved as JPEG.
  That strips metadata, including GPS location. Stored under a random name.
- **Removal:** "Remove photo" in the builder, and automatic deletion when the
  CV is deleted.
- **Where it shows:** the PDF sidebar templates (Sidebar Navy and Sidebar
  Slate), as a circle at the top of the sidebar. The photo is used only when
  consent is recorded and the file exists.
- **Not shown:** other layouts, and the DOCX output.
- **Storage:** the photo path and consent are stored in the resume's existing
  personal-info JSON. No database schema change.

## Privacy checklist before launch
- Update the privacy policy to cover profile photos: what is collected, why,
  how long it is kept, and how to delete it.
- Photos are stored on the server's disk, without encryption at rest. Confirm
  this meets your data-protection obligations, and check whether a data
  protection officer is required.
- Deleting a user account does not yet delete their photo files. Add that to
  the account-deletion flow.

## Tests
- `tests/test_photo_service.py` (13 tests): valid JPEG and PNG, square crop,
  metadata stripping, rejection of non-images, GIFs, empty, oversize and huge
  images, path-traversal protection, transparent circle mask, and PDFs with
  and without a photo.
- The upload and remove routes need Flask and a database to test, so they are
  not covered by automated tests. Test them manually in the sandbox first.

## Deploy
    mkdir -p <UPLOAD_FOLDER>/photos    # created automatically on first upload

## Header-band family (added in this round)
- **Header Band Burgundy** (`header-band-burgundy`) and **Header Band Forest**
  (`header-band-forest`): a full-width coloured band across the top with the
  name, title, and contact details in white. The profile photo, if uploaded,
  sits in the band beside the name. The rest of the CV is a single column, so
  these are easier for screening software to read than the sidebar layouts.
- Photos are used only with recorded consent, as in the sidebar templates.

## Deploy
    flask seed-templates      # adds the two new templates; safe to re-run

## Timeline family (added in this round)
- **Timeline Teal** (`timeline-teal`) and **Timeline Indigo** (`timeline-indigo`):
  experience and education sit on a vertical line, with a dot at the start of
  each entry. The line runs continuously, including across page breaks.
- Single column with a plain header, so the layout reads cleanly for screening
  software.
- The experience and education content is the same as the other layouts.
  Photos are not shown on timeline layouts yet.

## Deploy
    flask seed-templates      # adds the two new templates; safe to re-run

## Gallery previews (added in this round)
- Every template has a preview image in `app/static/templates/<slug>.png`,
  made from a fictional sample CV. No real people or uploaded photos are used.
- The gallery shows the top of each CV's first page. Templates without an image
  still show the old colour swatch.
- `tools/build_thumbnails.py` regenerates the images. It needs `pdftoppm`
  (poppler-utils). Run it after any template design change.
- `flask set-thumbnails` links the images to the templates. `db-init` runs it.
- A test fails if any template has no preview image.

## Deploy
    flask seed-templates      # adds any new templates
    flask set-thumbnails      # links preview images to templates

## Word (DOCX) output (added in this round)
- Word files now follow the template: accent colour, and the same layout
  families as the PDFs. Header band, sidebar (two-column table), timeline
  (coloured rules and dots), plain header, and filled or ruled section headings.
- Profile photos appear in the sidebar and header-band layouts, with the same
  consent rules as the PDFs.
- Existing downloads for the default template look the same, except section
  rules now use the accent colour.
- Timeline bullets are rebuilt as plain paragraphs with typed bullets. Word's
  built-in list numbering doesn't reliably carry the timeline rule and indent.
- Checked by rendering the Word files through LibreOffice and inspecting them.
  Word itself has not been used to open them yet. Please open a sample in Word.
- `tests/test_docx_layouts.py` (9 tests), including a LibreOffice conversion
  check that is skipped when soffice isn't installed.

## App-level tests (added in this round, not yet run)
- `tests/test_offers_app.py` (10 tests): pricing page with live, voided,
  expired, and sold-out offers, server-side checkout price, and feedback form
  (valid, honeypot, short message). These use the real database, so they run in
  CI with the full requirements. They were written without Flask or SQLAlchemy
  available, so they have never been executed. Fix any failures before relying
  on them.

## Progress bars for slow operations (added in this round)
- A progress overlay appears while the server works. It covers:
  - AI revamp, AI enhance buttons in the wizard, and builder AI assist
  - CV upload parsing, cover-letter generation, and ATS checks
  - Support chat answers
  - PDF and cover-letter downloads (the bar hides itself after a few seconds)
- The bar is estimated from elapsed time, because the server doesn't report
  progress. It rises quickly, slows near 92%, and jumps to 100% on completion.
  The estimates are guesses. Tune the `data-estimate` values after measuring
  real response times.
- Files: `app/static/js/progress.js`, `app/templates/_progress.html` (included
  once in `base.html`), and `data-progress` / `data-estimate` attributes on the
  triggering forms, buttons, and links.
- Tests: `tests/test_progress_browser.py` (8 tests) runs the real overlay in
  headless Chromium. It needs Playwright, and is skipped when that isn't
  installed. The browser tests passed here. The Tailwind styling wasn't checked,
  because this environment has no internet access.

## Deploy
    python -m playwright install chromium   # only if you want the browser tests to run
