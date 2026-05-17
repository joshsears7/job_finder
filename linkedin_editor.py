"""
linkedin_editor.py
------------------
LinkedIn profile optimization.
Uses Claude API when ANTHROPIC_API_KEY is set; falls back to local templates.
"""

import re
from claude_ai import generate_about_claude, generate_headlines_claude, generate_cold_dm_claude

# ── Skill display helper: ensure proper casing for tech acronyms ──
_UPPERCASE_SKILLS = {
    "sql","api","aws","gcp","kpi","crm","erp","sap","seo","sem","ux","ui","bi",
    "nlp","ml","ai","etl","elt","ci","cd","html","css","git","r","c++","bi",
    "pmp","cpa","cfa","hr","ats","saas","paas","sdk","iot","ar","vr",
}

def _skill_display(s: str) -> str:
    """Return skill with proper casing: SQL not Sql, Python not python."""
    sl = s.lower()
    if sl in _UPPERCASE_SKILLS:
        return sl.upper()
    if s == s.lower():           # all-lowercase → title-case
        return s.title()
    return s                     # already has intentional casing


# ── Top marketable skills by frequency in job postings ────────────
POWER_SKILLS = [
    "python","sql","machine learning","data analysis","financial modeling",
    "product management","project management","salesforce","aws","react",
    "marketing","excel","cybersecurity","devops","agile","tableau","power bi",
    "javascript","java","go","docker","kubernetes","seo","google analytics",
]

# ── Role → skills that LinkedIn recruiters filter on ──────────────
ROLE_LINKEDIN_SKILLS = {
    "software engineer":     ["Python","JavaScript","React","AWS","Docker","Kubernetes","CI/CD","System Design","REST APIs","Git"],
    "data analyst":          ["SQL","Python","Tableau","Power BI","Excel","Statistics","Google Analytics","Looker","dbt","R"],
    "data scientist":        ["Python","Machine Learning","TensorFlow","PyTorch","SQL","Statistics","NLP","Computer Vision","MLflow","Spark"],
    "business analyst":      ["SQL","Excel","Tableau","Jira","Confluence","Agile","Requirements Gathering","Process Improvement","Stakeholder Management","Power BI"],
    "product manager":       ["Product Roadmap","Agile","Jira","User Research","A/B Testing","SQL","Analytics","Stakeholder Management","Go-to-Market","OKRs"],
    "marketing analyst":     ["Google Analytics","SEO","SEM","HubSpot","Salesforce","Excel","Tableau","Content Strategy","Email Marketing","A/B Testing"],
    "financial analyst":     ["Financial Modeling","Excel","Bloomberg","SQL","Python","DCF","Valuation","FP&A","Power BI","PowerPoint"],
    "ux designer":           ["Figma","User Research","Prototyping","Wireframing","Adobe XD","Usability Testing","Design Systems","Sketch","Accessibility","HTML/CSS"],
    "project manager":       ["PMP","Agile","Scrum","Jira","MS Project","Risk Management","Stakeholder Management","Budget Management","Smartsheet","Change Management"],
    "consultant":            ["Excel","PowerPoint","Data Analysis","Financial Modeling","Project Management","Client Communication","Problem-Solving","SQL","Python","Stakeholder Management"],
    "account manager":       ["Salesforce","CRM","Sales Strategy","Account Management","Negotiation","HubSpot","Pipeline Management","Client Success","Revenue Growth","Prospecting"],
    "cybersecurity analyst": ["Security+","CISSP","SIEM","Splunk","Network Security","Incident Response","Python","Linux","Cloud Security","Risk Assessment"],
    "marketing coordinator": ["Social Media","Content Creation","SEO","Google Analytics","HubSpot","Canva","Email Marketing","Campaign Management","Brand Strategy","Adobe"],
    "hr specialist":         ["Workday","Greenhouse","Recruiting","Onboarding","HRIS","Compensation","Benefits","Employee Relations","Talent Acquisition","Performance Management"],
    "operations analyst":    ["SQL","Excel","Tableau","SAP","ERP","Supply Chain","Lean","Six Sigma","Process Improvement","Data Analysis"],
}


def _infer_industry(raw: str) -> str:
    raw = raw.lower()
    if any(w in raw for w in ["fintech","bank","finance","investment","trading","hedge fund","pe firm"]):
        return "Fintech & Finance"
    if any(w in raw for w in ["startup","series a","seed round","saas","venture"]):
        return "Startups & Tech"
    if any(w in raw for w in ["consulting","mckinsey","deloitte","bcg","bain","big 4","advisory"]):
        return "Consulting"
    if any(w in raw for w in ["healthcare","medical","pharma","biotech","hospital"]):
        return "Healthcare"
    if any(w in raw for w in ["ecommerce","retail","amazon","shopify","d2c","consumer"]):
        return "eCommerce & Retail"
    if any(w in raw for w in ["government","federal","public sector","dod","nsa","cia"]):
        return "Government & Defense"
    return ""


def generate_headlines(profile: dict, target_role: str = "") -> list[str]:
    """
    Return 3 LinkedIn headline variants.
    Uses Claude API when available; falls back to local templates.
    Max 220 chars (LinkedIn limit).
    """
    claude_result = generate_headlines_claude(profile, target_role)
    if claude_result:
        return claude_result

    skills   = [s.lower() for s in profile.get("skills", [])]
    titles   = profile.get("titles", [])
    raw      = profile.get("raw_text", "").lower()
    is_student = any(w in raw for w in ["university","college","student","graduating","gpa","sophomore","junior","senior"])

    role = target_role or (titles[0].title() if titles else "Professional")
    industry = _infer_industry(raw)

    top_skills = [_skill_display(s) for s in POWER_SKILLS if s in skills][:3]
    skills_str = " · ".join(top_skills) if top_skills else "Analytical Thinking · Problem Solving"

    h = []

    # Option 1: Keyword-dense (ATS-optimised for recruiter search)
    seeking = "Seeking opportunities" if is_student else "Open to new roles"
    h.append(f"{role} | {skills_str} | {seeking}")

    # Option 2: Value-prop / story-driven
    if len(top_skills) >= 2:
        h.append(f"Turning {top_skills[0]} & {top_skills[1]} into business impact · {role} · {industry or 'Open to opportunities'}")
    elif industry:
        h.append(f"{role} breaking into {industry} · {skills_str} · Let's connect")
    else:
        h.append(f"{role} | Building a career at the intersection of {top_skills[0] if top_skills else 'business'} & strategy")

    # Option 3: Bold personal brand
    if is_student:
        uni = next((w.title() for w in ["elon","unc","duke","mit","stanford","yale","harvard","ohio state","penn state","georgia tech"] if w in raw), "college")
        h.append(f"{uni} {'student' if uni == 'college' else uni + ' student'} → aspiring {role} | {skills_str} | Building in public")
    else:
        verb = "Driving" if any(w in raw for w in ["grew","increased","drove","delivered"]) else "Building"
        h.append(f"{verb} results through {top_skills[0] if top_skills else 'strategy'} · {role} · {industry or 'Open to impact'}")

    return [h_[:220] for h_ in h]


def generate_about(profile: dict, target_role: str = "") -> str:
    """
    Generate a LinkedIn About section.
    Uses Claude API when available; falls back to local templates.
    """
    claude_result = generate_about_claude(profile, target_role)
    if claude_result:
        return claude_result

    skills    = profile.get("skills", [])
    titles    = profile.get("titles", [])
    raw       = profile.get("raw_text", "").lower()
    name      = profile.get("name", "")
    yrs       = profile.get("years_experience", 1)
    exp_items = profile.get("experience", [])

    role       = target_role or (titles[0].title() if titles else "professional")
    industry   = _infer_industry(raw)
    is_student = any(w in raw for w in ["university","college","student","graduating","gpa","sophomore","junior","senior"])

    # Use original casing from profile skills, matched against power skills
    _UPPERCASE_SKILLS = {"sql","api","aws","gcp","kpi","crm","erp","sap","seo","sem","ux","ui","bi",
                         "nlp","ml","ai","etl","elt","ci","cd","html","css","git","r","c++"}
    def _skill_display(s):
        sl = s.lower()
        if sl in _UPPERCASE_SKILLS:
            return sl.upper()
        return s if (s != sl) else s.title()
    skills_lower = {s.lower(): s for s in skills}
    top_skills_orig = [_skill_display(skills_lower[ps]) for ps in POWER_SKILLS if ps in skills_lower][:5]
    fallback_skills = [_skill_display(s) for s in skills[:4]] if skills else []
    display_skills = top_skills_orig or fallback_skills

    skills_str_3 = ", ".join(display_skills[:3]) if display_skills else "strategy, analysis, and execution"
    all_skills_s  = ", ".join(display_skills) if display_skills else "core professional skills"

    # Broad signal detection
    has_leadership    = any(w in raw for w in ["led","managed","coordinated","directed","supervised","captain","head of","oversaw","mentored"])
    has_results       = any(w in raw for w in ["increased","reduced","improved","saved","saving","grew","generated","delivered","boosted","cut","achieved","exceeded","drove","optimized"])
    has_international = any(w in raw for w in ["international","global","abroad","uk","london","europe","studied","multicultural","cross-border"])
    has_tech          = any(w in raw for w in ["built","deployed","automated","automat","developed","launched","engineered","architected","coded","programmed","scripted"])
    has_client        = any(w in raw for w in ["client","customer","stakeholder","partner","account","vendor"])
    has_data          = any(w in raw for w in ["data","analytics","analysis","dashboard","reporting","metrics","insights","kpi"])

    # Companies worked at (for social proof)
    companies = [e.get("company","") for e in exp_items if e.get("company")][:3]
    co_str = companies[0] if companies else ""

    exp_str = f"{yrs}+ year{'s' if yrs != 1 else ''}"
    in_str  = f" in {industry}" if industry else ""

    # ── Paragraph 1: Hook (~45-55 words) ──
    if is_student:
        p1 = (
            f"I'm a {role.lower()}-focused student building real, hands-on experience "
            f"at the intersection of {display_skills[0] if display_skills else 'business'} and "
            f"{display_skills[1] if len(display_skills) > 1 else 'data-driven decision-making'}. "
            f"My goal: bridge the gap between technical skills and tangible business outcomes, "
            f"and find opportunities where I can learn fast and contribute immediately."
        )
    elif has_results:
        p1 = (
            f"I'm a {role} with {exp_str} of experience{in_str}. "
            f"My work sits at the intersection of {display_skills[0] if display_skills else 'analysis'} "
            f"and {display_skills[1] if len(display_skills) > 1 else 'clear communication'} — "
            f"with a focus on outcomes that are measurable, not just visible."
        )
    else:
        p1 = (
            f"I'm a {role} with a background in {skills_str_3}{' in ' + industry if industry else ''}. "
            f"I'm drawn to roles where rigorous thinking leads to clear decisions — "
            f"where the goal is not just to surface data, but to change what happens because of it."
        )

    # ── Paragraph 2: What I bring / day-to-day (~55-70 words) ──
    brings = []
    if has_tech and has_data:
        brings.append(f"{'Automating' if 'automat' in raw else 'Building'} analytical workflows that give teams faster, more reliable insights")
    elif has_tech:
        brings.append(f"Developing tools in {', '.join(str(s) for s in display_skills[:2]) or 'modern tech stacks'} to solve operational problems")
    if has_leadership:
        brings.append("Leading cross-functional initiatives, aligning stakeholders, and delivering on time")
    if has_client:
        brings.append("Working directly with clients to translate ambiguous requirements into clear, actionable plans")
    if has_data and not has_tech:
        brings.append("Translating data into clear narratives that support decisions at every level of an organization")
    if has_results:
        brings.append("Measuring outcomes, iterating based on evidence, and communicating findings to non-technical audiences")
    if not brings:
        brings = [
            f"Applying {display_skills[0] if display_skills else 'analytical'} skills to complex business problems",
            "Communicating clearly across technical and non-technical audiences",
            "Delivering work that is both rigorous and actionable",
        ]

    p2 = (
        f"What I bring to every role:\n"
        + "\n".join(f"- {b.capitalize()}" for b in brings[:4])
    )

    # ── Paragraph 3: Proof / differentiators (~50-70 words) ──
    proofs = []
    if has_tech and has_results:
        proofs.append(
            f"I've built systems{(' at ' + co_str) if co_str else ''} that reduced manual work "
            f"and produced results stakeholders could act on. "
            f"Technical accuracy matters — but so does the ability to explain what it means."
        )
    if has_leadership:
        proofs.append(
            "In my experience, strong teams run on clear goals, honest feedback, and shared ownership "
            "of outcomes. I've seen the difference it makes when everyone understands not just what "
            "they're doing, but why it matters."
        )
    if has_international:
        proofs.append(
            "My international experience has sharpened how I communicate across different working "
            "styles and cultural contexts — a skill that becomes more valuable as teams become more distributed."
        )
    if not proofs:
        proofs.append(
            f"My background in {all_skills_s} gives me the range to contribute across functions — "
            f"from initial analysis to final recommendation. I care about the full arc of a problem: "
            f"understanding it, solving it, and communicating the outcome clearly."
        )
    p3 = " ".join(proofs[:2])

    # ── Paragraph 4: CTA (~30-40 words) ──
    if is_student:
        p4 = (
            f"I'm actively looking for {role} internships and entry-level roles. "
            f"If you're hiring, building something interesting, or just want to connect — feel free to reach out. "
            f"I respond to every message."
        )
    else:
        p4 = (
            f"Currently open to {role} opportunities where I can make a real contribution "
            f"from day one{' in ' + industry if industry else ''}. "
            f"If that sounds like a fit, I'd love to talk."
        )

    return f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"


def rewrite_bullets_for_linkedin(bullets: list[str]) -> list[str]:
    """
    Rewrite resume bullets for LinkedIn style:
    - Shorter (1-2 lines, max 200 chars)
    - Achievement-first, not duty-first
    - Drop passive/bureaucratic openers
    - Keep the metric if one exists
    """
    PASSIVE_OPENERS = [
        "responsible for", "tasked with", "worked on", "helped with",
        "assisted in", "involved in", "duties included", "handled",
    ]
    WEAK_OPENERS = ["helped", "assisted", "supported", "participated in"]

    rewrites = []
    for b in bullets[:10]:
        b = b.strip().lstrip("•·-* ")
        if not b:
            continue
        b_lower = b.lower()

        # Strip passive openers
        for p in PASSIVE_OPENERS:
            if b_lower.startswith(p):
                b = b[len(p):].strip().capitalize()
                b_lower = b.lower()
                break

        # Replace weak openers with stronger alternatives
        replacements = {"helped ": "Contributed to ", "assisted ": "Supported ", "participated in ": "Took part in "}
        for weak, strong in replacements.items():
            if b_lower.startswith(weak):
                b = strong + b[len(weak):]
                break

        # Truncate to ~180 chars (LinkedIn bullet sweet spot)
        if len(b) > 180:
            # Try to cut at sentence boundary
            cut = b[:180]
            last_period = cut.rfind(".")
            b = (cut[:last_period + 1] if last_period > 120 else cut + "…")

        rewrites.append(b)

    return rewrites


def skills_to_add(profile: dict, target_role: str = "", job_description: str = "") -> list[str]:
    """
    Return LinkedIn skills the user should add for target_role.
    Compares the role's recruiter-filter skills against what the resume already shows.
    If a job_description is provided, also factors in JD-extracted skills.
    """
    existing = {s.lower() for s in profile.get("skills", [])}

    # Widen the search: also check the full resume text for skills mentioned inline
    # (catches "built with PostgreSQL" even if SQL isn't in the parsed skills list)
    raw_lower = profile.get("raw_text", "").lower()

    def _already_covered(skill: str) -> bool:
        sl = skill.lower()
        if sl in existing:
            return True
        # Check if a close variant appears in the full resume text
        core = sl.replace(" ", "").replace("-", "")
        return core in raw_lower.replace(" ", "").replace("-", "")

    # Determine target skill list from role
    role_lower = target_role.lower().strip()
    target: list[str] = []
    for role_key, skill_list in ROLE_LINKEDIN_SKILLS.items():
        if role_lower in role_key or role_key in role_lower or any(w in role_lower for w in role_key.split()):
            target = skill_list
            break

    if not target:
        target = ["SQL", "Python", "Excel", "Tableau", "Agile", "Project Management",
                  "Data Analysis", "Stakeholder Management", "Problem-Solving", "Communication"]

    missing = [s for s in target if not _already_covered(s)]

    # If a JD is provided, surface any COMMON_SKILLS in the JD that aren't in the resume — prepend them
    if job_description:
        try:
            from resume_parser import COMMON_SKILLS
            jd_lower = job_description.lower()
            jd_skills = [s for s in COMMON_SKILLS if s in jd_lower and not _already_covered(s)]
            # Deduplicate with the role-based list (jd_skills take priority)
            existing_lower = {m.lower() for m in missing}
            jd_unique = [s.title() if s.islower() else s for s in jd_skills if s.lower() not in existing_lower]
            missing = jd_unique + missing
        except Exception:
            pass

    return missing[:8]


def generate_connection_request(target_name: str, target_company: str,
                                 context: str = "", my_role: str = "") -> list[str]:
    """Return 3 short LinkedIn connection request variants (< 300 chars each)."""
    first = target_name.split()[0] if target_name and target_name.strip() else "there"
    co    = target_company or "your company"
    my_r  = my_role or "a job seeker"

    variants = [
        f"Hi {first} — I came across your profile and admire what you're building at {co}. I'm exploring {my_r} opportunities and would love to connect — no ask, just growing my network.",
        f"Hi {first}, I'm a {my_r} interested in {co}. Your path caught my attention and I'd love to follow along and potentially connect at some point. Hope you're open to it!",
        f"Hi {first} — found you while researching {co}. I'm actively looking at {my_r} roles and your background seems really relevant. Would love to connect and chat sometime.",
    ]
    return [v[:300] for v in variants]


def generate_cold_dm(profile: dict, target_name: str, target_company: str,
                     target_role_at_co: str = "", job_title: str = "") -> str:
    """
    Generate a cold LinkedIn DM / cold email to a recruiter or hiring manager.
    Uses Claude API when available; falls back to local templates.
    """
    claude_result = generate_cold_dm_claude(profile, target_name, target_company, target_role_at_co, job_title)
    if claude_result:
        return claude_result

    name    = profile.get("name", "")
    titles  = profile.get("titles", [])
    skills  = profile.get("skills", [])
    raw     = profile.get("raw_text", "").lower()

    my_role   = titles[0].title() if titles else "professional"
    top_skill = skills[0].title() if skills else "analytical thinking"
    has_result = any(w in raw for w in ["increased","reduced","grew","delivered","built","launched"])
    first = target_name.split()[0] if target_name and target_name.strip() else "there"

    result_line = ""
    if has_result:
        result_line = "In my recent work, I've [insert 1 specific result — e.g., built X that saved Y hours/week]."

    job_line = f"for the **{job_title}** position" if job_title else f"at {target_company}"

    msg = (
        f"Hi {first},\n\n"
        f"I came across your profile and noticed you're at {target_company} — {target_company} is actually "
        f"at the top of my list of companies I'd love to join.\n\n"
        f"I'm a {my_role} with experience in {top_skill}. {result_line} "
        f"I'd love to learn more about what the team is working on {job_line} and where my background might be a fit.\n\n"
        f"Would you be open to a quick 15-minute call? Completely flexible on timing.\n\n"
        f"Thanks so much,\n{name}"
    )
    return msg.strip()


def generate_salary_negotiation(offer_amount: int, target_amount: int,
                                 company: str, role: str, name: str = "",
                                 offer_context: str = "") -> dict:
    """
    Generate salary negotiation script with opening, counter, and walk-away.
    Returns dict with keys: opening, counter_email, verbal_script, notes.
    """
    gap_pct = round((target_amount - offer_amount) / offer_amount * 100)
    mid     = int((offer_amount + target_amount) / 2)

    opening = (
        f"Thank you so much for the offer — I'm genuinely excited about the opportunity to join {company} "
        f"as {role}. After carefully considering the offer and researching market rates for this role in this "
        f"location, I'd like to discuss the base salary.\n\n"
        f"Based on my research and the value I'd bring — specifically [your top 2 differentiators] — "
        f"I was hoping we could get closer to **${target_amount:,}**. "
        f"Is there flexibility there?"
    )

    counter_email = (
        f"Hi [Recruiter name],\n\n"
        f"Thank you again for the offer of ${offer_amount:,} for the {role} role at {company}. "
        f"I'm very excited about this opportunity and have been doing my research on market compensation.\n\n"
        f"Based on BLS and industry data for this role in this market, and given my background in "
        f"[your key skill/differentiator], I'd like to respectfully counter at **${target_amount:,}**.\n\n"
        f"I'm confident I can deliver strong results and would love to make this work. "
        f"Please let me know if there's flexibility, or if there are other components (signing bonus, "
        f"equity, remote flexibility) we can discuss.\n\n"
        f"Looking forward to your response,\n{name or '[Your name]'}"
    )

    verbal_script = (
        f"When they ask: 'What are your salary expectations?' → "
        f"Say: 'Based on my research for {role} roles in this market, I'm targeting "
        f"${target_amount:,}–${int(target_amount * 1.05):,}. Is that range workable?'\n\n"
        f"When they say: 'That's above our budget' → "
        f"Say: 'I understand. Could we meet in the middle at ${mid:,}? "
        f"And if base is fixed, is there room on signing bonus or equity?'\n\n"
        f"Walk-away line: 'I appreciate the offer and I want to make this work. "
        f"My minimum to make the move is ${int(offer_amount * 1.08):,}. "
        f"If that's not possible, I'll need to respectfully decline — though I hope we can find a path forward.'"
    )

    notes = [
        f"Your ask is {gap_pct}% above offer — {'reasonable, expect pushback' if gap_pct > 20 else 'well within normal negotiation range'}.",
        "Never give a number first — always respond to their number.",
        "Silence is powerful after making your ask — don't fill it.",
        "Always negotiate. 85% of employers have room to negotiate. Most people never ask.",
        "Ask for 48 hours to review any offer before countering — use it to research.",
        "If they won't move on base, ask for: signing bonus, equity, extra PTO, remote flexibility, 6-month review.",
    ]

    return {
        "opening": opening,
        "counter_email": counter_email,
        "verbal_script": verbal_script,
        "notes": notes,
        "gap_pct": gap_pct,
        "mid": mid,
    }


# ── Profile Analyzer ──────────────────────────────────────────────

def analyze_profile(pasted_text: str, target_role: str = "", has_photo: bool = True,
                    connection_count: int = 0) -> dict:
    """
    Score a pasted LinkedIn profile on 8 dimensions.
    User copies their profile text from the browser and pastes it here.

    Returns dict with keys:
        overall_score (0-100), grade, sections (dict of section_name -> {score, issues, tips}),
        all_star_checklist (list of {item, done}), top_recommendations (list of str)
    """
    raw = pasted_text.lower().strip()
    words = raw.split()
    word_count = len(words)

    sections = {}

    # ── 1. Headline (inferred from first 1-2 lines) ──────────────
    first_lines = pasted_text.strip().split("\n")[:3]
    headline_text = " ".join(first_lines).strip()
    h_score = 0
    h_issues = []
    h_tips = []

    if len(headline_text) >= 40:
        h_score += 30
    else:
        h_issues.append("Headline appears short — aim for 80–120 characters.")
        h_tips.append("Add your top 2 skills and the role you're targeting, separated by '|'.")

    # Check for keyword richness
    kw_hits = sum(1 for kw in POWER_SKILLS if kw in headline_text.lower())
    if kw_hits >= 2:
        h_score += 40
    elif kw_hits == 1:
        h_score += 20
        h_tips.append("Add 1–2 more skill keywords to your headline to appear in more recruiter searches.")
    else:
        h_issues.append("No recognizable skill keywords in headline — recruiters filter by these.")
        h_tips.append("Include skills like SQL, Python, Marketing, or your top technical skill.")

    # Check for role title
    if target_role and target_role.lower() in headline_text.lower():
        h_score += 30
    elif any(title in headline_text.lower() for title in ["analyst","engineer","manager","designer","consultant","developer","specialist"]):
        h_score += 20
    else:
        h_tips.append("Include your target job title in the headline for recruiter search visibility.")

    sections["Headline"] = {"score": min(h_score, 100), "issues": h_issues, "tips": h_tips}

    # ── 2. About / Summary section ───────────────────────────────
    about_indicators = ["about", "summary", "i am", "i'm a", "passionate", "experienced", "background in"]
    has_about = any(ind in raw for ind in about_indicators)
    ab_score = 0
    ab_issues = []
    ab_tips = []

    if has_about:
        ab_score += 40
        # Length check — about section typically 150-300 words
        if word_count >= 150:
            ab_score += 30
        else:
            ab_issues.append("About section appears short. Aim for 150–300 words.")
            ab_tips.append("Add a 'Proof' paragraph: list 2–3 specific accomplishments or skills you bring.")

        # CTA check
        if any(w in raw for w in ["reach out", "connect", "open to", "looking for", "feel free", "message me"]):
            ab_score += 30
        else:
            ab_tips.append("End your About with a call-to-action: 'Open to X roles — feel free to connect.'")
    else:
        ab_issues.append("No About/Summary section detected. This is one of the highest-impact sections.")
        ab_tips.append("Add a 3-paragraph About: Hook (who you are) → Proof (what you bring) → CTA (what you want).")

    sections["About / Summary"] = {"score": min(ab_score, 100), "issues": ab_issues, "tips": ab_tips}

    # ── 3. Experience ─────────────────────────────────────────────
    exp_indicators = ["experience", "worked at", "present", "current", "jan ", "feb ", "mar ", "jan 2", "20", "–", " - "]
    has_experience = sum(1 for ind in exp_indicators if ind in raw) >= 2
    ex_score = 0
    ex_issues = []
    ex_tips = []

    if has_experience:
        ex_score += 40
        # Quantification check
        has_numbers = bool(re.search(r'\d+%|\$\d|\d+x|\d+ (people|team|users|clients|accounts|projects)', raw))
        if has_numbers:
            ex_score += 35
        else:
            ex_issues.append("No quantified results detected. Numbers make bullets 40% more effective.")
            ex_tips.append("Add metrics: 'increased X by Y%', 'managed team of N', 'saved $X per quarter'.")

        # Multiple roles check
        role_count = raw.count(" at ") + raw.count("\npresent") + raw.count("· present")
        if role_count >= 2:
            ex_score += 25
        else:
            ex_tips.append("Make sure all your roles are listed, even part-time and internships.")
    else:
        ex_issues.append("No experience section detected in pasted text.")
        ex_tips.append("Ensure your Experience section is complete — it is the most-read section by recruiters.")
        ex_score = 20

    sections["Experience"] = {"score": min(ex_score, 100), "issues": ex_issues, "tips": ex_tips}

    # ── 4. Skills ─────────────────────────────────────────────────
    skill_indicators = ["skills", "endorsement", "skill assessment"]
    has_skills_section = any(ind in raw for ind in skill_indicators)
    skill_count = sum(1 for sk in POWER_SKILLS if sk in raw)
    sk_score = 0
    sk_issues = []
    sk_tips = []

    if has_skills_section or skill_count >= 3:
        sk_score += 40
        if skill_count >= 5:
            sk_score += 40
        elif skill_count >= 3:
            sk_score += 20
            sk_tips.append(f"Add more skills — found {skill_count} recognizable skills. LinkedIn recommends 5+ for search ranking.")
        else:
            sk_issues.append("Very few skills detected. LinkedIn ranks profiles higher when 5+ skills are listed.")

        # LinkedIn skill assessments
        if "skill assessment" in raw or "assessed" in raw or "verified" in raw:
            sk_score += 20
        else:
            sk_tips.append("Take LinkedIn Skill Assessments (SQL, Excel, Python) — passing adds a badge and boosts search rank.")
    else:
        sk_issues.append("No Skills section detected. This is critical for recruiter search filters.")
        sk_tips.append("Add 5–10 skills immediately — go to Profile → Add section → Skills.")
        sk_score = 10

    sections["Skills"] = {"score": min(sk_score, 100), "issues": sk_issues, "tips": sk_tips}

    # ── 5. Education ──────────────────────────────────────────────
    edu_indicators = ["university", "college", "bachelor", "master", "mba", "b.s.", "b.a.", "degree", "graduated", "gpa"]
    has_edu = any(ind in raw for ind in edu_indicators)
    ed_score = 0
    ed_issues = []
    ed_tips = []

    if has_edu:
        ed_score += 70
        # Activities/honors
        if any(w in raw for w in ["gpa", "honor", "dean", "club", "society", "award", "scholarship"]):
            ed_score += 30
        else:
            ed_tips.append("Add GPA (if 3.5+), honors, relevant coursework, or clubs to strengthen your Education section.")
    else:
        ed_issues.append("No Education section detected. Required for LinkedIn 'All-Star' status.")
        ed_score = 0

    sections["Education"] = {"score": min(ed_score, 100), "issues": ed_issues, "tips": ed_tips}

    # ── 6. Recommendations ────────────────────────────────────────
    rec_indicators = ["recommendation", "recommends", "endorsed by", "gave a recommendation"]
    has_recs = any(ind in raw for ind in rec_indicators)
    rec_score = 0
    rec_issues = []
    rec_tips = []

    if has_recs:
        rec_score = 85
        rec_tips.append("Great — keep collecting recommendations from managers and colleagues.")
    else:
        rec_issues.append("No recommendations detected. Profiles with recommendations get significantly more recruiter views.")
        rec_tips.append("Ask 2–3 people (manager, professor, peer) for a LinkedIn recommendation. A template request message is below.")
        rec_score = 0

    sections["Recommendations"] = {"score": rec_score, "issues": rec_issues, "tips": rec_tips}

    # ── 7. Photo & Profile Completeness ───────────────────────────
    photo_score = 85 if has_photo else 0
    photo_issues = [] if has_photo else ["No profile photo — profiles with photos get 21x more views and 9x more connection requests."]
    photo_tips = [] if has_photo else ["Add a professional headshot. Clean background, good lighting, business casual minimum."]
    sections["Profile Photo"] = {"score": photo_score, "issues": photo_issues, "tips": photo_tips}

    # ── 8. Network / Connections ──────────────────────────────────
    net_score = 0
    net_issues = []
    net_tips = []
    if connection_count >= 500:
        net_score = 100
    elif connection_count >= 200:
        net_score = 75
        net_tips.append("Aim for 500+ connections — LinkedIn shows '500+' publicly which signals credibility.")
    elif connection_count >= 50:
        net_score = 50
        net_issues.append("Under 200 connections. Send 5–10 personalized connection requests per day.")
        net_tips.append("Connect with classmates, alumni, professors, recruiters, and former colleagues first.")
    elif connection_count > 0:
        net_score = 25
        net_issues.append("Under 50 connections — prioritize building your network before actively job searching.")
        net_tips.append("Start with people you know: classmates, professors, family, former coworkers.")
    else:
        net_score = 40  # unknown — don't penalize if not provided
        net_tips.append("Add your connection count above to get a network strength score.")

    sections["Network Size"] = {"score": net_score, "issues": net_issues, "tips": net_tips}

    # ── Overall score (weighted) ──────────────────────────────────
    weights = {
        "Headline": 0.20,
        "About / Summary": 0.18,
        "Experience": 0.22,
        "Skills": 0.15,
        "Education": 0.10,
        "Recommendations": 0.08,
        "Profile Photo": 0.05,
        "Network Size": 0.02,
    }
    overall = int(sum(sections[s]["score"] * w for s, w in weights.items()))

    if overall >= 85:
        grade = "A"
    elif overall >= 75:
        grade = "B"
    elif overall >= 60:
        grade = "C"
    elif overall >= 45:
        grade = "D"
    else:
        grade = "F"

    # ── All-Star checklist ────────────────────────────────────────
    all_star = [
        {"item": "Profile photo added",                  "done": has_photo},
        {"item": "Headline is complete (80+ chars)",     "done": len(headline_text) >= 80},
        {"item": "About/Summary section written",        "done": has_about},
        {"item": "Current position with description",    "done": has_experience},
        {"item": "Education section added",              "done": has_edu},
        {"item": "5+ skills listed",                     "done": skill_count >= 5},
        {"item": "50+ connections",                      "done": connection_count >= 50 or connection_count == 0},
        {"item": "Industry specified",                   "done": any(w in raw for w in ["industry", "sector", "finance", "technology", "marketing", "healthcare", "consulting"])},
        {"item": "Location set",                         "done": any(w in raw for w in ["new york", "san francisco", "chicago", "boston", "austin", "remote", "united states"])},
        {"item": "At least 1 recommendation",            "done": has_recs},
    ]
    all_star_done = sum(1 for item in all_star if item["done"])
    is_all_star = all_star_done >= 7

    # ── Top 3 recommendations (highest-impact first) ──────────────
    by_impact = sorted(
        [(name, data) for name, data in sections.items() if data["issues"]],
        key=lambda x: x[1]["score"]
    )
    top_recs = []
    for name, data in by_impact[:3]:
        if data["tips"]:
            top_recs.append(f"**{name}**: {data['tips'][0]}")

    return {
        "overall_score": overall,
        "grade": grade,
        "sections": sections,
        "all_star_checklist": all_star,
        "all_star_done": all_star_done,
        "is_all_star": is_all_star,
        "top_recommendations": top_recs,
        "word_count": word_count,
    }
