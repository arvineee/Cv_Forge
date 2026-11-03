"""
CVForge AI - Layout templates added after launch.

Seeded by `flask seed-templates`, which adds any slug not already in the
templates table, so it is safe to run on an existing database.
Each slug must have an entry in SLUG_TO_THEME in pdf_service.py.
"""

LAYOUT_TEMPLATES = [
    dict(slug="centred-classic", name="Centred Classic", category="professional",
         description="Centred name with thin rules between sections. Calm and easy to scan.",
         is_premium=False, sort_order=13, accent_color="#1e3a5f", font_style="classic"),
    dict(slug="banded-sections", name="Banded Sections", category="professional",
         description="Filled section headings so each part of your CV is easy to find at a glance.",
         is_premium=False, sort_order=14, accent_color="#1e3a5f", font_style="modern"),
    dict(slug="sidebar-navy", name="Sidebar Navy", category="professional",
         description="Navy side column for contact, education and skills. Two-column design; for online applications, a single-column template is the safer choice.",
         is_premium=False, sort_order=15, accent_color="#1e3a5f", font_style="modern"),
    dict(slug="sidebar-slate", name="Sidebar Slate", category="professional",
         description="Slate side column in the same two-column design. For online applications, a single-column template is the safer choice.",
         is_premium=False, sort_order=16, accent_color="#334155", font_style="modern"),
    dict(slug="header-band-burgundy", name="Header Band Burgundy", category="professional",
         description="Burgundy band across the top with your name and photo, then a single column of experience.",
         is_premium=False, sort_order=17, accent_color="#7f1d1d", font_style="modern"),
    dict(slug="header-band-forest", name="Header Band Forest", category="professional",
         description="Forest green band across the top with your name and photo, then a single column of experience.",
         is_premium=False, sort_order=18, accent_color="#14532d", font_style="modern"),
    dict(slug="timeline-teal", name="Timeline Teal", category="professional",
         description="Experience and education on a vertical timeline, with a teal accent and a single column.",
         is_premium=False, sort_order=19, accent_color="#0f766e", font_style="modern"),
    dict(slug="timeline-indigo", name="Timeline Indigo", category="professional",
         description="The same timeline layout in indigo, for a slightly bolder look.",
         is_premium=False, sort_order=20, accent_color="#4338ca", font_style="modern"),
]
