"""CVForge AI - CV example pages (public SEO content).

Each example is a fictional, clearly labelled sample CV plus profession-specific
writing tips and FAQs. The page renders its FAQ and the FAQPage JSON-LD from the
same list, so they cannot drift apart.

Content rules (enforced by tests/test_cv_examples.py):
  * Every person, employer and figure is made up. Pages say so.
  * No guarantees about interviews, jobs or passing screening software.
  * No currency symbols or currency names; no regional "Africa" audience wording.
  * Titles <= 65 characters and descriptions 120-160 characters, all unique.
"""

DISCLAIMER = (
    "This is an example only. The name, employers and figures are made up. "
    "Use your own real details and never copy numbers you cannot support."
)


def _ex(slug, role, short, seo_title, seo_desc, card, intro, sample, tips, faqs):
    return {"slug": slug, "role": role, "short": short, "seo_title": seo_title,
            "seo_desc": seo_desc, "card": card, "intro": intro, "sample": sample,
            "tips": tips, "faqs": faqs}


EXAMPLES = [
    _ex(
        "registered-nurse", "Registered Nurse", "Nurse",
        "Nurse CV Example and Writing Tips | CVForge",
        "See a registered nurse CV example with a sample summary, experience bullets and skills, plus tips on listing your licence, wards and patient numbers.",
        "Licence, ward experience and patient load.",
        "A nursing CV is read for three things: your registration, where you have worked and what you can safely do. Lead with those, keep the layout plain and show the scale of the care you give.",
        {
            "name": "Priya Nair",
            "headline": "Registered Nurse | Medical-Surgical and Emergency Care",
            "summary": "Registered nurse with 6 years of experience in medical-surgical and emergency wards. Comfortable managing a caseload of 8 to 10 patients, giving medication safely and communicating clearly with families and doctors. Seeking a ward nurse role in a busy teaching hospital.",
            "experience": [
                {"title": "Staff Nurse, Medical-Surgical Ward", "org": "City General Hospital", "dates": "2021 to present",
                 "bullets": ["Care for 8 to 10 patients per shift, including medication rounds, wound care and discharge teaching.",
                             "Trained 5 new nurses on the ward's handover and documentation process.",
                             "Helped reduce missed observation checks by completing a weekly audit with the ward manager."]},
                {"title": "Nurse, Emergency Department", "org": "Lakeside Medical Centre", "dates": "2018 to 2021",
                 "bullets": ["Triaged up to 40 patients per shift using the department's priority scale.",
                             "Assisted with resuscitation and trauma cases as part of a team of 6.",
                             "Kept accurate records that passed two internal documentation reviews."]},
            ],
            "credentials": ["BSc Nursing, Riverside University (2018)", "Registered nurse licence, current",
                            "Basic Life Support (BLS) certificate", "Advanced Cardiac Life Support (ACLS) certificate"],
            "skills": ["Medication administration", "Patient assessment", "Wound care", "IV therapy", "Triage",
                       "Patient and family communication", "Electronic health records", "Infection control"],
        },
        ["Put your registration or licence near the top, and name the regulator if the employer is in another country.",
         "Name the type of ward and the number of patients you care for, so a reader can judge your experience quickly.",
         "List certificates such as BLS or ACLS with their year or expiry date.",
         "Use real outcomes, such as audits passed, only if you can back them up. Never invent figures.",
         "Keep patient details out of your CV. Describe the work, not the people."],
        [("How long should a nurse CV be?",
          "Two pages is common for nurses with several years of experience, because registration, certificates and ward experience all need space. A newly qualified nurse can often fit everything on one page. Always follow the employer's instructions."),
         ("Should I put my licence number on my CV?",
          "Say that you are registered and with which regulator. Many nurses leave the full number off a CV that will be shared widely and give it when an employer asks to verify it.")],
    ),
    _ex(
        "software-developer", "Software Developer", "Software Developer",
        "Software Developer CV Example and Tips | CVForge",
        "Read a software developer CV example with a sample summary, project bullets and skills, plus tips on showing your stack, results and portfolio links.",
        "Stack, results and portfolio links.",
        "A developer CV works best when it shows what you built, with which tools and what changed because of it. Recruiters skim for your stack and for proof that your work shipped.",
        {
            "name": "Daniel Kim",
            "headline": "Software Developer | Python, JavaScript and Cloud APIs",
            "summary": "Software developer with 4 years of experience building web applications and APIs in Python and JavaScript. Ships small, tested changes often and works closely with designers and product managers. Looking for a backend or full-stack role in a product team.",
            "experience": [
                {"title": "Software Developer", "org": "Brightpath Tech", "dates": "2022 to present",
                 "bullets": ["Built and maintain 12 REST API endpoints used by a web app with about 20,000 monthly users.",
                             "Reduced page load time by 35% by adding caching and fixing slow database queries.",
                             "Wrote automated tests that raised coverage on the payments module from 40% to 85%."]},
                {"title": "Junior Developer", "org": "Northwind Digital", "dates": "2020 to 2022",
                 "bullets": ["Developed customer-facing features in React and Node.js as part of a team of 5.",
                             "Fixed more than 60 reported bugs and wrote clear release notes for each deployment.",
                             "Moved the team's deployments to a CI pipeline, cutting release time from 2 hours to 20 minutes."]},
            ],
            "credentials": ["BSc Computer Science, Riverside University (2020)", "AWS Certified Cloud Practitioner (2023)"],
            "skills": ["Python", "JavaScript", "React", "Node.js", "SQL", "REST APIs", "Git", "Docker", "Automated testing"],
        },
        ["Lead with a short skills line that matches the stack in the job post, such as Python, Django and PostgreSQL.",
         "Describe results such as speed, users or reliability, not just that you worked on a feature.",
         "Link to your GitHub or portfolio, and make sure the projects behind those links are tidy.",
         "Keep to one or two pages and avoid listing every tool you have ever touched.",
         "Only list technologies you could discuss in an interview."],
        [("Should a developer CV list every programming language?",
          "No. List the languages and tools you use well and that match the job. A long list of tools you barely know can hide the strong ones, and interviewers may ask about anything you list."),
         ("Do I need a portfolio link on my developer CV?",
          "It helps, especially for junior roles, because it shows real work. Link only to projects you are happy for an employer to read, with a short description of what each one does.")],
    ),
    _ex(
        "accountant", "Accountant", "Accountant",
        "Accountant CV Example and Tips | CVForge",
        "Study an accountant CV example with a sample summary, reconciliation and reporting bullets and skills, plus tips on showing accuracy and qualifications.",
        "Accuracy, systems and qualifications.",
        "An accounting CV should show accuracy, the systems you use and the size of the books you handle. Numbers help here: reconciliations, budgets, month-end timelines and audit results.",
        {
            "name": "Grace Mwangi",
            "headline": "Accountant | Month-End Close, Reconciliations and Audit Support",
            "summary": "Accountant with 5 years of experience in general ledger accounting, reconciliations and financial reporting for small and mid-sized companies. Reliable at month-end deadlines and experienced in supporting external audits. Seeking a senior accountant role.",
            "experience": [
                {"title": "Accountant", "org": "Harbour Trading Ltd", "dates": "2021 to present",
                 "bullets": ["Prepare monthly management accounts for a business with 3 branches, delivered by working day 5.",
                             "Reconcile 15 bank and supplier accounts each month and clear differences within the same close.",
                             "Supported two external audits and answered all queries on the areas I manage."]},
                {"title": "Accounts Assistant", "org": "Meridian Supplies", "dates": "2019 to 2021",
                 "bullets": ["Processed around 400 supplier invoices a month and matched them to purchase orders.",
                             "Prepared tax returns and filed them on time every period.",
                             "Helped move payroll and expense records into a new accounting package."]},
            ],
            "credentials": ["BCom Accounting, Riverside University (2019)",
                            "Professional accounting qualification (state the body and your level)"],
            "skills": ["General ledger", "Bank reconciliation", "Month-end close", "Financial reporting", "Tax returns",
                       "Accounts payable and receivable", "Excel", "Accounting software (name yours)"],
        },
        ["Name the accounting package you use, such as QuickBooks, Xero or Sage, only if you really use it.",
         "Show timelines and volumes, for example close by day 5, 15 reconciliations or 400 invoices.",
         "State your professional qualification and its level clearly near the top.",
         "Mention audits, budgets or cost savings you contributed to, with real numbers.",
         "Check every figure and date. An error on an accountant's CV costs trust."],
        [("Should an accountant list software skills?",
          "Yes, by name, and only the ones you actually use. Accounting packages and Excel skills are often used to filter applications, so match the tools named in the job post where they are true for you."),
         ("How do I show my qualification if I am still studying?",
          "List it with your level or the exams passed so far and an expected completion date. Be clear about what is complete, so nobody has to guess.")],
    ),
    _ex(
        "teacher", "Teacher", "Teacher",
        "Teacher CV Example and Tips | CVForge",
        "Explore a teacher CV example with a sample summary, classroom experience bullets and skills, plus tips on showing subjects, age groups and learner progress.",
        "Subjects, age groups and learner progress.",
        "A teaching CV is read by head teachers and school panels who want to know what you teach, to whom and how your learners progress. Be specific about subjects, age groups and results.",
        {
            "name": "Hannah Brooks",
            "headline": "Secondary School Teacher | Mathematics and Science",
            "summary": "Secondary school teacher with 7 years of experience teaching mathematics to learners aged 12 to 18. Plans clear lessons, uses short checks for understanding and supports learners who need extra help. Looking for a mathematics teacher role in a school that values steady progress.",
            "experience": [
                {"title": "Mathematics Teacher", "org": "Hillcrest Secondary School", "dates": "2019 to present",
                 "bullets": ["Teach 5 classes of about 35 learners each, aged 12 to 18.",
                             "Raised the share of my learners reaching the pass mark from 62% to 78% over three years with weekly practice quizzes and revision sessions.",
                             "Run a free after-school mathematics club for 25 learners and mentor 2 trainee teachers each year."]},
                {"title": "Teacher, Mathematics and Science", "org": "Greenfield Academy", "dates": "2016 to 2019",
                 "bullets": ["Taught mathematics and general science to learners aged 12 to 15.",
                             "Wrote and marked end-of-term exams and gave written feedback to parents.",
                             "Coached the school science fair team, which reached the regional round in 2018."]},
            ],
            "credentials": ["Bachelor of Education (Mathematics), Riverside University (2016)", "Teaching registration or licence, current"],
            "skills": ["Lesson planning", "Classroom management", "Assessment and marking", "Differentiated teaching",
                       "Mathematics for ages 12 to 18", "Parent communication", "Mentoring trainee teachers", "Digital learning tools"],
        },
        ["Name the subjects, age groups and class sizes you have taught.",
         "Show learner progress with a real result, such as improved pass rates, if you can support it.",
         "Include your teaching registration and any safeguarding or child protection training.",
         "Add extra-curricular work, such as clubs and coaching, because schools value it.",
         "Keep the layout calm and easy to read. Panels often read many CVs in one sitting."],
        [("Should I include a personal statement in a teacher CV?",
          "A short professional summary at the top of the CV is enough. Some schools also ask for a separate application letter, so check the vacancy instructions."),
         ("What should a newly qualified teacher put on a CV?",
          "Put your qualification and teaching practice first, then name the subjects and age groups you taught, the lessons you planned and any feedback you received from your mentor.")],
    ),
    _ex(
        "customer-service-representative", "Customer Service Representative", "Customer Service",
        "Customer Service CV Example and Tips | CVForge",
        "Use this customer service CV example with a sample summary, call and chat bullets and skills, plus tips on showing volume, quality and calm under pressure.",
        "Volume, quality scores and calm under pressure.",
        "Customer service managers hire people who stay calm, solve problems and are accurate. Your CV should show how many customers you help, how quickly and how you handle difficult moments.",
        {
            "name": "Tariq Hussain",
            "headline": "Customer Service Representative | Phone, Email and Live Chat",
            "summary": "Customer service representative with 3 years of experience handling about 60 calls and chats a day for an online retailer. Calm with upset customers, careful with details and quick to find a fix. Looking for a customer support role in a team that values clear communication.",
            "experience": [
                {"title": "Customer Service Representative", "org": "ShopSure Online", "dates": "2023 to present",
                 "bullets": ["Handle around 60 customer contacts a day across phone, email and live chat.",
                             "Kept a customer satisfaction score of 92% over the last 12 months.",
                             "Resolve most issues at first contact and pass complex cases to the right team with clear notes."]},
                {"title": "Call Centre Agent", "org": "ConnectLine Services", "dates": "2021 to 2023",
                 "bullets": ["Answered more than 80 inbound calls a day and met the team's handling-time target.",
                             "Recorded each call accurately in the CRM so colleagues could follow up without asking the customer again.",
                             "Was recognised as team member of the quarter twice for positive customer feedback."]},
            ],
            "credentials": ["Secondary school certificate or diploma (add the year)", "Customer service training course (name the provider)"],
            "skills": ["Active listening", "Problem solving", "Phone and live chat support", "Email writing", "CRM software",
                       "Complaint handling", "Typing speed and accuracy", "Teamwork"],
        },
        ["Show volume: how many calls, chats or tickets you handle each day.",
         "Include a real satisfaction or quality score if your employer tracks one.",
         "Mention the channels you support, such as phone, email, chat or social media.",
         "Give one short example of turning a difficult customer into a satisfied one.",
         "Check spelling and punctuation. Employers read your CV as a writing sample."],
        [("What skills should a customer service CV include?",
          "Communication, patience, problem solving and accuracy come first, followed by tools such as a CRM or ticketing system. Back each skill with a short example in your experience section."),
         ("Can I get a customer service job with no experience?",
          "Yes, many employers hire for attitude and train on the job. Show customer-facing work you have done, such as retail, hospitality, volunteering or school roles, and explain what you learned.")],
    ),
    _ex(
        "marketing-executive", "Marketing Executive", "Marketing",
        "Marketing Executive CV Example and Tips | CVForge",
        "Review a marketing executive CV example with a sample summary, campaign result bullets and skills, plus tips on showing channels, budgets and measurable growth.",
        "Channels, budgets and measurable results.",
        "Marketing managers look for results: leads, sales, reach and cost per result. Show the channels you run, the budgets you handle and what changed because of your work.",
        {
            "name": "Sofia Alvarez",
            "headline": "Marketing Executive | Social Media, Email and Content",
            "summary": "Marketing executive with 4 years of experience running social media, email and content campaigns for consumer brands. Comfortable with analytics, testing and working to a monthly budget. Seeking a digital marketing role in a growing business.",
            "experience": [
                {"title": "Marketing Executive", "org": "Bloom & Co", "dates": "2022 to present",
                 "bullets": ["Manage social media accounts with 45,000 followers and grew engagement by 28% in 12 months.",
                             "Plan and send a monthly newsletter to 12,000 subscribers with an average open rate of 31%.",
                             "Manage the monthly paid advertising budget and lowered cost per lead by 18% through A/B testing."]},
                {"title": "Marketing Assistant", "org": "Peak Retail Group", "dates": "2020 to 2022",
                 "bullets": ["Wrote blog posts and product descriptions that increased organic search visits by 40%.",
                             "Helped plan 6 product launches by preparing content, schedules and reports.",
                             "Built weekly performance reports in Excel for the marketing manager."]},
            ],
            "credentials": ["BA Marketing or Communications, Riverside University (2020)", "Google Analytics certification (add the year)"],
            "skills": ["Social media management", "Email marketing", "Content writing", "SEO basics", "Google Analytics",
                       "Paid advertising", "Campaign reporting", "Canva or design tools"],
        },
        ["Lead each bullet with a result, such as growth, leads or sales, and the time it took.",
         "Name the platforms and tools you use, such as Meta Ads, Mailchimp or Google Analytics.",
         "Show that you can work to a budget and report on it.",
         "Link to a portfolio or sample campaigns where you can.",
         "Use percentages and counts you can verify. Marketers are expected to know their numbers."],
        [("What should a marketing CV include?",
          "A short summary, your channels and tools, results with numbers and a link to samples of your work. Keep the results honest and be ready to explain how you measured them."),
         ("How do I show results if I was part of a team?",
          "Say what you personally did and what the team achieved, for example: wrote the emails for a campaign that lifted team sales by 15%. This keeps the credit accurate.")],
    ),
    _ex(
        "administrative-assistant", "Administrative Assistant", "Administrative Assistant",
        "Administrative Assistant CV Example and Tips | CVForge",
        "See an administrative assistant CV example with a sample summary, scheduling and records bullets and skills, plus tips on showing organisation and accuracy.",
        "Organisation, records and office software.",
        "An administrative assistant keeps an office running. Your CV should show organisation, accuracy and the tools you use, with real examples of the schedules, records and people you support.",
        {
            "name": "Naomi Clarke",
            "headline": "Administrative Assistant | Scheduling, Records and Office Support",
            "summary": "Administrative assistant with 5 years of experience supporting a team of 12 in a busy office. Organised, discreet and fast with documents, calendars and filing systems. Looking for an executive assistant or office administrator role.",
            "experience": [
                {"title": "Administrative Assistant", "org": "Crestview Logistics", "dates": "2021 to present",
                 "bullets": ["Manage calendars, travel and meetings for 3 managers and avoid double-bookings with a shared planner.",
                             "Prepare and proofread reports, letters and minutes for weekly management meetings.",
                             "Moved paper records into a digital filing system so the team can find documents faster."]},
                {"title": "Receptionist and Office Assistant", "org": "Pinnacle Clinic", "dates": "2019 to 2021",
                 "bullets": ["Welcomed about 50 visitors and callers a day and directed them to the right person.",
                             "Kept stock records for office supplies and reordered before items ran out.",
                             "Handled incoming and outgoing post and courier bookings."]},
            ],
            "credentials": ["Diploma in Office Administration, Riverside College (2019)", "Computer skills certificate (name it)"],
            "skills": ["Calendar management", "Minute taking", "Document preparation", "Filing and records",
                       "Microsoft Office or Google Workspace", "Phone and email etiquette", "Travel booking", "Confidentiality"],
        },
        ["List the software you know, such as Word, Excel, Outlook or Google Workspace.",
         "Mention how many people you support and how many calls, visitors or tasks you handle.",
         "Show that you can be trusted with private information.",
         "Give one example of a process you improved, even a small one.",
         "Format your CV neatly. It is your best proof of attention to detail."],
        [("What skills does an administrative assistant need?",
          "Organisation, clear writing, time management, discretion and confident use of office software. Show each one with a real task, such as managing a calendar or preparing minutes."),
         ("Is a typing speed worth listing?",
          "If the job post mentions it or the role involves a lot of data entry, yes. Give a tested speed and accuracy figure rather than a vague claim.")],
    ),
    _ex(
        "project-manager", "Project Manager", "Project Manager",
        "Project Manager CV Example and Tips | CVForge",
        "Check a project manager CV example with a sample summary, delivery bullets and skills, plus tips on showing scope, budget, team size and on-time results.",
        "Scope, budget, team size and delivery.",
        "A project manager CV should show scope, budget, timeline and team size, and whether the work was delivered. Hiring managers want proof that you finish what you start.",
        {
            "name": "Rahul Mehta",
            "headline": "Project Manager | Delivery, Budgets and Cross-Team Coordination",
            "summary": "Project manager with 8 years of experience delivering software and operations projects on time and within budget. Skilled at planning, risk tracking and keeping stakeholders informed. Seeking a senior project manager role.",
            "experience": [
                {"title": "Project Manager", "org": "Orbit Systems", "dates": "2020 to present",
                 "bullets": ["Led 6 projects with teams of 4 to 15 people and delivered 5 on schedule and within budget.",
                             "Reported spend and progress to senior management each month for projects with budgets of up to 250,000.",
                             "Introduced weekly risk reviews that helped the team spot and fix delays earlier."]},
                {"title": "Project Coordinator", "org": "Vantage Operations", "dates": "2017 to 2020",
                 "bullets": ["Coordinated schedules and tasks for 4 projects running at the same time in a shared planning tool.",
                             "Ran weekly progress meetings and sent clear action lists to all stakeholders.",
                             "Supported the move to a new inventory system across 3 sites."]},
            ],
            "credentials": ["BSc Business Administration, Riverside University (2016)",
                            "PMP, PRINCE2 or similar certification (state the level and year)"],
            "skills": ["Project planning", "Budget management", "Risk management", "Stakeholder communication",
                       "Agile and waterfall methods", "Team leadership", "Reporting", "Planning tools (name yours)"],
        },
        ["Show project size: budget, team size, duration and outcome.",
         "State whether you delivered on time and on budget, and what you did when things slipped.",
         "Name your methods and certifications, such as Agile, PRINCE2 or PMP, only if you hold them.",
         "Keep the tone about results and leadership, not just tasks.",
         "Include one example of a risk you spotted early and how you handled it."],
        [("Do I need a PMP to get a project manager job?",
          "Not always. Many employers value delivered projects as much as a certificate. A recognised certification can help, so list it clearly if you hold it, and show real delivery next to it."),
         ("How do I show project results without exact figures?",
          "Give honest ranges or describe the outcome, for example delivered two weeks early or kept within the approved budget. Do not invent precise numbers.")],
    ),
    _ex(
        "no-experience", "First Job or Graduate", "No Experience",
        "CV With No Experience: Example and Tips | CVForge",
        "Learn how to write a CV with no experience using this graduate example: sample summary, projects, volunteering and skills, plus tips to fill one page well.",
        "Education, projects and volunteering.",
        "You do not need job history to write a good first CV. Use your education, projects, volunteering and skills to show what you can do, and keep it to one page.",
        {
            "name": "Emma Walker",
            "headline": "Graduate | Business Studies | Seeking an Entry-Level Role",
            "summary": "Recent business studies graduate with strong teamwork, communication and Excel skills, built through university projects, a student society role and volunteering. Quick to learn and reliable. Looking for an entry-level role in administration or customer support.",
            "experience": [
                {"title": "Treasurer, Business Studies Society", "org": "Riverside University", "dates": "2023 to 2024",
                 "bullets": ["Tracked the society's budget in Excel and reported spending to 40 members each term.",
                             "Helped organise 3 events with more than 100 attendees by managing sign-ups and supplier contacts.",
                             "Worked with a committee of 8 to set and meet semester goals."]},
                {"title": "Volunteer, Community Food Drive", "org": "Local community group", "dates": "2022 to 2023",
                 "bullets": ["Sorted and packed food for 120 families across 6 weekend sessions.",
                             "Welcomed volunteers and kept the sign-in sheet accurate.",
                             "Helped train 4 new volunteers on safe lifting and packing."]},
            ],
            "credentials": ["BA Business Studies, Riverside University (2024)", "Secondary school certificate (add grades if strong)"],
            "skills": ["Teamwork", "Written and spoken communication", "Excel", "Time management",
                       "Customer service (volunteering)", "Quick learning", "Reliability", "Basic data entry"],
        },
        ["Put education first, then add projects, society roles, volunteering and part-time work under it.",
         "Describe school and volunteer work the same way you would a job: what you did and what resulted.",
         "Match your skills to the job post, using only skills you can show.",
         "Keep it to one page with a short summary that names the role you want.",
         "Ask a teacher or supervisor to read it before you send it."],
        [("What do I put on a CV if I have no work experience?",
          "Education, projects, volunteering, society or sports roles, short courses and skills. Describe what you did and what resulted, in the same way you would describe paid work."),
         ("Should I include hobbies on a first CV?",
          "You can add a short interests line if it shows useful traits, such as team sports or running a club. Keep it brief and honest, and give most of the space to skills and achievements.")],
    ),
]

_BY_SLUG = {e["slug"]: e for e in EXAMPLES}


def all_examples():
    return list(EXAMPLES)


def get_example(slug):
    return _BY_SLUG.get(slug)


def related(slug, count=4):
    """Other examples to link to, in a stable order starting after this one."""
    slugs = [e["slug"] for e in EXAMPLES]
    if slug not in slugs:
        return EXAMPLES[:count]
    i = slugs.index(slug)
    ordered = slugs[i + 1:] + slugs[:i]
    return [_BY_SLUG[s] for s in ordered[:count]]
