"""
CVForge AI - User manual content.

Single source of truth for the manual. The same content feeds the /guide web
page and the branded PDF download (manual_pdf.py), so the two never disagree.
To change the manual, edit this file only.

Block types:
    ("p", "text")                 paragraph
    ("h3", "text")                sub-heading
    ("ul", ["item", ...])         bullet list
    ("ol", ["item", ...])         numbered list
    ("table", [header...], [[cell...], ...])
Inline **bold** is supported in text.
"""

MANUAL_TITLE = "CVForge AI User Manual"
MANUAL_TAGLINE = "Build a job-winning CV in minutes"
MANUAL_UPDATED = "2026-11-03"  # ISO date; bump when the content changes (used for SEO dateModified)

SECTIONS = [
    {
        "title": "Welcome",
        "blocks": [
            ("p", "CVForge AI helps you build a professional CV in about 15 minutes, with AI doing the hard "
                  "writing for you. You can build and preview your CV for free; you pay only when you download it."),
            ("h3", "What you can do"),
            ("ul", [
                "**Build a CV from scratch** with a guided, step-by-step wizard and an \"Enhance with AI\" button.",
                "**Upload an old CV** (PDF or Word) and let AI rewrite it to be stronger.",
                "**Pick a template**, including a two-column sidebar design with an optional profile photo.",
                "**Check your CV with the ATS checker.** ATS means Applicant Tracking System, the software many "
                "employers use to screen CVs.",
                "**Write a cover letter** that matches your CV.",
                "**Download** your CV as a PDF, or as a Word file on plans that include it.",
            ]),
            ("h3", "Cost in one minute"),
            ("ul", [
                "Building, AI writing help and ATS checks are free to use. Free accounts get a limited number of "
                "AI uses per day for each feature (currently 3).",
                "To download the PDF or Word file you need an active paid plan. The Plans page shows current "
                "prices and what each plan includes.",
                "Before you pay, you see a preview of your own CV with the text blurred, so you know what you "
                "are buying.",
            ]),
        ],
    },
    {
        "title": "Getting started",
        "blocks": [
            ("p", "You can be signed in within two minutes, either with an email address or with your Google account."),
            ("h3", "Sign up with email"),
            ("ol", [
                "Open the site and choose **Register**.",
                "Enter your name, email address and a password, then submit.",
                "Open the verification email we send you and tap the link inside.",
                "Return to the site and **Log in**.",
            ]),
            ("p", "You cannot log in until your email is verified. If the email has not arrived after a few "
                  "minutes, check your spam folder. Then use **Resend verification** on the login page."),
            ("h3", "Sign up with Google"),
            ("p", "Choose the Google button on the login or register page. Google accounts are already verified, "
                  "so you go straight in."),
            ("h3", "Forgot your password?"),
            ("p", "Choose **Forgot password** on the login page, enter your email, and follow the reset link we send you."),
        ],
    },
    {
        "title": "Build a CV from scratch",
        "blocks": [
            ("p", "The wizard takes you through seven short steps, one section per page. From the **My CVs** page "
                  "choose **Create a new CV**, then **Build from Scratch**."),
            ("table", ["Step", "What to enter"], [
                ["1. Personal info", "Full name, job title, email, phone, location, LinkedIn"],
                ["2. Professional summary", "Two to four sentences on who you are and what you offer"],
                ["3. Work experience", "Job title, employer, dates, and what you achieved"],
                ["4. Education", "Qualification, institution, year"],
                ["5. Skills", "The skills that match the jobs you want"],
                ["6. Certifications", "Professional certificates and licences"],
                ["7. Review", "Check everything, see feedback, then download"],
            ]),
            ("h3", "Using AI help"),
            ("p", "On the sections that benefit from it, type a rough draft and press **Enhance with AI**. The AI "
                  "rewrites your draft and shows you its suggestion. Read it, keep what is true, and change "
                  "anything that is not. Only you know your real achievements, so never keep a number or claim "
                  "you cannot back up."),
            ("h3", "Moving around"),
            ("ul", [
                "Use the next and back buttons to move between steps.",
                "You can skip any step except Personal info, and come back to it later.",
                "Your CV is saved as a draft, so you can stop and finish another day from the **My CVs** page.",
            ]),
            ("h3", "The Review step"),
            ("p", "The last step shows your CV with a list of gaps, such as a missing summary or no measurable "
                  "results. On the top plan, an AI Career Coach gives line-by-line advice on what to fix. "
                  "Template choice and download buttons are also on this page."),
        ],
    },
    {
        "title": "Upload an existing CV and revamp it",
        "blocks": [
            ("p", "If you already have a CV, upload it and let AI make it stronger. This is the fastest route."),
            ("ol", [
                "From the **My CVs** page choose **Upload my existing CV**.",
                "Select your file. It must be a PDF or Word (DOCX) file, up to 10 MB.",
                "Wait about 15 seconds while we read it. Your details are copied into a new draft CV.",
                "On the Revamp page, choose a template (see the next section).",
                "Press **Revamp with AI Now** and wait about 25 seconds.",
            ]),
            ("h3", "What the AI changes"),
            ("ul", [
                "Your professional summary, written in a stronger and clearer voice.",
                "Your work experience bullets, using action verbs and measurable results.",
                "Your skills, arranged so employers' software can read them.",
            ]),
            ("p", "It keeps your job titles and your bullet structure. It does not invent new jobs."),
            ("h3", "Fill in the square brackets"),
            ("p", "Where the AI cannot know a number, it leaves a placeholder such as [X%] or [N customers]. "
                  "**Replace every placeholder with your real figure before you download**, or delete the phrase "
                  "if you have no figure. Never send a CV with brackets in it."),
            ("h3", "Your old version is safe"),
            ("p", "Every revamp saves a \"Before\" and an \"After\" copy. Open **Versions** on your CV to compare "
                  "them or restore the earlier one."),
            ("h3", "If the upload reads badly"),
            ("p", "Scanned photos of a CV, and files with heavy design, may not be read correctly. If your details "
                  "come through empty or jumbled, use **Build from Scratch** instead, or upload a plain Word version."),
        ],
    },
    {
        "title": "Choose or change your template",
        "blocks": [
            ("p", "The template decides how your PDF looks. You can change it at any time without losing your content."),
            ("h3", "How to change it"),
            ("ol", [
                "Open the **Revamp** page of your CV, or the **Review** step at the end of the wizard.",
                "Find the **Template** panel and tap the design you want. The current one shows a tick.",
                "The page reloads with your choice. Download the PDF to see the result.",
            ]),
            ("p", "You can also browse the **Templates** page from the menu and press **Use Template** to start a "
                  "new CV in that design. Templates marked with a lock are for paid plans."),
            ("h3", "Template styles"),
            ("table", ["Style", "What it looks like", "Best for"], [
                ["Single column", "Everything in one column, simple headings", "Online applications and company portals"],
                ["Sidebar (Navy, Slate)", "Coloured left column with contact, education and skills; experience on the right",
                 "Emailing a CV or handing one over in person"],
                ["Header band (Burgundy, Forest)", "Coloured band across the top with your name, then one column",
                 "A bolder look with a simple layout"],
                ["Timeline (Teal, Indigo)", "Experience and education on a vertical timeline", "Showing career progress"],
            ]),
            ("p", "If you apply through an online portal, choose a single-column template. Some screening software "
                  "reads two-column layouts less reliably."),
            ("h3", "Adding a profile photo"),
            ("p", "A photo shows only on the Sidebar templates."),
            ("ol", [
                "Open your CV in the editor and go to the **Personal** step.",
                "Choose a JPEG or PNG photo, up to 5 MB.",
                "Tick the consent box, then upload.",
            ]),
            ("p", "We crop the photo to a square and remove hidden data such as location. Use **Remove photo** at "
                  "any time. Many employers do not ask for a photo, so check the job advert and add one only if "
                  "it suits the role."),
            ("h3", "Word files"),
            ("p", "The Word (DOCX) download uses one standard layout whatever template you choose. Templates and "
                  "photos apply to the PDF."),
        ],
    },
    {
        "title": "ATS checker and cover letters",
        "blocks": [
            ("h3", "ATS checker"),
            ("p", "The checker scores how well your CV will pass employers' screening software and tells you what to fix."),
            ("ol", [
                "Open **ATS Checker** from the menu.",
                "Choose a tab: **Use a Saved CV** to pick one you built here, or **Upload a File** to check a CV from anywhere.",
                "Paste the job description if you have one. This is optional.",
                "Press the check button and wait about 20 seconds for your report.",
            ]),
            ("ul", [
                "**With no job description**, you get a general audit of your CV.",
                "**With a job description**, you get a match analysis showing which important words from the "
                "advert your CV is missing.",
            ]),
            ("p", "Use the report to edit your CV, then check again. Do this for each job you apply for."),
            ("h3", "Cover letters"),
            ("p", "A cover letter is tailored to one job, so write a new one each time."),
            ("ol", [
                "Open **Cover Letters** and choose to write a new one.",
                "Enter the **Job Title**.",
                "Pick a **Tone**: Professional, Formal, Executive or Friendly.",
                "Under **Use My CV**, choose one of your CVs so the letter uses your real experience. This is "
                "optional but gives better results.",
                "Paste the **Job Description** and submit.",
            ]),
            ("p", "When the letter appears, read it and edit anything that is not accurate or does not sound like "
                  "you. Then download it. Saved letters stay in your Cover Letters list, and you can delete any "
                  "you no longer need."),
        ],
    },
    {
        "title": "Preview, pay and download",
        "blocks": [
            ("p", "You only pay when your CV is ready. Until then you can build, edit and preview as much as you like."),
            ("h3", "Before you pay"),
            ("p", "At the **Review** step you see a preview of your own CV. The text is blurred and marked "
                  "\"SAMPLE\", so it cannot be copied. It shows that your CV is built and what it will look like. "
                  "Check the layout and the template here."),
            ("h3", "Choose a plan"),
            ("ol", [
                "Press **Choose a plan & download**, or open **Billing** from the menu.",
                "Compare the plans on the Plans page. Prices and features are shown there and may change.",
                "Pick a plan and a payment method.",
            ]),
            ("h3", "Pay with M-Pesa"),
            ("ol", [
                "Choose M-Pesa and enter the phone number registered with M-Pesa.",
                "Press pay. A payment prompt appears on your phone.",
                "Enter your M-Pesa PIN to approve.",
                "Wait on the page. It confirms automatically when the payment arrives.",
            ]),
            ("h3", "Pay by card"),
            ("p", "Choose card payment. You are taken to a secure checkout page to enter your card details, then "
                  "returned to the site."),
            ("p", "If the money left your account but the site still says pending, wait two minutes and refresh. "
                  "If it does not update, contact support with your M-Pesa confirmation message."),
            ("h3", "Download"),
            ("ol", [
                "Go to the **Review** step of your CV.",
                "Press **Download PDF**. Use **Download DOCX** if your plan includes Word files.",
                "Open the file and read it once more before you send it.",
            ]),
            ("p", "While your plan is active you can edit your CV and download it again as often as you like."),
        ],
    },
    {
        "title": "Manage your CVs",
        "blocks": [
            ("p", "The **My CVs** page lists every CV you have made, with the way it was created (wizard, upload or revamp)."),
            ("table", ["Action", "What it does"], [
                ["Edit", "Reopens your CV so you can change any section"],
                ["Versions", "Shows saved copies, including before and after an AI revamp, so you can compare and restore one"],
                ["Share", "Turns a public link on or off, so anyone with the link can view your CV without logging in (paid plans only)"],
                ["Delete", "Removes the CV for good, along with its profile photo"],
            ]),
            ("h3", "Good habits"),
            ("ul", [
                "Keep one main CV, and tailor its summary and skills before you apply for a different type of job.",
                "Give each CV a clear title when you create it, so you can tell them apart.",
                "Turn off the public link when you no longer need it.",
                "Deletion cannot be undone. Download a copy first if you may want it again.",
            ]),
        ],
    },
    {
        "title": "Tips and troubleshooting",
        "blocks": [
            ("h3", "Tips for a strong CV"),
            ("ul", [
                "Keep it to one or two pages. Put your most recent job first.",
                "Start each bullet with an action verb and, where you can, add a real number, such as \"Served 40 patients a day\".",
                "Use the exact skills named in the job advert, but only ones you truly have.",
                "Check spelling, dates and phone number. Ask a friend to read it.",
                "Run the ATS checker against each job description before you apply.",
                "Save your file with a clear name, such as Firstname_Lastname_CV.pdf.",
            ]),
            ("h3", "Common problems"),
            ("table", ["Problem", "What to do"], [
                ["No verification email", "Check spam, then use Resend verification on the login page"],
                ["Cannot log in", "Verify your email first. Use Forgot password if you cannot remember it"],
                ["Upload shows empty or jumbled details", "Upload a plain Word version, or use Build from Scratch"],
                ["AI says the daily limit is reached", "Free accounts have a daily limit for each feature. Try again tomorrow or upgrade"],
                ["AI suggestion failed", "Press the button again, or keep editing by hand. Your work is not lost"],
                ["Photo will not upload", "Use a JPEG or PNG under 5 MB and tick the consent box"],
                ["Template did not change", "Pick it again in the Template panel, then download a fresh PDF"],
                ["Paid but cannot download", "Wait two minutes, refresh, then contact support with your payment message"],
            ]),
            ("h3", "Getting help"),
            ("p", "Open **Support** from the site to ask our help assistant a question. It answers questions about "
                  "features and pricing at any time."),
        ],
    },
]
