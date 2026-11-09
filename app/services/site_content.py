"""CVForge AI - Public marketing copy shared by page templates and structured data.

Keeping the FAQ text in one place means the visible FAQ on a page and its
FAQPage JSON-LD can never drift apart, which search engines treat as a
mismatch.

Wording rules for this file:
  * Prices are charged in KES. Do not describe multi-currency pricing.
  * Card payments go through Paystack, M-Pesa is for customers in Kenya.
  * No guarantees about interviews, jobs or passing screening software.
"""

SITE_NAME = "CVForge AI"

HOME_TITLE = "CVForge: Online CV Builder, Resume Maker & CV Generator"
HOME_DESCRIPTION = (
    "Start free: an online CV creator and resume maker with AI. Build an ATS-friendly CV, improve an old resume, write cover letters, download PDF or Word."
)
# The 9 original phrases come first and must stay (tests pin them). The rest cover the
# other names people search for. Search engines mostly ignore the keywords tag, so the
# real ranking work is done by the title, description, headings, FAQ and body copy.
SEO_KEYWORDS = (
    "online CV builder, ATS-friendly resume builder, professional resume builder, "
    "CV builder online, resume creator, cover letter generator, AI CV builder, "
    "resume optimisation tool, CV writing tool, "
    "CV maker, CV creator, CV generator, resume maker, resume generator, "
    "resume builder online, online resume maker, online CV maker, CV maker online, "
    "AI resume builder, AI CV generator, AI resume generator, professional CV maker, "
    "curriculum vitae maker, create a CV online, make a CV online, make a resume online, "
    "ATS resume checker, ATS-friendly CV template, CV templates, resume templates, "
    "cover letter maker, CV maker Kenya, CV builder Kenya"
)

# Keywords for specific pages (used by the pages' own meta_keywords block).
TEMPLATES_KEYWORDS = (
    "CV templates, resume templates, ATS-friendly CV templates, professional CV templates, "
    "modern resume templates, simple CV templates, CV template PDF, CV template Word, "
    "resume template download, CV maker, resume maker"
)
PRICING_KEYWORDS = (
    "CV maker pricing, resume builder pricing, CV builder plans, resume maker plans, "
    "pay for CV builder with M-Pesa, CV builder card payment, CV maker KES, "
    "online CV builder, resume generator"
)
REGISTER_KEYWORDS = (
    "free CV maker, free resume builder account, create a CV online, make a resume online, "
    "start free CV builder, CV creator, resume maker"
)
GUIDE_KEYWORDS = (
    "how to make a CV, how to write a CV, how to make a resume online, CV writing guide, "
    "CV maker guide, resume builder tutorial, CV generator, resume maker"
)

PAYMENT_CARD_NOTE = (
    "Card payments are charged in Kenyan shillings (KES). If your card is in another "
    "currency, your bank or card issuer converts the amount and may add its own fees. "
    "Whether a card works for online payments abroad is decided by its issuer."
)

LANDING_FAQS = [
    (
        "What can CVForge do for me?",
        "CVForge helps you create a professional CV or resume from scratch, or improve one you "
        "already have. It rewrites weak wording, compares your document with a job description, "
        "flags missing keywords and writes a cover letter for a specific role.",
    ),
    (
        "Is this a CV builder or a resume builder?",
        "Both. The two words are used differently around the world: \"resume\" is the usual term in "
        "the USA and Canada, while \"CV\" is common in the UK, Australia, South Africa and much of "
        "Europe. Whether you call it a CV maker, CV creator, resume maker or resume generator, "
        "CVForge builds a clean, professional document you can use for either. Always check "
        "each employer's instructions for things like length or whether to include a photo.",
    ),
    (
        "Is there a free CV maker or resume creator online?",
        "You can start free. Create an account, build your CV with the guided builder and preview it "
        "at no cost. A paid plan is only needed for the clean PDF download, Word (DOCX) on eligible "
        "plans and more of the AI tools. Current plans are on the pricing page.",
    ),
    (
        "Can AI generate my CV or resume for me?",
        "CVForge works as an AI CV generator and resume generator. It drafts your summary, experience "
        "bullets and a cover letter from the details you enter. It uses only the facts you provide and "
        "does not invent jobs or qualifications, so review and edit every line before you send it.",
    ),
    (
        "Does CVForge have CV and resume templates?",
        "Yes. There are 20 professional CV and resume templates. Preview them, choose one for your "
        "details and switch designs at any time without retyping. You can browse them on the "
        "Templates page.",
    ),
    (
        "Do I need to pay to try it?",
        "No. You can create an account, build a CV and preview it for free. A paid plan unlocks the "
        "clean PDF download and more of the AI tools, and Word (DOCX) downloads are included on "
        "eligible plans. Current prices are on the pricing page.",
    ),
    (
        "Which payment methods do you accept, and can I pay from outside Kenya?",
        "You can pay with a debit or credit card through Paystack, or with M-Pesa if you are in Kenya. "
        "Card payments are available to customers outside Kenya, as long as your card issuer allows "
        "international online payments. " + PAYMENT_CARD_NOTE,
    ),
    (
        "Is my card information safe?",
        "You enter card details on Paystack's secure hosted checkout page, not on CVForge, so we never "
        "see or store your full card number. We keep the payment reference, amount and status so you "
        "can see your billing history.",
    ),
    (
        "Will my CV pass screening software (ATS)?",
        "No tool can promise that. CVForge uses clean, readable layouts and shows how your "
        "wording matches the job posting, so you can fix gaps before you apply.",
    ),
    (
        "Can I improve a CV or resume I already have?",
        "Yes. Upload a PDF or DOCX file and CVForge reads it so you can edit it, or let the AI rewrite "
        "your summary and experience bullets. It works from the facts in your document and does not "
        "invent jobs or qualifications.",
    ),
    (
        "How does job description matching work?",
        "Paste a job posting into the ATS checker. CVForge compares it with your CV, shows which keywords "
        "you already cover and which are missing, and suggests what to change. Only add skills you "
        "genuinely have.",
    ),
    (
        "Which file formats can I download?",
        "PDF for sending to employers, and Word (DOCX) on eligible plans if you want to keep editing. "
        "PDFs are A4, the standard size in the UK, Europe, Australia and South Africa. US Letter is "
        "not available yet.",
    ),
    (
        "Do plans renew automatically?",
        "No. Each plan lasts for the period shown on its card and does not renew automatically. "
        "You choose whether to buy another period when it ends.",
    ),
    (
        "How is my data handled?",
        "We do not sell your data and we do not use your CV content to train AI models. AI features "
        "send the relevant text to Google's Gemini API to generate a response. The Privacy Policy "
        "explains this in full.",
    ),
]

PRICING_FAQS = [
    (
        "How does payment work?",
        "Choose a plan and click Subscribe, then pick a payment method. With a debit or credit card you "
        "are taken to Paystack's secure checkout page. With M-Pesa (Kenya), enter your Safaricom number "
        "and approve the prompt on your phone. Your plan activates once the payment is confirmed.",
    ),
    (
        "Can I pay with an international card?",
        "Yes. Debit and credit card payments are processed by Paystack and are open to customers outside "
        "Kenya, provided your card issuer allows international online payments. M-Pesa is only for "
        "customers in Kenya.",
    ),
    (
        "Which currency am I charged in?",
        "Prices and charges are in Kenyan shillings (KES). CVForge does not show prices in other "
        "currencies. If your card is in another currency, your bank or card issuer converts the amount "
        "and may add its own fees.",
    ),
    (
        "Will my plan renew automatically?",
        "No. Each plan lasts for the period shown on its card and does not renew automatically.",
    ),
    (
        "What is the difference between the plans?",
        "The comparison table on this page lists the daily limits and features for each plan, including "
        "Word (DOCX) downloads, version history and the AI Career Coach where they are included.",
    ),
    (
        "Is my CV data secure?",
        "We do not sell your data or use your CV content to train AI models. Card details are entered on "
        "Paystack's checkout page and are never stored by CVForge. AI features send the relevant text to "
        "Google's Gemini API to generate a response; see the Privacy Policy for details.",
    ),
]


def faq_jsonld(faqs):
    """schema.org FAQPage node built from the same pairs the page displays."""
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faqs
        ],
    }


def landing_jsonld(base_url, plans, pricing_url, logo_url):
    """JSON-LD graph for the home page: organisation, website, web app, FAQ."""
    base = base_url.rstrip("/")
    graph = [
        {
            "@type": "WebSite",
            "@id": f"{base}/#website",
            "url": f"{base}/",
            "name": SITE_NAME,
            "inLanguage": "en",
            "alternateName": ["CVForge", "CVForge CV Maker", "CVForge Resume Builder"],
            "description": HOME_DESCRIPTION,
        },
        {
            "@type": "WebApplication",
            "@id": f"{base}/#app",
            "name": SITE_NAME,
            "url": f"{base}/",
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Any (web browser)",
            "browserRequirements": "Requires JavaScript",
            "description": HOME_DESCRIPTION,
            "alternateName": ["CVForge CV Maker", "CVForge Resume Maker", "CVForge CV Generator"],
            "keywords": SEO_KEYWORDS,
            "featureList": [
                "Professional CV and resume builder",
                "ATS-friendly CV and resume optimisation",
                "Resume improvement and rewriting",
                "Job description matching",
                "Cover letter generator",
                "PDF and Word (DOCX) downloads",
                "CV maker and CV creator",
                "Resume maker and resume generator",
                "AI CV generator",
                "CV and resume templates",
            ],
            "publisher": {"@id": f"{base}/#organization"},
        },
        faq_jsonld(LANDING_FAQS),
    ]

    prices = [int(p.display_price) for p in plans if getattr(p, "display_price", None) is not None]
    if prices:
        graph[1]["offers"] = {
            "@type": "AggregateOffer",
            "priceCurrency": "KES",
            "lowPrice": min(prices),
            "highPrice": max(prices),
            "offerCount": len(prices),
            "url": pricing_url,
        }

    return {"@context": "https://schema.org", "@graph": graph}
