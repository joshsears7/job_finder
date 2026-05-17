"""
ai_tools.py
-----------
Cover letter generator, ATS scanner, and interview prep.
Uses Claude API when ANTHROPIC_API_KEY is set; falls back to local templates.
"""

import re
import scorer as _scorer
from claude_ai import generate_cover_letter_claude

# ── Shared helpers ───────────────────────────────────────────────

_SKIP_PATTERNS = re.compile(
    r"(certif|bachelor|master|university|college|major|gpa|scuba|"
    r"microsoft|cisco|skill[s]?:|education|may 20|jan 20|present|elon|"
    r"member|captain|student|^\s*\d{4}|engage with|participate in|"
    r"communication,|adaptability|public speaking)",
    re.IGNORECASE,
)


def _top_resume_sentences(resume_text, job_description, top_n=3):
    """Return the N resume sentences most semantically similar to the job."""
    model = _scorer.get_model()
    raw = [s.strip() for s in re.split(r"[.\n]", resume_text) if len(s.strip()) > 40]
    # Filter out header-like lines and credential lines
    sentences = [s for s in raw if not _SKIP_PATTERNS.search(s)
                 and not s.isupper() and len(s.split()) >= 6]
    if not sentences:
        return []
    job_emb = model.encode(job_description[:600], convert_to_tensor=True)
    res_embs = model.encode(sentences, convert_to_tensor=True)
    scores = _scorer._util.cos_sim(job_emb, res_embs)[0]
    top_idx = scores.argsort(descending=True)[:min(top_n, len(sentences))]
    return [sentences[i] for i in top_idx]


def _extract_responsibilities(job_description, max_items=4):
    """Pull bullet-point-like responsibility lines from a job description."""
    lines = [l.strip(" •\t-–") for l in job_description.split("\n")
             if len(l.strip()) > 20]
    # Prefer lines that start with action verbs
    action_verbs = ("develop", "build", "manage", "analyze", "create", "support",
                    "lead", "coordinate", "design", "drive", "own", "work with",
                    "collaborate", "implement", "maintain", "improve", "partner")
    action_lines = [l for l in lines if l.lower().startswith(action_verbs)]
    fallback = [l for l in lines if l not in action_lines]
    combined = (action_lines + fallback)[:max_items]
    return combined


def _detect_role_family(title):
    t = title.lower()
    if any(x in t for x in ("analyst", "analysis", "analytics", "data")):
        return "analyst"
    if any(x in t for x in ("engineer", "developer", "software", "backend", "frontend")):
        return "engineer"
    if any(x in t for x in ("manager", "director", "vp", "head of", "lead")):
        return "manager"
    if any(x in t for x in ("marketing", "growth", "brand", "content", "seo")):
        return "marketing"
    if any(x in t for x in ("finance", "financial", "investment", "accounting", "banking")):
        return "finance"
    if any(x in t for x in ("operations", "coordinator", "associate", "specialist")):
        return "operations"
    if any(x in t for x in ("sales", "account", "business development", "bd")):
        return "sales"
    return "general"


# ── Cover Letter ─────────────────────────────────────────────────

OPENING_HOOKS = {
    "analyst": (
        "I have always been drawn to roles where rigorous analysis drives real decisions, "
        "which is why the {role} opportunity at {company} immediately caught my attention."
    ),
    "engineer": (
        "Building systems that solve real problems is what drives me — "
        "and the {role} role at {company} is exactly the kind of challenge I am looking for."
    ),
    "marketing": (
        "The intersection of data and creativity is where I thrive, "
        "which is why the {role} position at {company} stands out to me."
    ),
    "finance": (
        "A career at the intersection of financial markets and data-driven decision-making "
        "has always been my goal, making the {role} role at {company} a compelling opportunity."
    ),
    "operations": (
        "I am energized by the challenge of making complex operations run smoothly and efficiently, "
        "which drew me to the {role} position at {company}."
    ),
    "sales": (
        "I thrive in environments where building relationships and delivering value go hand in hand — "
        "exactly the spirit I see in the {role} role at {company}."
    ),
    "manager": (
        "I am excited to bring my leadership experience and strategic mindset "
        "to the {role} position at {company}."
    ),
    "general": (
        "I am writing to express my strong interest in the {role} position at {company}, "
        "where I believe my background and skills align closely with your needs."
    ),
}

PROJECT_TRIGGERS = {
    "python":      "including building automated workflows and data pipelines in Python that deliver real operational value",
    "data":        "including building end-to-end data pipelines that ingest, clean, and surface actionable insights",
    "finance":     "including developing financial models and analysis workflows that support decision-making",
    "sql":         "including designing and querying databases to support analytics and reporting needs",
    "excel":       "with advanced proficiency in Excel for financial modeling, dashboards, and data analysis",
    "api":         "including integrating and managing external APIs in production systems",
    "automation":  "including building automated analysis and reporting pipelines that reduce manual work significantly",
    "marketing":   "including applying data analysis to marketing campaigns and conversion optimization",
    "international":"combined with international experience that strengthened cross-cultural collaboration and communication",
}


def generate_cover_letter(profile, job):
    """
    Generate a tailored cover letter.
    Uses Claude API when available; falls back to local templates.
    Returns a string ready to copy-paste.
    """
    claude_result = generate_cover_letter_claude(profile, job)
    if claude_result:
        return claude_result

    company     = job.get("company", "your company")
    role        = job.get("title",   "this position")
    role_family = _detect_role_family(role)
    name        = profile.get("name") or "Candidate"
    jd_lower    = job.get("description", "").lower()

    # Matched skills
    matched, _ = _scorer.get_skill_gaps(profile["raw_text"], job.get("description", ""))
    top_skills  = matched[:4] or profile["skills"][:4]
    skills_str  = ", ".join(top_skills) if top_skills else "analytical thinking and problem solving"

    # Opening hook
    opening = OPENING_HOOKS.get(role_family, OPENING_HOOKS["general"]).format(
        role=role, company=company
    )

    # ── Build body dynamically from profile facts ──
    raw_lower = profile["raw_text"].lower()
    yrs       = profile.get("years_experience", 0)
    titles    = profile.get("titles", [])
    title_str = titles[0].title() if titles else ""

    # Background sentence (generic, based on actual profile)
    is_student = any(w in raw_lower for w in ["university","college","student","graduating","gpa"])
    if is_student:
        edu_sentence = (
            f"I am a student building a strong foundation in {skills_str}, "
            f"with hands-on project experience that has given me practical exposure beyond the classroom."
        )
    elif yrs >= 3:
        edu_sentence = (
            f"I bring {yrs}+ years of experience as a {title_str or 'professional'}, "
            f"with a strong track record in {skills_str}."
        )
    elif yrs >= 1:
        edu_sentence = (
            f"I bring {yrs} year{'s' if yrs != 1 else ''} of experience in {skills_str}, "
            f"with a focus on delivering measurable results."
        )
    else:
        edu_sentence = f"I bring a strong foundation in {skills_str}, with demonstrated experience applying these capabilities to real-world problems."

    # Leadership sentence (generic — detected from actual profile)
    has_leadership = any(w in raw_lower for w in
                         ["led","managed","supervised","captain","head of","coordinated","oversaw","mentored"])
    leadership_sentence = (
        "I have direct experience leading teams and cross-functional initiatives, "
        "which has given me a clear sense of how to align people, set expectations, and deliver results."
        if has_leadership else ""
    )

    # Technical / project sentence
    project_sentence = ""
    tech_skills = [s for s in profile["skills"] if s in ("python","sql","flask","pandas","r programming","excel","rest api")]
    for trigger, snippet in PROJECT_TRIGGERS.items():
        if trigger in jd_lower or trigger in role.lower():
            if tech_skills:
                project_sentence = (
                    f"In addition to my formal background, I have built technical skills through hands-on work — "
                    f"{snippet}. This has given me the ability to connect business context "
                    f"with data and technology in a practical way."
                )
            break

    if not project_sentence and tech_skills:
        project_sentence = (
            f"I have developed practical skills in {', '.join(tech_skills[:3])}, "
            f"applying them to projects that required both analytical rigor and "
            f"the ability to communicate findings clearly to non-technical stakeholders."
        )

    # Role-specific value prop
    role_value = {
        "analyst":    f"My combination of quantitative skills ({skills_str}) and ability to communicate findings clearly positions me to contribute meaningfully to {company}'s analytical work.",
        "marketing":  f"My background in {skills_str}, combined with a strong orientation toward data-driven decision-making, makes me eager to bring measurable impact to {company}.",
        "finance":    f"My technical skills in {skills_str} and my analytical foundation align closely with the work your team does at {company}.",
        "operations": f"I thrive in structured environments where process thinking and clear communication drive results — qualities I am eager to bring to {company}.",
        "engineer":   f"My technical background in {skills_str}, combined with a focus on clean, maintainable code and strong communication, aligns well with what {company} is building.",
        "sales":      f"My combination of {skills_str} and relationship-building experience positions me well to contribute to {company}'s growth.",
        "manager":    f"My leadership experience and skills in {skills_str} align closely with what this {role} role at {company} requires.",
        "general":    f"I am confident my background in {skills_str}, combined with strong communication and analytical skills, would allow me to contribute meaningfully at {company}.",
    }.get(role_family, f"I am confident my skills in {skills_str} align well with what {company} is looking for.")

    # Assemble paragraphs, skip empty ones
    body_paras = [p for p in [edu_sentence, leadership_sentence, project_sentence, role_value] if p.strip()]
    body = "\n\n".join(body_paras)

    letter = f"""Dear Hiring Manager,

{opening}

{body}

I would welcome the opportunity to discuss how my background maps to {company}'s goals and the {role} role specifically. Thank you for your time and consideration.

Sincerely,
{name}"""

    return letter.strip()


# ── ATS Scanner ──────────────────────────────────────────────────

def _build_bullet_suggestion(kw, resume_text):
    """Build a resume-specific bullet suggestion for a missing ATS keyword."""
    # Find the most semantically relevant resume sentence for this keyword
    closest = ""
    try:
        sentences = [s.strip() for s in re.split(r"[\n.]", resume_text) if len(s.strip()) > 25]
        sentences = [s for s in sentences if len(s.split()) >= 5 and not _SKIP_PATTERNS.search(s)][:60]
        if sentences:
            model = _scorer.get_model()
            kw_emb = model.encode(kw, convert_to_tensor=True)
            s_embs = model.encode(sentences, convert_to_tensor=True)
            scores = _scorer._util.cos_sim(kw_emb, s_embs)[0]
            best_idx = int(scores.argmax())
            if float(scores[best_idx]) > 0.22:
                closest = sentences[best_idx].strip().rstrip(".")
    except Exception:
        pass

    def _ctx(base):
        if closest:
            snippet = closest[:68] + ("…" if len(closest) > 68 else "")
            return f"{base} — draw from: \"{snippet}\""
        return base

    SUGGESTIONS = {
        "python":             _ctx("Automated workflow using Python, reducing manual effort and improving consistency"),
        "sql":                _ctx("Queried database using SQL to analyze key metrics, surfacing insights that drove a specific decision"),
        "excel":              _ctx("Built Excel model tracking KPIs for the team, enabling faster reporting and planning"),
        "tableau":            _ctx("Designed Tableau dashboard visualizing performance metrics for stakeholders, enabling data-driven decisions"),
        "data analysis":      _ctx("Analyzed dataset to identify trends in a key area, contributing to a measurable business outcome"),
        "project management": _ctx("Managed project from initiation through delivery, coordinating stakeholders and meeting all milestones"),
        "machine learning":   _ctx("Applied machine learning model to predict an outcome, improving accuracy over the previous approach"),
        "aws":                _ctx("Deployed application on AWS, achieving meaningful improvement in reliability or cost"),
        "marketing":          _ctx("Led marketing initiative targeting a specific audience, driving measurable growth in a key metric"),
        "financial modeling": _ctx("Built financial model to forecast revenue or costs, used by leadership to guide a major decision"),
        "communication":      _ctx("Presented complex findings to cross-functional stakeholders, aligning teams on a key decision"),
        "leadership":         _ctx("Led team through an initiative, setting clear goals and delivering the result on schedule"),
    }

    return SUGGESTIONS.get(kw, _ctx(f"Demonstrate {kw}: action verb + specific context + measurable result"))

ATS_FORMATTING_TIPS = [
    "Use a single-column layout — multi-column resumes often break ATS parsing.",
    "Save as .docx or plain .pdf (not image-based). Avoid tables and text boxes.",
    "Use standard section headers: 'Work Experience', 'Education', 'Skills'. Avoid creative labels.",
    "Spell out acronyms at least once: 'Application Programming Interface (API)'.",
    "Put your contact info in the body, not a header/footer — ATS often skips those.",
    "Match the exact job title somewhere in your resume if you legitimately can.",
]


# ── Skill classification: hard vs soft ───────────────────────────
_SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "collaboration", "problem solving",
    "problem-solving", "critical thinking", "time management", "adaptability",
    "creativity", "attention to detail", "organization", "interpersonal",
    "presentation", "public speaking", "negotiation", "conflict resolution",
    "decision making", "decision-making", "emotional intelligence", "empathy",
    "mentoring", "coaching", "facilitation", "active listening", "stakeholder management",
    "cross-functional", "multitasking", "prioritization", "work ethic",
    "self-motivated", "proactive", "analytical thinking", "strategic thinking",
    "written communication", "verbal communication", "fast learner", "detail-oriented",
}


def ats_scan(resume_text, job_description):
    """
    Detailed ATS analysis.
    Returns dict: score, found_keywords, missing_keywords,
                  missing_hard, missing_soft,
                  suggested_bullets, formatting_tips, verdict
    """
    from resume_parser import COMMON_SKILLS
    import re as _re

    jd_lower  = job_description.lower()
    res_lower = resume_text.lower()

    # Extract all meaningful phrases from job description
    # Also pull key noun phrases (2-3 word combinations) not just single skills
    jd_words = set(_re.findall(r"\b[a-z][a-z]+\b", jd_lower))
    STOP = {"and", "the", "for", "with", "this", "that", "have", "will",
            "your", "our", "are", "you", "we", "to", "of", "in", "a",
            "an", "or", "is", "it", "at", "be", "as", "on", "by", "do"}
    meaningful = {w for w in jd_words if w not in STOP and len(w) > 3}

    found_keywords = sorted([s for s in COMMON_SKILLS if s in jd_lower and s in res_lower])
    missing_keywords = sorted([s for s in COMMON_SKILLS if s in jd_lower and s not in res_lower])

    # Job-specific non-COMMON_SKILLS terms present in JD but not resume
    extra_missing = [w for w in meaningful
                     if w not in {s.replace(" ", "") for s in COMMON_SKILLS}
                     and w in jd_lower and w not in res_lower
                     and len(w) > 4][:10]

    # Score: base from keyword match + semantic bonus
    total_jd_skills = len(found_keywords) + len(missing_keywords)
    keyword_score = int((len(found_keywords) / total_jd_skills * 100)) if total_jd_skills else 50

    from scorer import score_job
    semantic_score = score_job(resume_text, job_description)
    final_score = int(keyword_score * 0.5 + semantic_score * 0.5)

    # Suggest resume bullets for top missing keywords — use actual resume context
    suggested_bullets = []
    for kw in missing_keywords[:6]:
        suggestion = _build_bullet_suggestion(kw, resume_text)
        if suggestion:
            suggested_bullets.append({
                "keyword": kw,
                "suggested_bullet": suggestion,
            })

    # Verdict
    if final_score >= 75:
        verdict = ("strong", "Strong match. Your resume should pass ATS and reach a human reviewer.")
    elif final_score >= 50:
        verdict = ("medium", "Moderate match. Add the missing keywords below before applying.")
    else:
        verdict = ("weak", "Weak match. Consider whether this role fits your current profile, or tailor heavily.")

    # Split missing keywords into hard skills vs soft skills
    missing_hard = [k for k in missing_keywords if k not in _SOFT_SKILLS]
    missing_soft = [k for k in missing_keywords if k in _SOFT_SKILLS]
    # Also check extra_missing for soft signals
    extra_soft = [k for k in extra_missing if any(s in k for s in
                  ["communicat","collaborat","leadership","teamwork","interpersonal","proactive"])]
    missing_soft = sorted(set(missing_soft + extra_soft))

    # Cliché detector — flag empty buzzwords in the resume
    _CLICHES = [
        "results-driven", "results driven", "team player", "detail-oriented",
        "detail oriented", "passionate about", "go-getter", "go getter",
        "dynamic professional", "hard-working", "hard working", "self-motivated",
        "self motivated", "out-of-the-box", "think outside the box",
        "people person", "strong work ethic", "proven track record",
        "excellent communication skills", "fast learner", "quick learner",
    ]
    cliches_found = [c for c in _CLICHES if c in res_lower]

    return {
        "score":             final_score,
        "keyword_score":     keyword_score,
        "semantic_score":    semantic_score,
        "found_keywords":    found_keywords,
        "missing_keywords":  missing_keywords,
        "missing_hard":      missing_hard,
        "missing_soft":      missing_soft,
        "extra_missing":     extra_missing,
        "suggested_bullets": suggested_bullets,
        "formatting_tips":   ATS_FORMATTING_TIPS,
        "verdict":           verdict,
        "cliches":           cliches_found,
    }


# ── Interview Prep ───────────────────────────────────────────────

BEHAVIORAL_QUESTIONS = [
    ("Tell me about a time you had to analyze a large amount of data to make a decision.",
     "Use STAR format. Draw from your actual experience — a data project, reporting work, or analytical task. Quantify the outcome if possible.",
     "Behavioral"),
    ("Describe a situation where you had to lead a team under pressure.",
     "Use STAR format. Any leadership experience works — managing a project, mentoring a colleague, or coordinating a cross-functional effort.",
     "Behavioral"),
    ("Tell me about a time you had to adapt quickly to a new environment or challenge.",
     "Use STAR format. Think about: a new role, a sudden scope change, a new tool or process you had to learn fast, or an unfamiliar team.",
     "Behavioral"),
    ("Give an example of when you took initiative on a project without being asked.",
     "Use STAR format. Think about a process you improved, a problem you identified and solved, or a project you proposed and drove.",
     "Behavioral"),
    ("Describe a time you had to communicate complex information to a non-technical audience.",
     "Use STAR format. Any example where you translated data, technical work, or a complex recommendation into clear, actionable terms.",
     "Behavioral"),
]

ROLE_QUESTIONS = {
    "analyst": [
        ("Walk me through how you would approach analyzing a new dataset you've never seen before.",
         "Talk about cleaning, exploring distributions, looking for nulls, then forming hypotheses. Mention pandas/SQL/Excel.", "Technical"),
        ("What metrics would you track to measure the success of [product/campaign]?",
         "Ask clarifying questions first. Then framework: leading vs lagging indicators, business goals.", "Technical"),
        ("How comfortable are you with SQL? Walk me through a query you've written.",
         "Describe a real query from your actual experience — joins, aggregations, filtering. Be specific about what you queried and what insight you surfaced.", "Technical"),
    ],
    "marketing": [
        ("How would you run an A/B test for a new campaign?",
         "Cover: hypothesis, control/variant, sample size, significance threshold, measurement.", "Technical"),
        ("What channels would you prioritize for a B2C brand with a limited budget?",
         "SEO, email, and organic social for low-cost. Show you understand CAC and LTV.", "Technical"),
        ("How do you stay current on marketing trends?",
         "Mention industry newsletters, podcasts, or communities you follow. Name 1-2 specific sources — it signals genuine interest.", "Situational"),
    ],
    "finance": [
        ("Walk me through a DCF model.",
         "Project FCFs, terminal value, discount by WACC. Reference any financial modeling you've done — even academic projects count.", "Technical"),
        ("What's happening in the markets right now that concerns you most?",
         "Pick a real macro theme: interest rates, AI sector valuation, geopolitical risks. Show you follow markets.", "Situational"),
        ("How would you value a company with negative earnings?",
         "Revenue multiples, EV/EBITDA comps, precedent transactions, option value for early stage.", "Technical"),
    ],
    "engineer": [
        ("Walk me through how you'd design a scalable data pipeline.",
         "Cover ingestion, transformation, storage, scheduling, and failure handling. Reference a real system you've built.", "Technical"),
        ("How do you handle API rate limits in production?",
         "Cover: caching responses, exponential backoff, request queuing, and circuit breakers. Reference a specific API integration you've implemented.", "Technical"),
        ("What's your approach to debugging a system that's silently failing?",
         "Cover: structured logging, monitoring/alerting, unit tests for edge cases, and reproducing the failure locally.", "Technical"),
    ],
    "operations": [
        ("How would you prioritize tasks when everything feels urgent?",
         "Eisenhower matrix or impact/effort framework. Show structured thinking.", "Situational"),
        ("Describe a process you identified as inefficient and how you improved it.",
         "Use STAR format. Think about: a reporting process you automated, a workflow you streamlined, or a recurring task you improved. Quantify time saved if possible.", "Behavioral"),
    ],
    "general": [
        ("Why do you want to work here?",
         "Research the company before. Mention something specific — a product, mission, recent news.", "Situational"),
        ("Where do you see yourself in 5 years?",
         "Show ambition + relevance to the role. Don't be too specific — growth within the field.", "Situational"),
    ],
}

CLOSING_QUESTIONS = [
    ("Why should we hire you over other candidates?",
     "Lead with your top 2-3 differentiators: a specific technical skill, a demonstrated result, and something about your approach that sets you apart. Be direct and confident — this is not the time to hedge.", "Closing"),
    ("Do you have any questions for us?",
     "Always ask at least 2. Good ones: 'What does success look like in the first 90 days?' and 'What's the team's biggest challenge right now?'", "Closing"),
]


def generate_interview_questions(profile, job):
    """
    Generate ~10 tailored interview questions with hints personalized to the resume.
    Returns list of {question, hint, type}
    """
    role_family = _detect_role_family(job.get("title", ""))
    jd = job.get("description", "").lower()
    company = job.get("company", "this company")
    resume_text = profile.get("raw_text", "")

    questions = []

    # Role-specific technical questions
    role_qs = ROLE_QUESTIONS.get(role_family, ROLE_QUESTIONS["general"])
    for q, hint, qtype in role_qs[:3]:
        questions.append({
            "question": q.replace("[company]", company),
            "hint": hint,
            "type": qtype,
        })

    # Behavioral from universal set — pick 3 most relevant to JD, then
    # personalize each hint with the closest matching resume bullet
    model = _scorer.get_model()
    bq_texts = [q for q, _, _ in BEHAVIORAL_QUESTIONS]
    jd_emb = model.encode(jd[:400], convert_to_tensor=True)
    bq_embs = model.encode(bq_texts, convert_to_tensor=True)
    scores = _scorer._util.cos_sim(jd_emb, bq_embs)[0]
    top_bq = scores.argsort(descending=True)[:min(3, len(bq_texts))]
    for i in top_bq:
        q, hint, qtype = BEHAVIORAL_QUESTIONS[i]
        relevant = _top_resume_sentences(resume_text, q, top_n=1)
        if relevant:
            snippet = relevant[0][:72].rstrip(".") + ("…" if len(relevant[0]) > 72 else "")
            hint = f"{hint} Your resume shows: \"{snippet}\" — build your STAR story around that."
        questions.append({"question": q, "hint": hint, "type": qtype})

    # Dynamic question from JD responsibilities, with resume context in the hint
    responsibilities = _extract_responsibilities(job.get("description", ""), max_items=2)
    for resp in responsibilities[:1]:
        relevant = _top_resume_sentences(resume_text, resp, top_n=1)
        hint = "Mirror their exact language when describing your experience."
        if relevant:
            snippet = relevant[0][:72].rstrip(".") + ("…" if len(relevant[0]) > 72 else "")
            hint += f" Draw from: \"{snippet}\""
        questions.append({
            "question": f"This role involves: '{resp[:120]}' — walk me through your most relevant experience.",
            "hint": hint,
            "type": "Role-Specific",
        })

    # Closing questions
    for q, hint, qtype in CLOSING_QUESTIONS:
        questions.append({"question": q, "hint": hint, "type": qtype})

    return questions[:12]
