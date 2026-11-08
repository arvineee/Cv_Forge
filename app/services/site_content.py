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

HOME_TITLE = "CVForge: Online CV Builder & ATS-Friendly Resume Maker"
HOME_DESCRIPTION = (
    "Build a professional, ATS-friendly CV or resume online. Improve an existing "
    "CV, match it to a job description, write a cover letter and download PDF or Word."
)
SEO_KEYWORDS = (
    "online CV builder, ATS-friendly resume builder, professional resume builder, "
    "CV builder online, resume creator, cover letter generator, AI CV builder, "
    "resume optimisation tool, CV writing tool"
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
        "Europe. CVForge builds a clean, professional document you can use for either. Always check "
        "each employer's instructions for things like length or whether to include a photo.",
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
            "featureList": [
                "Professional CV and resume builder",
                "ATS-friendly CV and resume optimisation",
                "Resume improvement and rewriting",
                "Job description matching",
                "Cover letter generator",
                "PDF and Word (DOCX) downloads",
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
