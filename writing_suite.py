"""
writing_suite.py
-----------------
AI writing generators for every type of application content.
All template-based + semantic matching — no external API needed.

Covers:
  Application essays, short answers, diversity statements,
  emails (thank-you, follow-up, cold outreach, networking),
  profile copy (LinkedIn About, resume summary, personal bio),
  and a universal custom-prompt handler.
"""

import re

# ── Shared helpers ───────────────────────────────────────────────

def _skills_str(profile, job=None, max_n=4):
    if job:
        from scorer import get_skill_gaps
        matched, _ = get_skill_gaps(profile["raw_text"], job.get("description",""))
        skills = matched[:max_n] or profile["skills"][:max_n]
    else:
        skills = profile["skills"][:max_n]
    return ", ".join(skills) if skills else "analytical thinking and problem solving"


def _has(profile, *keywords):
    text = profile.get("raw_text","").lower()
    return any(k in text for k in keywords)


def _name(profile):   return profile.get("name") or "Candidate"
def _company(job):    return job.get("company","your company") if job else "your company"
def _role(job):       return job.get("title","this role") if job else "this role"


def _is_student(profile):
    raw = profile.get("raw_text","").lower()
    return any(w in raw for w in ["university","college","student","graduating","gpa","expected 20","class of"])


def _background_sentence(profile):
    """Return a 1-sentence background intro based on who the person actually is."""
    yrs    = profile.get("years_experience", 0)
    titles = profile.get("titles", [])
    title  = titles[0].title() if titles else ""
    skills = profile.get("skills", [])[:3]
    skills_str = ", ".join(skills) if skills else "analytical and problem-solving skills"

    if _is_student(profile):
        raw = profile.get("raw_text","")
        school = ""
        for line in raw.split("\n"):
            if any(w in line.lower() for w in ["university","college","institute","school"]):
                candidate = line.strip()
                if 3 < len(candidate) < 80 and not re.search(r"\d{4}", candidate):
                    school = candidate
                    break
        school_str = f"at {school}" if school else "currently in school"
        return f"I am a student {school_str} building hands-on experience in {skills_str}."
    elif yrs >= 5:
        return f"I am a {title or 'professional'} with {yrs}+ years of experience in {skills_str}."
    elif yrs >= 2:
        return f"I am a {title or 'professional'} with {yrs} years of hands-on experience in {skills_str}."
    elif yrs == 1:
        return f"I am a {title or 'professional'} with a year of experience in {skills_str}."
    else:
        return f"I am a {title or 'professional'} building deep expertise in {skills_str}."


def _intl_sentence(profile):
    raw = profile.get("raw_text","").lower()
    if any(w in raw for w in ["study abroad","studied abroad","international","global experience","overseas","cross-border","multicultural"]):
        return ("I also bring international experience that has strengthened my ability to collaborate "
                "across cultures and adapt to diverse business environments.")
    return ""


def _tech_sentence(profile):
    TECH_SKILLS = {
        "python","sql","r programming","java","javascript","typescript","scala","golang","rust","c++",
        "flask","django","fastapi","react","node.js","angular","vue",
        "pandas","numpy","scikit-learn","tensorflow","pytorch","dbt","airflow","spark",
        "tableau","power bi","looker",
        "aws","azure","gcp","docker","kubernetes","git","ci/cd","linux",
        "excel","financial modeling","salesforce","google analytics","jira",
    }
    tech = [s for s in profile.get("skills",[]) if s in TECH_SKILLS]
    if tech:
        tech_str = ", ".join(tech[:4])
        return (f"I have hands-on experience in {tech_str}, "
                "which allows me to work effectively across both strategic and technical challenges.")
    return ""


def _leadership_sentence(profile):
    raw = profile.get("raw_text","").lower()
    if any(w in raw for w in ["led","managed","supervised","captain","head of",
                               "coordinated","oversaw","mentored","directed","coached"]):
        return ("I have direct experience leading teams and cross-functional initiatives, "
                "which has taught me that strong outcomes depend on clear expectations, "
                "consistent communication, and giving people the context they need to do their best work.")
    return ""


def _best_bullet(profile):
    """Return the most metrics-rich bullet from the resume, for use in achievement stories."""
    raw = profile.get("raw_text","")
    lines = [l.strip().lstrip("•-* ") for l in raw.split("\n")
             if len(l.strip()) > 20 and re.search(r"\d", l)]
    if not lines:
        return ""
    # Prefer bullets with %, $, time-saved, or multipliers
    strong = [b for b in lines if re.search(r"\d+%|\$[\d,]+|\d+x|\d+ hours|\d+ minutes", b)]
    return (strong[0] if strong else lines[0])[:200]


def _recent_role(profile):
    """Return (title_str, company_str) for the most recent experience entry."""
    titles = profile.get("titles",[])
    title  = titles[0].title() if titles else "my current role"
    raw    = profile.get("raw_text","")
    # Scan for a line with date range or "Present"
    for line in raw.split("\n"):
        low = line.lower()
        if ("present" in low or re.search(r"20\d\d", line)) and len(line.strip()) > 5:
            parts = re.split(r"[,|\-–—@]", line)
            for p in parts:
                p = p.strip()
                if 3 < len(p) < 50 and not re.search(r"20\d\d|present", p.lower()):
                    return title, p
    return title, ""


# ── PROMPT CATALOG ───────────────────────────────────────────────

PROMPT_CATALOG = {
    # ── Application essays ──────────────────────────────────────
    "why_company": {
        "label": "Why do you want to work here?",
        "category": "Application Essays",
        "needs_job": True,
        "placeholder": "Optionally paste anything you know about the company culture, mission, or recent news…",
    },
    "why_role": {
        "label": "Why are you interested in this role?",
        "category": "Application Essays",
        "needs_job": True,
        "placeholder": "Paste the job description for a more tailored response…",
    },
    "tell_about_yourself": {
        "label": "Tell me about yourself",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "Optionally note the audience (recruiter screen, panel interview, networking event)…",
    },
    "challenge": {
        "label": "Describe a challenge you overcame",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "Optionally specify which experience to draw from (work, school, leadership)…",
    },
    "strengths": {
        "label": "What are your greatest strengths?",
        "category": "Application Essays",
        "needs_job": True,
        "placeholder": "",
    },
    "weakness": {
        "label": "What is your greatest weakness?",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "",
    },
    "five_years": {
        "label": "Where do you see yourself in 5 years?",
        "category": "Application Essays",
        "needs_job": True,
        "placeholder": "",
    },
    "achievement": {
        "label": "What is your greatest achievement?",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "",
    },
    "failure": {
        "label": "Describe a time you failed and what you learned",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "",
    },
    "teamwork": {
        "label": "Tell us about a time you worked in a team",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "",
    },
    "leadership_essay": {
        "label": "Describe your leadership experience",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "",
    },
    "unique_perspective": {
        "label": "What unique perspective do you bring?",
        "category": "Application Essays",
        "needs_job": True,
        "placeholder": "",
    },
    "diversity": {
        "label": "Diversity & Inclusion statement",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "Optionally specify what dimension to focus on (background, perspective, experience)…",
    },
    "additional_info": {
        "label": "Additional Information / Anything else we should know?",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "",
    },
    "custom_essay": {
        "label": "Custom question — paste any prompt",
        "category": "Application Essays",
        "needs_job": False,
        "placeholder": "Paste the exact question here…",
    },
    # ── Emails ──────────────────────────────────────────────────
    "thank_you": {
        "label": "Thank-you email (post-interview)",
        "category": "Emails",
        "needs_job": True,
        "placeholder": "Paste 1-2 things you discussed in the interview to personalize it…",
    },
    "follow_up": {
        "label": "Follow-up email (after applying)",
        "category": "Emails",
        "needs_job": True,
        "placeholder": "How long ago did you apply? Any recruiter name you have?",
    },
    "cold_outreach": {
        "label": "Cold outreach to hiring manager",
        "category": "Emails",
        "needs_job": True,
        "placeholder": "Paste anything you know about the hiring manager or team…",
    },
    "networking_msg": {
        "label": "LinkedIn networking message",
        "category": "Emails",
        "needs_job": True,
        "placeholder": "Note how you found them (mutual connection, their post, their company)…",
    },
    "referral_request": {
        "label": "Referral request to a contact",
        "category": "Emails",
        "needs_job": True,
        "placeholder": "How do you know this person? How well?",
    },
    "elevator_pitch": {
        "label": "Elevator pitch (30 / 60 / 90 sec)",
        "category": "Emails",
        "needs_job": False,
        "placeholder": "Context: networking event, phone screen, career fair, Zoom intro…",
    },
    "linkedin_rec_request": {
        "label": "LinkedIn recommendation request",
        "category": "Emails",
        "needs_job": False,
        "placeholder": "Who are you asking? Your relationship? What you'd like them to highlight?",
    },
    "rejection_feedback": {
        "label": "Rejection — request for feedback",
        "category": "Emails",
        "needs_job": True,
        "placeholder": "How far did you get? (phone screen, final round, etc.)",
    },
    # ── Profile copy ─────────────────────────────────────────────
    "linkedin_about": {
        "label": "LinkedIn 'About' section",
        "category": "Profile",
        "needs_job": False,
        "placeholder": "What roles are you targeting? Any specific industries?",
    },
    "resume_summary": {
        "label": "Resume headline / summary",
        "category": "Profile",
        "needs_job": False,
        "placeholder": "Target role or industry focus…",
    },
    "personal_bio": {
        "label": "Personal bio (portfolio / website)",
        "category": "Profile",
        "needs_job": False,
        "placeholder": "Tone: professional, casual, or hybrid?",
    },
}

CATEGORIES = ["Application Essays", "Emails", "Profile"]


# ── Generators ───────────────────────────────────────────────────

def _generate_with_claude(prompt_type: str, profile: dict, job: dict | None, extra_context: str) -> str | None:
    """
    Universal Claude-powered generator for any writing tool.
    Builds a rich, context-aware prompt from the catalog entry + profile + job.
    Returns text or None if Claude unavailable/failed.
    """
    try:
        from claude_ai import _call_claude, claude_available
        if not claude_available():
            return None

        catalog_entry = PROMPT_CATALOG.get(prompt_type, {})
        label = catalog_entry.get("label", prompt_type.replace("_", " ").title())
        category = catalog_entry.get("category", "")

        from claude_ai import _sanitize
        name = profile.get("name") or "the candidate"
        resume = _sanitize(profile.get("raw_text") or "", 3000)
        company = (job.get("company") or "") if job else ""
        role    = (job.get("title") or "")   if job else ""
        jd      = _sanitize(job.get("description") or "", 1200) if job else ""

        job_ctx = ""
        if role or company:
            job_ctx = f"\nTarget Role: {role}" + (f" at {company}" if company else "")
        if jd:
            job_ctx += f"\n\nJob Description (excerpt):\n{jd}"
        if extra_context and extra_context.strip():
            job_ctx += f"\n\nAdditional context from user: {extra_context.strip()}"

        # Per-category length and style guidance
        length_guide = {
            "Application Essays": "150–250 words unless the prompt implies shorter",
            "Emails": "3–4 short paragraphs, under 180 words total",
            "Profile": "150–220 words, first person, conversational but professional",
        }.get(category, "150–220 words")

        # Special handling for elevator pitch — produce 3 lengths
        if prompt_type == "elevator_pitch":
            extra_instruction = (
                "Produce THREE versions:\n"
                "• 30-second version (~75 words)\n"
                "• 60-second version (~130 words)\n"
                "• 90-second version (~200 words)\n"
                "Label each clearly. Write as spoken speech, first person, natural rhythm."
            )
        elif prompt_type == "custom_essay":
            extra_instruction = (
                f"The custom question/prompt is: {extra_context.strip() or 'general essay question'}\n"
                "Answer it directly and specifically, drawing from real resume details."
            )
        else:
            extra_instruction = ""

        system = (
            "You are an expert career coach and professional writer specializing in job search content. "
            "Write specific, genuine, polished content that sounds like a real person — not a template. "
            "Always draw real details from the resume: actual companies, real skills, specific achievements. "
            "Never use brackets like [insert X] or placeholder text. Write complete, ready-to-use sentences."
        )

        user = f"""Write the following for {name}: {label}

CANDIDATE RESUME:
{resume}
{job_ctx}

Requirements:
- Use ONLY real details from the resume — actual company names, real skills, specific numbers/outcomes
- Never use placeholder brackets like [your name], [insert achievement], [X years], [Interviewer Name], etc.
- If you don't know someone's name, use "Hi," or a natural opener instead of brackets
- Sound like a confident, authentic human — not corporate or formulaic
- Length: {length_guide}
- Tone: professional but warm, direct, not sycophantic
{extra_instruction}

Write {label} now:"""

        return _call_claude(system, user, max_tokens=900)
    except Exception:
        return None


def generate(prompt_type, profile, job=None, extra_context=""):
    """
    Main dispatcher. Tries Claude first; falls back to local templates.
    Returns (title, body) tuple.
    """
    catalog_entry = PROMPT_CATALOG.get(prompt_type, {})
    title = catalog_entry.get("label", "Generated Content")

    # Always try Claude first — it produces genuinely personalized output
    claude_result = _generate_with_claude(prompt_type, profile, job, extra_context)
    if claude_result:
        try:
            import analytics as _a
            _a.track("cover_letter_gen", meta=prompt_type)
        except Exception:
            pass
        return title, claude_result

    # Template fallback
    fn = _GENERATORS.get(prompt_type)
    if fn:
        return fn(profile, job, extra_context)
    return ("Custom Response", _custom(profile, job, extra_context))


# ── Application Essays ───────────────────────────────────────────

def _why_company(profile, job, extra):
    company    = _company(job)
    role       = _role(job)
    skills     = _skills_str(profile, job)
    background = _background_sentence(profile)
    tech       = _tech_sentence(profile)
    intl       = _intl_sentence(profile)
    extra_para = f"\n\n{extra.strip()}" if extra.strip() else ""

    return ("Why This Company", f"""
{company} stands out to me because it sits at the intersection of {skills} and real business impact — which is exactly where I want to build my career.

{background} {tech} {intl}

What draws me to {company} specifically is the opportunity to bring that combination to a team that takes both seriously. The {role} role maps closely to the direction I am building toward — where analytical rigor meets real business judgment in a fast-moving environment.{extra_para}

I would be genuinely excited to contribute to {company}'s work and grow alongside a team doing meaningful things.
""".strip())


def _why_role(profile, job, extra):
    role       = _role(job)
    company    = _company(job)
    skills     = _skills_str(profile, job)
    background = _background_sentence(profile)
    tech       = _tech_sentence(profile)

    # Pull most relevant JD line
    jd = job.get("description","") if job else ""
    resp_line = ""
    if jd:
        for line in jd.split("\n"):
            l = line.strip().lstrip("•-–")
            if len(l.split()) > 8 and any(v in l.lower() for v in
                    ("analyze","build","develop","manage","support","coordinate","design","drive","own")):
                resp_line = l[:120]
                break

    return ("Why This Role", f"""
The {role} role at {company} caught my attention because it asks for exactly the combination I have been building: {skills}, applied to real business problems.

{background} {tech}

{"Specifically, the responsibility to " + resp_line.lower() + " aligns directly with what I find most energizing in my work." if resp_line else "The day-to-day scope of this role aligns with what I find most energizing — problems that require both structured thinking and the flexibility to communicate findings clearly across teams."}

I am at a stage where I want to go deep on a specific problem set with a strong team, and this role at {company} feels like the right environment to do that.
""".strip())


def _tell_about_yourself(profile, job, extra):
    name       = _name(profile)
    background = _background_sentence(profile)
    tech       = _tech_sentence(profile)
    intl       = _intl_sentence(profile)
    leader     = _leadership_sentence(profile)
    target     = _role(job) if job else "my target roles"
    company    = _company(job) if job else "forward-thinking organizations"
    best       = _best_bullet(profile)

    proof_line = f"\n\nFor example: {best}" if best else ""

    return ("Tell Me About Yourself", f"""
{background}

{tech}

{leader}

{intl}{proof_line}

Right now I am targeting {target} at {company}, where I can apply that combination directly and keep building fast. Outside of work, I stay engaged with trends in my field and look for ways to keep sharpening the skills that matter most.
""".strip())


def _challenge(profile, job, extra):
    background = _background_sentence(profile)
    tech       = _tech_sentence(profile)
    best       = _best_bullet(profile)
    context    = extra.strip() or "a technically complex project early in my career"

    return ("Challenge Essay", f"""
One of the more meaningful challenges I have faced was [describe the challenge — a difficult project, learning curve, or obstacle] around {context}.

The situation required me to [describe what made it hard: tight deadline, unfamiliar tools, team misalignment, scope creep, or other specific friction].

My approach was to break the problem into the smallest possible actionable pieces, stay disciplined about daily progress, and treat each setback as information rather than failure. I also made sure to communicate status clearly so stakeholders were never surprised.{(' Concretely: ' + best) if best else ''}

The outcome was [describe the result]. The deeper lesson I carried forward: the gap between "I can't do this" and "I can do this" is almost always structured persistence and the willingness to ask for help at the right moment.

[Customize: replace bracketed sections with your specific story for maximum impact.]
""".strip())


def _strengths(profile, job, extra):
    skills     = _skills_str(profile, job, max_n=3)
    company    = _company(job) if job else "your team"
    background = _background_sentence(profile)
    best       = _best_bullet(profile)

    return ("Greatest Strengths", f"""
My three strongest assets are analytical thinking, execution, and adaptability.

On the analytical side: I naturally break complex problems into structured frameworks, whether I am evaluating a business decision or debugging a system. {background} I have found that this approach consistently leads to clearer outcomes than intuition alone.

On execution: I have a strong track record of finishing what I start, independently and on time. {('One example: ' + best) if best else 'My work in ' + skills + ' demonstrates this directly.'}

On adaptability: I move quickly in new environments and build context fast. I have operated effectively across [technical / cross-functional / fast-paced] settings, and that flexibility is exactly what roles at {company} tend to require.
""".strip())


def _weakness(profile, job, extra):
    return ("Greatest Weakness", f"""
My most honest answer is that I can be impatient with slow or unclear processes when I can see a faster path forward. When I am deep in a project, I tend to move quickly and sometimes have to remind myself to pause, document, and communicate progress to others who are operating at a different pace.

I have been actively working on this. I have gotten better at building in explicit checkpoints — briefly summarizing where I am and what decisions I made before moving to the next phase — which has made me easier to collaborate with and made my work more reproducible.

It is still something I watch, but it has genuinely improved over time.
""".strip())


def _five_years(profile, job, extra):
    company    = _company(job) if job else "a high-growth organization"
    role       = _role(job) if job else "this type of role"
    background = _background_sentence(profile)
    skills     = _skills_str(profile, job, max_n=2)

    return ("5-Year Vision", f"""
In five years I want to be a decision-maker who is equally trusted for business judgment and technical fluency — someone who can walk into a room with a complex problem and walk out with a clear, defensible strategy.

More specifically, I see myself taking on increasing responsibility within {company}'s direction — moving from executing well in the {role} to leading a team or owning a function end-to-end. I am the kind of person who earns trust quickly and moves fast, and I expect that trajectory to continue.

I am also paying close attention to how {skills} are evolving — the professionals who will be most valuable over the next decade are those who understand both the tools and the business context they operate in. I am actively building toward that intersection.
""".strip())


def _achievement(profile, job, extra):
    best       = _best_bullet(profile)
    title, co  = _recent_role(profile)
    tech       = _tech_sentence(profile)
    background = _background_sentence(profile)

    if best:
        return ("Greatest Achievement", f"""
My most significant professional achievement is: {best}

{background}

The reason I am most proud of this is not just the outcome — it is what the process revealed. To get there, I had to [describe the approach: technical work, cross-functional coordination, creative problem-solving, persistence]. {tech}

What I took from it: the ability to combine [your key skills] with clear communication and structured follow-through is what separates good work from great work. I want to replicate that pattern — at larger scale and with higher stakes — in my next role.

[Tip: Add 1–2 sentences of context about the project scope, constraints, or team size to make this more concrete for the reader.]
""".strip())
    else:
        return ("Greatest Achievement", f"""
[Describe your most meaningful professional or academic achievement here.]

The context: [What was the situation? What were the constraints, stakes, or difficulty level?]

My contribution: [What specifically did you do? What tools, skills, or approach did you use?] {tech}

The result: [Quantify the outcome — time saved, revenue impacted, score achieved, team size led, etc.]

Why this matters: this achievement reflects [key trait: problem-solving / leadership / technical skill / persistence] that I bring to every role I am in.

[Tip: Fill in the brackets above with your real story — the more specific, the more memorable.]
""".strip())


def _failure(profile, job, extra):
    return ("Failure Essay", f"""
[Replace this with your real story — the more specific, the more credible]

Early in [a project / a role / a team setting], I [describe what happened: misread a deadline, miscommunicated with a stakeholder, underestimated scope, made a technical error]. The result was [describe the consequence: missed deadline, extra work for the team, a redo].

I was frustrated with myself, but what I did next mattered more than the failure itself: [describe your response — how you communicated, fixed it, took accountability, or rebuilt trust].

What I changed afterward: [describe the specific habit or process change you made]. That change has prevented the same situation from recurring in every context since.

The lesson: failure is most useful when you treat it as data, not judgment. I have gotten genuinely better at [the thing you failed at] because of this experience.

[Tip: Pick a real story from your background — even a small one is fine. Interviewers want accountability and self-awareness, not perfection.]
""".strip())


def _teamwork(profile, job, extra):
    title, co  = _recent_role(profile)
    intl       = _intl_sentence(profile)

    return ("Teamwork Essay", f"""
The clearest example of effective teamwork I can point to is [describe a specific project or situation where you collaborated with a team — at {co or 'work'}, school, or in a volunteer or extracurricular context].

The challenge was not just the task itself — it was [describe the team dynamic challenge: different working styles, unclear ownership, competing priorities, communication gaps, or a tight deadline].

My specific contribution was [describe what you did: proposed a process, took on a coordination role, resolved a conflict, clarified scope, or kept momentum]. I found that the most effective thing I could do was [specific action] rather than [what might have been the default approach].

We [describe the outcome]. More importantly, I left with a clearer picture of what actually makes teams work — which is not just having the right people, but having an explicit shared understanding of what success looks like.

[Tip: Replace bracketed sections with specifics from your own experience. The more concrete, the better.]
""".strip())


def _leadership_essay(profile, job, extra):
    title, co  = _recent_role(profile)
    leader     = _leadership_sentence(profile)
    best       = _best_bullet(profile)

    return ("Leadership Essay", f"""
The leadership experience that shaped me most was [describe the situation: leading a team, managing a project, mentoring someone, or stepping up in a crisis].

[If you have direct management experience]: I led a team of [N] people through [describe the challenge or project]. I inherited [describe initial situation] and focused my energy on [your approach: setting clear goals, improving communication, building accountability, removing blockers].

{leader}

The result was [describe the outcome]. {('Concretely: ' + best) if best else ''}

What I took from it: leadership is less about the person at the front of the room and more about the conditions you create for others to do their best work. I try to bring that principle to every team context I am in.

[Tip: Even informal leadership — running a meeting, mentoring a junior colleague, or driving a cross-functional initiative — counts here. Pick a real example from your experience.]
""".strip())


def _unique_perspective(profile, job, extra):
    company    = _company(job) if job else "your team"
    tech       = _tech_sentence(profile)
    intl       = _intl_sentence(profile)
    background = _background_sentence(profile)
    skills     = _skills_str(profile, job)

    return ("Unique Perspective", f"""
The perspective I bring that is genuinely unusual is [describe your specific combination — technical + business, international + analytical, creative + data-driven, or other rare pairing].

{background}

{tech}

{intl}

Most candidates for roles like this have either [one side of your combination] or [the other] — rarely both. That combination means I can work fluently across functions, communicate with both technical and non-technical stakeholders, and bring [a specific lens] to problems that are often viewed narrowly.

At {company}, I believe that translates to someone who can bridge teams, operate in ambiguity, and deliver work that is both rigorous and actionable.

[Tip: Your unique perspective is usually the intersection of two things you do well that most people only have one of. Think about what makes your background unusual for someone in your target role.]
""".strip())


def _diversity(profile, job, extra):
    intl = _intl_sentence(profile)

    return ("Diversity & Inclusion Statement", f"""
My perspective on diversity is shaped more by experience than theory.

{intl if intl else "[Describe a relevant personal experience — navigating different cultural or professional environments, being underrepresented in a field, or collaborating across difference]."}

What that experience taught me is that the most creative and resilient teams are those where people's assumptions are regularly challenged — not combatively, but naturally, the way it happens when people with genuinely different backgrounds work on the same problem.

I try to bring that belief into every team I join: asking questions that surface hidden assumptions, looking for the perspective that is not yet in the room, and recognizing when my own frame is too narrow.

I am drawn to organizations that share this view — because I have seen firsthand that it is not just the right thing to do, it is the strategically smart thing.
""".strip())


def _additional_info(profile, job, extra):
    tech       = _tech_sentence(profile)
    background = _background_sentence(profile)
    skills     = _skills_str(profile)

    return ("Additional Information", f"""
I want to flag one thing that may not be immediately obvious from my resume: [describe your strongest differentiator that is hard to capture in a resume — a portfolio project, technical depth, a unique combination of skills, or an unusual career path].

{background}

{tech if tech else "My core skills include " + skills + "."}

I mention this because it is directly relevant to any role involving [your target domain], and because it represents a significant investment of time and intentionality outside of my formal credentials. I believe it is my strongest differentiator and I want it to be visible.

I am happy to discuss further, share examples, or demonstrate any of this directly if it would be useful context.
""".strip())


def _custom(profile, job, extra):
    """Universal handler for any custom prompt."""
    if not extra.strip():
        return ("Response", "Please paste the question in the context box above and regenerate.")

    company    = _company(job) if job else "your organization"
    role       = _role(job) if job else "this role"
    skills     = _skills_str(profile, job)
    tech       = _tech_sentence(profile)
    intl       = _intl_sentence(profile)
    background = _background_sentence(profile)
    name       = _name(profile)
    question   = extra.strip().rstrip("?") + "?"

    return ("Custom Response", f"""
[Question: {question}]

{background}

{tech}

{intl}

In the context of {company} and the {role} role, my answer specifically is: [describe your response, drawing on {skills} and your direct experience].

I approach this by [describe your method or philosophy], which has consistently led to [describe the type of outcome this produces].

[Note: Replace the bracketed sections with specifics from your background. The framework above will give you a solid foundation — the real story is what makes it memorable.]
""".strip())


# ── Emails ───────────────────────────────────────────────────────

def _thank_you(profile, job, extra):
    company    = _company(job)
    role       = _role(job)
    name       = _name(profile)
    convo_note = extra.strip() if extra.strip() else "our conversation about the team's priorities and what success looks like in this role"

    return ("Thank-You Email", f"""Subject: Thank You — {role} Interview at {company}

Hi [Interviewer Name],

Thank you for taking the time to speak with me today about the {role} role at {company}. I genuinely enjoyed the conversation — particularly {convo_note}.

It reinforced my enthusiasm for this opportunity. The combination of the role's scope and the team's approach to [specific thing you discussed] is exactly the kind of environment where I do my best work.

I am confident I can contribute from day one and would be excited to bring my background in [your top 2 skills] to the team.

Please don't hesitate to reach out if you need any additional information. I look forward to hearing about next steps.

Best,
{name}
""".strip())


def _follow_up(profile, job, extra):
    company = _company(job)
    role    = _role(job)
    name    = _name(profile)
    timing  = extra.strip() or "two weeks ago"

    return ("Follow-Up Email", f"""Subject: Following Up — {role} Application at {company}

Hi [Recruiter/Hiring Manager Name],

I wanted to follow up on my application for the {role} position at {company}, which I submitted {timing}. I remain very interested in the opportunity and wanted to confirm that my materials came through.

I am confident I would be a strong fit for the team — particularly given my background in [your top skill] and [second relevant skill or experience]. I would welcome any update you are able to share about the timeline.

Thank you for your time and consideration.

Best,
{name}
""".strip())


def _cold_outreach(profile, job, extra):
    company    = _company(job)
    role       = _role(job)
    name       = _name(profile)
    skills     = _skills_str(profile, job, max_n=2)
    background = _background_sentence(profile)
    context    = extra.strip() or "your work at " + company

    return ("Cold Outreach Email", f"""Subject: {role} Interest — {name}

Hi [Name],

I came across {context} and wanted to reach out directly. {background}

My background in {skills} is directly relevant to the kind of work your team is doing, and {company} has been on my radar for a while as a place where I could contribute meaningfully.

I would genuinely value 15 minutes of your time — not to pitch myself formally, just to learn more about how your team operates and what you look for.

No pressure if now isn't a good time. Either way, thank you for the work you're doing at {company}.

Best,
{name}
""".strip())


def _networking_msg(profile, job, extra):
    company = _company(job)
    role    = _role(job)
    name    = _name(profile)
    context = extra.strip() or "your profile and your work at " + company

    return ("LinkedIn Networking Message", f"""Hi [Name],

I came across {context} and wanted to connect. I'm a {role.lower() if role != 'this role' else 'professional'} with a strong interest in {company} and the work your team is doing.

I'd love to hear about your experience there if you ever have 15 minutes — no ask beyond that.

Best, {name}
""".strip())


def _referral_request(profile, job, extra):
    company      = _company(job)
    role         = _role(job)
    name         = _name(profile)
    relationship = extra.strip() or "we have crossed paths professionally"

    return ("Referral Request", f"""Hi [Name],

I hope you're doing well! I wanted to reach out because I'm applying for the {role} position at {company} and noticed you're connected there.

[Context: {relationship}.]

I've put together what I think is a strong application, and I genuinely believe this role is a great fit for my background. If you felt comfortable passing along my name or resume to the hiring team, I would be incredibly grateful — even just a note that you know me would help.

Completely understand if it's not a good time or you don't feel comfortable. Either way, I appreciate you and will keep you posted.

Best,
{name}
""".strip())


# ── Profile copy ─────────────────────────────────────────────────

def _linkedin_about(profile, job, extra):
    skills     = _skills_str(profile, max_n=5)
    tech       = _tech_sentence(profile)
    intl       = _intl_sentence(profile)
    background = _background_sentence(profile)
    target     = extra.strip() or (_role(job) if job else "my next opportunity")
    yrs        = profile.get("years_experience", 0)
    best       = _best_bullet(profile)

    proof_line = f"\n\nProof: {best}" if best else ""

    return ("LinkedIn About Section", f"""
{background}

{tech}

{intl}

What I bring to every role:
- Applying {skills} to complex, ambiguous problems
- Communicating clearly across technical and non-technical audiences
- Delivering work that creates measurable impact, not just activity{proof_line}

Currently open to {target} where I can contribute from day one and keep growing fast.

Skills: {skills}
Open to: {'internships, entry-level roles' if yrs < 2 else 'new opportunities'} and conversations.
""".strip())


def _resume_summary(profile, job, extra):
    skills     = _skills_str(profile, job, max_n=4)
    target     = extra.strip() or (_role(job) if job else "my target role")
    yrs        = profile.get("years_experience", 0)
    titles     = profile.get("titles", [])
    title      = titles[0].title() if titles else "Professional"
    intl_flag  = "International experience. " if _intl_sentence(profile) else ""
    tech_flag  = ""
    if _has(profile,"python","sql","r","tableau"):
        tech_flag = "Strong technical depth in data and analysis. "

    exp_str = f"{yrs}+ years" if yrs >= 2 else ("Entry-level" if yrs < 1 else "1 year")

    return ("Resume Summary", f"""
{exp_str} {title} with expertise in {skills}. {tech_flag}{intl_flag}Targeting {target} where analytical rigor and cross-functional communication drive results.

Core skills: {skills}
""".strip())


def _personal_bio(profile, job, extra):
    name       = _name(profile)
    tone       = extra.strip().lower() if extra.strip() else "professional"
    tech       = _tech_sentence(profile)
    intl       = _intl_sentence(profile)
    background = _background_sentence(profile)
    skills     = _skills_str(profile, max_n=3)
    titles     = profile.get("titles", [])
    title      = titles[0].title() if titles else "professional"

    if "casual" in tone:
        return ("Personal Bio", f"""
Hey, I'm {name} — a {title} who genuinely enjoys the intersection of {skills} and real-world problem-solving.

{tech.replace('I have built hands-on technical depth in', 'I spend a lot of time working with')}

When I'm not doing that, I'm [one sentence about your interests outside work — reading, sports, a side project, travel].

Currently looking for roles where I can apply this combination somewhere it actually matters.
""".strip())
    else:
        return ("Personal Bio", f"""
{name} is a {title} with experience in {skills}. {tech} {intl}

Known for [describe 2 key traits — e.g., combining technical rigor with clear communication, or moving fast without breaking things], {name} brings a mix of [analytical / creative / strategic / technical] thinking to every problem.

Currently seeking {'internship and entry-level' if _is_student(profile) else 'new'} opportunities in [your target area].
""".strip())


# ── Extra Email Generators ───────────────────────────────────────

def _elevator_pitch(profile, job, extra):
    name       = _name(profile)
    background = _background_sentence(profile)
    tech       = _tech_sentence(profile)
    best       = _best_bullet(profile)
    target     = _role(job) if job else "my next opportunity"
    skills     = _skills_str(profile, job, max_n=3)
    context    = extra.strip() or "networking event"

    s30 = (
        f"Hi, I'm {name}. "
        f"{background.split('.')[0]}. "
        f"I'm targeting {target} — would love to connect."
    )

    s60 = (
        f"Hi, I'm {name}. {background} "
        f"I specialize in {skills}"
        + (f", and my biggest recent win: {best[:100]}." if best else ".")
        + f" I'm actively looking for {target} — happy to swap contact info."
    )

    s90 = (
        f"Hi, I'm {name}. {background} {tech} "
        + (f"One thing I'm proud of: {best[:120]}. " if best else "")
        + f"I'm targeting {target} where I can combine that depth with real business impact. "
        + ("I'd love to learn more about what you're working on — are you open to staying in touch?"
           if "network" in context.lower()
           else "Looking forward to learning more about this role.")
    )

    return ("Elevator Pitch", f"""30-SECOND VERSION
-----------------
{s30}

60-SECOND VERSION
-----------------
{s60}

90-SECOND VERSION (interviews / "tell me about yourself")
-----------------
{s90}

[Tip: Practice each out loud. 30s = introductions at events. 60s = recruiter screen opener. 90s = interview opener — fill in brackets with your real story.]
""".strip())


def _linkedin_rec_request(profile, job, extra):
    name    = _name(profile)
    context = extra.strip() or "our work together"

    return ("LinkedIn Recommendation Request", f"""Subject: Quick favor — LinkedIn recommendation?

Hi [Name],

I hope you're doing well! I wanted to reach out with a small ask.

I'm currently [searching for new opportunities / actively applying for X roles] and I'm building out my LinkedIn profile. I'd be incredibly grateful if you'd be willing to write a short recommendation based on {context}.

Specifically, if you could speak to [1–2 specific skills or qualities — e.g. "my ability to turn complex data into clear decisions" or "my leadership on the X project"], that would be incredibly valuable for anyone reviewing my profile.

Of course, I completely understand if now isn't a good time — zero pressure. I'm also happy to return the favor if you'd ever like one from me.

Thank you for even considering it.

Best,
{name}

---
[Tip: The more specific you are about what you'd like highlighted, the better the recommendation. Vague asks get generic results.]
""".strip())


def _rejection_feedback(profile, job, extra):
    company = _company(job)
    role    = _role(job)
    name    = _name(profile)
    stage   = extra.strip() or "the interview process"

    return ("Rejection — Feedback Request", f"""Subject: Thank You + Quick Question — {role} at {company}

Hi [Recruiter / Hiring Manager Name],

Thank you for letting me know about the decision on the {role} role. I appreciate you taking the time to consider my application and move me through {stage}.

I genuinely enjoyed learning about the team and what you're building at {company}. While I'm disappointed, I respect the decision completely.

One small ask: if you have a few minutes, I'd genuinely value any feedback on where my profile fell short or what would have made me a stronger candidate. I'm actively working to improve and even a sentence or two would help.

Completely understand if you're not able to share — no pressure at all. Either way, thank you for the experience and I hope our paths cross again.

Best,
{name}

---
[Tip: ~20% of recruiters will respond. Keep it short, gracious, and specific about what you're asking. This email is also about leaving a strong impression for future openings.]
""".strip())


# ── Dispatcher ───────────────────────────────────────────────────

_GENERATORS = {
    "why_company":        _why_company,
    "why_role":           _why_role,
    "tell_about_yourself":_tell_about_yourself,
    "challenge":          _challenge,
    "strengths":          _strengths,
    "weakness":           _weakness,
    "five_years":         _five_years,
    "achievement":        _achievement,
    "failure":            _failure,
    "teamwork":           _teamwork,
    "leadership_essay":   _leadership_essay,
    "unique_perspective": _unique_perspective,
    "diversity":          _diversity,
    "additional_info":    _additional_info,
    "custom_essay":       _custom,
    "thank_you":          _thank_you,
    "follow_up":          _follow_up,
    "cold_outreach":      _cold_outreach,
    "networking_msg":     _networking_msg,
    "referral_request":   _referral_request,
    "elevator_pitch":     _elevator_pitch,
    "linkedin_rec_request": _linkedin_rec_request,
    "rejection_feedback": _rejection_feedback,
    "linkedin_about":     _linkedin_about,
    "resume_summary":     _resume_summary,
    "personal_bio":       _personal_bio,
}
