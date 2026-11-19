CVForge Public Job Discovery Patch
==================================

Purpose
-------
Make /career/jobs publicly accessible, while keeping account actions protected.
Adds public, crawlable job detail pages and includes active job URLs in the sitemap.

Files
-----
- app/routes/dashboard.py
- app/routes/seo.py
- app/templates/career/jobs.html
- app/templates/career/job_detail.html (new)

What changes
------------
1. Visitors can browse and search active vacancies without signing in.
2. Job detail pages are public at /career/jobs/<job_id>.
3. Saving a vacancy and matching a CV still require login.
4. Career workspace, job alerts, and job matching remain behind login.
5. Public jobs index with canonical URLs, descriptive metadata, and page-level
   WebPage structured data.
6. Search/filter result URLs are noindex and canonicalise to the main jobs page.
7. Active public job detail URLs are added to /sitemap.xml.
8. Private career workspace/action paths remain disallowed in robots.txt.

Deployment (safe overlay)
-------------------------
1. Make a backup of the live project and database first.
2. Extract this ZIP into the existing Flask project root, preserving folders.
   Allow it to overwrite the three existing files and add the new template.
3. Do NOT replace instance/cvforge.db, .env, uploads, or any user data.
4. Restart/reload the Flask web application.
5. Verify while logged out:
   - https://cvforge.site/career/jobs
   - Open one job detail link
   - https://cvforge.site/robots.txt
   - https://cvforge.site/sitemap.xml
6. Verify saving and CV matching redirect unauthenticated users to login.
7. Verify a signed-in user can still save and match jobs.

No database migration is required. The patch does not include a database,
environment file, Git history, uploads, or dependencies.

SEO note
--------
The job source model does not currently store a vacancy closing/expiry date.
Therefore this patch intentionally does not emit Google JobPosting rich-result
markup with a fabricated validThrough date. It emits truthful WebPage metadata.
Adding full JobPosting rich-result eligibility requires capturing a genuine
closing date (or an explicit source-provided expiry) and expiring stale jobs.
