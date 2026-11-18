# Merge manifest

Every file from both archives, classified. Base for the three-way merge: commit `1fdbc5a` in `cvforge.zip`'s git history (209 of 219 comparable files in the sprint-008 zip matched it byte-for-byte).

| Result | Meaning | Count |
|---|---|---|
| RESOLVED | conflict, resolved by hand | 5 |
| AUTOMERGE | both sides edited, merged cleanly | 4 |
| TAKE-A | only A changed vs common base → A's version | 38 |
| TAKE-B | only B changed vs common base → B's version | 1 |
| ONLY-A | exists only in cvforge.zip | 24 |
| ONLY-B | exists only in sprint-008 zip | 16 |
| RESTORED | recovered from A git history | 14 |
| NEW | created by merge | 6 |
| DROPPED | intentionally left out | 8 |
| SAME | identical in both zips | 171 |
| **Total** | | **287** |

## RESOLVED (5)

| File | Note |
|---|---|
| `README.md` | hand-merged (see MERGE_NOTES) |
| `app/cli.py` | both command sets kept |
| `app/routes/cv.py` | A conversion tracking + B dashboard milestones, both kept |
| `app/routes/dashboard.py` | A onboarding + B career/job/alert routes, imports unioned |
| `app/templates/dashboard/index.html` | A hero/drafts banner + B checklist |

## AUTOMERGE (4)

| File | Note |
|---|---|
| `.env.example` |  |
| `FOUNDER_EXECUTION_AUDIT.md` |  |
| `app/models.py` |  |
| `config.py` |  |

## TAKE-A (38)

| File | Note |
|---|---|
| `.github/workflows/deploy.yml` | B unchanged vs base |
| `.gitignore` | B unchanged vs base |
| `app/__init__.py` | B unchanged vs base |
| `app/routes/admin.py` | B unchanged vs base |
| `app/routes/ats.py` | B unchanged vs base |
| `app/routes/auth.py` | B unchanged vs base |
| `app/routes/billing.py` | B unchanged vs base |
| `app/routes/cover_letter.py` | B unchanged vs base |
| `app/routes/webhooks.py` | B unchanged vs base |
| `app/services/email_service.py` | B unchanged vs base |
| `app/services/intasend_service.py` | B unchanged vs base |
| `app/services/nudge_service.py` | B unchanged vs base |
| `app/services/visitor_tracking.py` | B unchanged vs base |
| `app/templates/admin/broadcast.html` | B unchanged vs base |
| `app/templates/admin/growth.html` | B unchanged vs base |
| `app/templates/admin/index.html` | B unchanged vs base |
| `app/templates/admin/nudges.html` | B unchanged vs base |
| `app/templates/admin/payments.html` | B unchanged vs base |
| `app/templates/base.html` | B unchanged vs base |
| `app/templates/billing/index.html` | B unchanged vs base |
| `app/templates/cv/_template_picker.html` | B unchanged vs base |
| `app/templates/cv/_wizard_base.html` | B unchanged vs base |
| `app/templates/cv/builder.html` | B unchanged vs base |
| `app/templates/cv/list.html` | B unchanged vs base |
| `app/templates/cv/revamp.html` | B unchanged vs base |
| `app/templates/cv/wizard_personal_info.html` | B unchanged vs base |
| `app/templates/dashboard/profile.html` | B unchanged vs base |
| `app/templates/privacy.html` | B unchanged vs base |
| `app/templates/templates_gallery/_grid.html` | B unchanged vs base |
| `requirements.txt` | B unchanged vs base |
| `scripts/pa_deploy.py` | B unchanged vs base |
| `tests/test_admin_features.py` | B unchanged vs base |
| `tests/test_app_smoke.py` | B unchanged vs base |
| `tests/test_cv_examples.py` | B unchanged vs base |
| `tests/test_free_ats_page.py` | B unchanged vs base |
| `tests/test_international.py` | B unchanged vs base |
| `tests/test_offers_app.py` | B unchanged vs base |
| `tests/test_review_fixes.py` | B unchanged vs base |

## TAKE-B (1)

| File | Note |
|---|---|
| `app/templates/base_dashboard.html` | A unchanged vs base |

## ONLY-A (24)

| File | Note |
|---|---|
| `app/services/acquisition_tracking.py` |  |
| `app/services/conversion_tracking.py` |  |
| `app/services/entitlements.py` |  |
| `app/services/growth_analytics.py` |  |
| `app/services/payment_integrity.py` |  |
| `app/services/unit_economics.py` |  |
| `app/templates/admin/conversion.html` |  |
| `app/templates/admin/unit_economics.html` |  |
| `app/templates/dashboard/onboarding.html` |  |
| `cvforge-scheduler/README.md` |  |
| `cvforge-scheduler/cvforge-cv-reminders.service` |  |
| `cvforge-scheduler/cvforge-cv-reminders.timer` |  |
| `cvforge-scheduler/cvforge-nudges.service` |  |
| `cvforge-scheduler/cvforge-nudges.timer` |  |
| `cvforge-scheduler/cvforge-prune-visits.service` |  |
| `cvforge-scheduler/cvforge-prune-visits.timer` |  |
| `cvforge-scheduler/install.sh` |  |
| `tests/test_config_defaults.py` |  |
| `tests/test_deploy_protection.py` |  |
| `tests/test_sprint003_conversion.py` |  |
| `tests/test_sprint005_payment_app.py` |  |
| `tests/test_sprint005_payment_integrity.py` |  |
| `tests/test_sprint006_growth.py` |  |
| `tests/test_sprint007_unit_economics.py` |  |

## ONLY-B (16)

| File | Note |
|---|---|
| `JOB_DISCOVERY_SETUP.md` |  |
| `SPRINT_005_CAREER_WORKSPACE.md` |  |
| `SPRINT_008_JOB_ALERTS.md` |  |
| `VPS_DEPLOYMENT.md` |  |
| `app/services/job_alerts.py` |  |
| `app/services/job_discovery.py` |  |
| `app/templates/career/applications.html` |  |
| `app/templates/career/job_alerts.html` |  |
| `app/templates/career/jobs.html` |  |
| `app/templates/career/match.html` |  |
| `migrations_manual/001_create_job_applications.sql` |  |
| `migrations_manual/001_create_job_applications_sqlite.sql` |  |
| `migrations_manual/002_create_job_opportunities_postgresql.sql` |  |
| `migrations_manual/002_create_job_opportunities_sqlite.sql` |  |
| `migrations_manual/003_create_job_alerts_postgresql.sql` |  |
| `migrations_manual/003_create_job_alerts_sqlite.sql` |  |

## RESTORED (14)

| File | Note |
|---|---|
| `CVFORGE_SPRINT_004_ARCHITECTURE_AUDIT.md` | deleted from A working tree but present in A git HEAD |
| `CVFORGE_SPRINT_005_AUDIT.md` | deleted from A working tree but present in A git HEAD |
| `CVFORGE_SPRINT_006_GROWTH_AUDIT.md` | deleted from A working tree but present in A git HEAD |
| `CVFORGE_SPRINT_007_UNIT_ECONOMICS_AUDIT.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_003_ADMIN_DASHBOARD_UPDATE.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_003_CHANGELOG.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_003_DEPLOYMENT.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_004_CHANGELOG.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_005_CHANGELOG.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_005_DEPLOYMENT.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_006_CHANGELOG.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_006_DEPLOYMENT.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_007_CHANGELOG.md` | deleted from A working tree but present in A git HEAD |
| `SPRINT_007_DEPLOYMENT.md` | deleted from A working tree but present in A git HEAD |

## NEW (6)

| File | Note |
|---|---|
| `MERGE_MANIFEST.md` | added by the merge |
| `MERGE_NOTES.md` | added by the merge |
| `cvforge-scheduler/cvforge-job-alerts.service` | added by the merge |
| `cvforge-scheduler/cvforge-job-alerts.timer` | added by the merge |
| `cvforge-scheduler/cvforge-job-feeds.service` | added by the merge |
| `cvforge-scheduler/cvforge-job-feeds.timer` | added by the merge |

## DROPPED (8)

| File | Note |
|---|---|
| `.env` | secrets file (credentials) – never ship |
| `.mannual.diff.swp` | editor swap file |
| `app/models.py.bak` | backup file (already removed in B) |
| `app/routes/dashboard.py.bak` | backup file |
| `app/services/growth_analytics.py.bak` | backup file |
| `app/services/visitor_tracking.py.bak` | backup file |
| `instance/cvforge.db` | local SQLite database (user data) – never ship |
| `patch.py` | one-off CI patch script; its fixes are already in A's patched sources |

## SAME (171 files)
Identical in both archives; listed in full below.

| File | Note |
|---|---|
| `OPTIMIZATION_DEPLOYMENT.md` |  |
| `PAYSTACK_SETUP.md` |  |
| `app/ai_service.py` |  |
| `app/routes/__init__.py` |  |
| `app/routes/api.py` |  |
| `app/routes/cv_examples.py` |  |
| `app/routes/feedback.py` |  |
| `app/routes/free_ats.py` |  |
| `app/routes/guide.py` |  |
| `app/routes/main.py` |  |
| `app/routes/seo.py` |  |
| `app/routes/support.py` |  |
| `app/routes/templates_gallery.py` |  |
| `app/services/__init__.py` |  |
| `app/services/ats_lite.py` |  |
| `app/services/cv_diff.py` |  |
| `app/services/cv_examples.py` |  |
| `app/services/cv_parser.py` |  |
| `app/services/cv_preview.py` |  |
| `app/services/docx_service.py` |  |
| `app/services/manual_content.py` |  |
| `app/services/manual_mailing.py` |  |
| `app/services/manual_pdf.py` |  |
| `app/services/payment_settings.py` |  |
| `app/services/paystack_service.py` |  |
| `app/services/pdf_service.py` |  |
| `app/services/photo_service.py` |  |
| `app/services/pricing.py` |  |
| `app/services/section_intelligence.py` |  |
| `app/services/site_content.py` |  |
| `app/services/storage.py` |  |
| `app/services/template_catalog.py` |  |
| `app/services/upload_validation.py` |  |
| `app/static/apple-touch-icon.png` |  |
| `app/static/css/tw.css` |  |
| `app/static/favicon.ico` |  |
| `app/static/icon-192.png` |  |
| `app/static/icon-512.png` |  |
| `app/static/js/progress.js` |  |
| `app/static/logo-full.png` |  |
| `app/static/logo-full.webp` |  |
| `app/static/logo-nav.png` |  |
| `app/static/logo-nav.webp` |  |
| `app/static/logo.png` |  |
| `app/static/og-default.jpg` |  |
| `app/static/templates/banded-sections.png` |  |
| `app/static/templates/banded-sections.webp` |  |
| `app/static/templates/centred-classic.png` |  |
| `app/static/templates/centred-classic.webp` |  |
| `app/static/templates/classic-navy.png` |  |
| `app/static/templates/classic-navy.webp` |  |
| `app/static/templates/clean-white.png` |  |
| `app/static/templates/clean-white.webp` |  |
| `app/static/templates/creative-teal.png` |  |
| `app/static/templates/creative-teal.webp` |  |
| `app/static/templates/emerald-fresh.png` |  |
| `app/static/templates/emerald-fresh.webp` |  |
| `app/static/templates/executive-black.png` |  |
| `app/static/templates/executive-black.webp` |  |
| `app/static/templates/header-band-burgundy.png` |  |
| `app/static/templates/header-band-burgundy.webp` |  |
| `app/static/templates/header-band-forest.png` |  |
| `app/static/templates/header-band-forest.webp` |  |
| `app/static/templates/minimal-gray.png` |  |
| `app/static/templates/minimal-gray.webp` |  |
| `app/static/templates/modern-blue.png` |  |
| `app/static/templates/modern-blue.webp` |  |
| `app/static/templates/purple-bold.png` |  |
| `app/static/templates/purple-bold.webp` |  |
| `app/static/templates/rose-modern.png` |  |
| `app/static/templates/rose-modern.webp` |  |
| `app/static/templates/sidebar-navy.png` |  |
| `app/static/templates/sidebar-navy.webp` |  |
| `app/static/templates/sidebar-slate.png` |  |
| `app/static/templates/sidebar-slate.webp` |  |
| `app/static/templates/tech-dark.png` |  |
| `app/static/templates/tech-dark.webp` |  |
| `app/static/templates/timeline-indigo.png` |  |
| `app/static/templates/timeline-indigo.webp` |  |
| `app/static/templates/timeline-teal.png` |  |
| `app/static/templates/timeline-teal.webp` |  |
| `app/static/templates/two-column-pro.png` |  |
| `app/static/templates/two-column-pro.webp` |  |
| `app/static/templates/warm-terracotta.png` |  |
| `app/static/templates/warm-terracotta.webp` |  |
| `app/templates/_offer_banner.html` |  |
| `app/templates/_payment_methods.html` |  |
| `app/templates/_progress.html` |  |
| `app/templates/about.html` |  |
| `app/templates/admin/claims.html` |  |
| `app/templates/admin/feedback.html` |  |
| `app/templates/admin/manual_plan.html` |  |
| `app/templates/admin/offer_form.html` |  |
| `app/templates/admin/offers.html` |  |
| `app/templates/admin/payment_methods.html` |  |
| `app/templates/admin/pricing.html` |  |
| `app/templates/admin/pricing_form.html` |  |
| `app/templates/admin/template_form.html` |  |
| `app/templates/admin/templates.html` |  |
| `app/templates/admin/users.html` |  |
| `app/templates/admin/visitors.html` |  |
| `app/templates/ats/_report_partial.html` |  |
| `app/templates/ats/index.html` |  |
| `app/templates/ats/report.html` |  |
| `app/templates/auth/forgot_password.html` |  |
| `app/templates/auth/login.html` |  |
| `app/templates/auth/register.html` |  |
| `app/templates/auth/resend_verification.html` |  |
| `app/templates/auth/reset_password.html` |  |
| `app/templates/billing/payments.html` |  |
| `app/templates/billing/plans.html` |  |
| `app/templates/billing/success.html` |  |
| `app/templates/cover_letter/list.html` |  |
| `app/templates/cover_letter/new.html` |  |
| `app/templates/cover_letter/view.html` |  |
| `app/templates/cv/fill_gaps.html` |  |
| `app/templates/cv/new.html` |  |
| `app/templates/cv/public.html` |  |
| `app/templates/cv/start.html` |  |
| `app/templates/cv/upload.html` |  |
| `app/templates/cv/versions.html` |  |
| `app/templates/cv/wizard_awards.html` |  |
| `app/templates/cv/wizard_certifications.html` |  |
| `app/templates/cv/wizard_education.html` |  |
| `app/templates/cv/wizard_languages.html` |  |
| `app/templates/cv/wizard_professional_summary.html` |  |
| `app/templates/cv/wizard_projects.html` |  |
| `app/templates/cv/wizard_references.html` |  |
| `app/templates/cv/wizard_review.html` |  |
| `app/templates/cv/wizard_skills.html` |  |
| `app/templates/cv/wizard_work_experience.html` |  |
| `app/templates/cv_examples/_footer.html` |  |
| `app/templates/cv_examples/_header.html` |  |
| `app/templates/cv_examples/detail.html` |  |
| `app/templates/cv_examples/index.html` |  |
| `app/templates/errors/403.html` |  |
| `app/templates/errors/404.html` |  |
| `app/templates/errors/500.html` |  |
| `app/templates/feedback/_form.html` |  |
| `app/templates/feedback/dashboard.html` |  |
| `app/templates/feedback/public.html` |  |
| `app/templates/free_ats/page.html` |  |
| `app/templates/guide/_prompt.html` |  |
| `app/templates/guide/index.html` |  |
| `app/templates/landing.html` |  |
| `app/templates/pricing.html` |  |
| `app/templates/support/index.html` |  |
| `app/templates/templates_gallery/index.html` |  |
| `app/templates/templates_gallery/public.html` |  |
| `app/templates/terms.html` |  |
| `requirements-dev.txt` |  |
| `run.py` |  |
| `tailwind.config.js` |  |
| `tailwind.input.css` |  |
| `tests/__init__.py` |  |
| `tests/_load.py` |  |
| `tests/test_ats_lite.py` |  |
| `tests/test_cv_diff.py` |  |
| `tests/test_docx_layouts.py` |  |
| `tests/test_layout_templates.py` |  |
| `tests/test_manual.py` |  |
| `tests/test_offers_logic.py` |  |
| `tests/test_payment_settings.py` |  |
| `tests/test_photo_service.py` |  |
| `tests/test_progress_browser.py` |  |
| `tests/test_revamp_validation.py` |  |
| `tests/test_seo_keywords.py` |  |
| `tests/test_templates.py` |  |
| `tests/test_upload_validation.py` |  |
| `tools/build_icons.py` |  |
| `tools/build_thumbnails.py` |  |
