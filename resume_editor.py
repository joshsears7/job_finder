import re
import math

# Detects certification-related content anywhere in resume text
_CERT_CONTENT_RE = re.compile(
    r"\b(certif(?:ied|ication|icate|ying)|comptia|pmp|cissp|cpa\b|cfa\b|"
    r"coursera|udemy|nanodegree|scrum master|series [0-9]+|"
    r"aws cert|azure cert|google cert|microsoft cert|"
    r"security\+|network\+|a\+|linux\+|pentest\+|"
    r"snowflake cert|tableau cert|databricks cert)\b",
    re.IGNORECASE
)

# ── Section map ────────────────────────────────────────────────
# Maps canonical section name → keyword list used by detect_sections().
SECTION_MAP = {
    "Summary":        ["summary", "objective", "profile", "about me", "professional summary",
                       "career summary", "overview", "personal statement"],
    "Experience":     ["experience", "employment", "work history", "professional experience",
                       "career history", "positions held", "work experience"],
    "Education":      ["education", "academic", "degree", "coursework", "academic background"],
    "Skills":         ["skills", "technical skills", "core competencies", "competencies",
                       "expertise", "proficiencies", "technologies", "tools"],
    "Projects":       ["projects", "personal projects", "academic projects",
                       "side projects", "portfolio", "selected projects"],
    "Certifications": ["certifications", "certificates", "licenses", "credentials",
                       "accreditations", "training", "certification"],
    "Leadership":     ["leadership", "activities", "campus involvement", "extracurricular activities",
                       "involvement", "organizations"],
    "Awards":         ["awards", "honors", "achievements", "recognition", "accomplishments",
                       "scholarships"],
    "Volunteer":      ["volunteer", "volunteering", "community service", "civic"],
    "Publications":   ["publications", "papers", "research", "articles", "presentations"],
    "Languages":      ["languages", "language skills"],
    "Interests":      ["interests", "hobbies"],
    "References":     ["references"],
}

# ── Section coaching tips ──────────────────────────────────────
SECTION_COACH = {
    "Summary": (
        "Write 1–2 sentences max — recruiters spend 6 seconds scanning; a paragraph gets skipped. "
        "Lead with the contrast or differentiator that makes you unusual, not a job title. "
        "Name something specific: a technology you've shipped, a market you know, a credential you've earned. "
        "End with your target direction. "
        "Avoid: 'results-driven', 'passionate', 'team player', 'seeking an opportunity' — these are invisible."
    ),
    "Experience": (
        "Experience is the most important section for recruiters and ATS systems. "
        "Every role should have 3–6 bullet points starting with a strong action verb. "
        "Format: 'Verb + task + result' — e.g. 'Reduced churn 18% by redesigning onboarding.' "
        "Quantify outcomes wherever possible. Use past tense for previous roles. "
        "Never write paragraphs — bullets are scanned, not read."
    ),
    "Education": (
        "Include degree, field of study, school name, and graduation year. "
        "If you graduated within the last 3 years, add relevant coursework, GPA (if ≥ 3.5), "
        "honors, or clubs that demonstrate skills. "
        "Once you have 3+ years of experience, move Education below Experience. "
        "Omit high school once you have a college degree."
    ),
    "Projects": (
        "A Projects section is essential if you lack work experience or are switching fields. "
        "Each project should name the project, the tech/tools used, and a measurable outcome. "
        "Link to live demos or GitHub repos. 2–4 projects is ideal — quality beats quantity. "
        "Describe impact, not just what you built: 'Built X that achieved Y.'"
    ),
    "Certifications": (
        "List certifications with the full name, issuing organization, and year obtained. "
        "Prioritize certifications relevant to roles you're targeting. "
        "Note 'Expected [Month Year]' for in-progress certs. "
        "Remove certifications older than 5 years unless still standard in your field."
    ),
    "Skills": (
        "An explicit Skills section is required by every ATS system. Without it, your technical skills "
        "won't be detected even if they appear in bullets — parsers look for a labeled section. "
        "List 10–15 skills max, organized by category (e.g. 'Languages', 'Tools', 'Methodologies'). "
        "Put your most in-demand skills first. Omit assumed basics (e.g. Microsoft Word). "
        "Pair each skill listed here with a bullet in Experience that demonstrates it."
    ),
}

# ── Strong action verbs (lowercase, used in bullet detection) ──
STRONG_VERBS = frozenset({
    "accelerated", "achieved", "acquired", "administered", "advanced", "advised",
    "analyzed", "applied", "assessed", "authored", "automated",
    "built", "championed", "coached", "collaborated", "completed", "conducted",
    "consolidated", "coordinated", "crafted", "created", "cut",
    "decreased", "delivered", "deployed", "designed", "developed", "diagnosed",
    "directed", "drove", "earned",
    "engineered", "established", "examined", "exceeded", "executed", "expanded",
    "facilitated", "formulated", "founded",
    "generated", "grew", "guided",
    "identified", "implemented", "improved", "increased", "influenced",
    "initiated", "integrated",
    "launched", "led",
    "managed", "mentored", "migrated", "modeled",
    "navigated", "negotiated",
    "optimized", "orchestrated", "oversaw", "owned",
    "partnered", "piloted", "presented", "prioritized", "produced", "promoted",
    "reduced", "researched", "resolved", "restructured",
    "scaled", "secured", "shaped", "shipped", "simplified", "solved",
    "spearheaded", "standardized", "streamlined",
    "trained", "transformed",
    "upgraded", "utilized",
    "validated",
})


# ── Section detection ─────────────────────────────────────────

# Words that appear in sentences but not in section headers.
# If more than one of these is in the line, it's content, not a heading.
_SENTENCE_WORDS = frozenset({
    "of", "in", "and", "the", "with", "for", "to", "a", "an", "no", "not",
    "strong", "background", "years", "needed", "required", "seeking", "looking",
    "minimum", "at", "or", "as", "from", "by", "on",
})


def _looks_like_section_header(stripped: str) -> bool:
    """Return True only if the line structurally looks like a section heading."""
    words = stripped.split()
    if not words:
        return False
    # Must not start with a digit (e.g. "5 years of experience")
    if words[0][0].isdigit():
        return False
    # Must not be a long sentence (real headers ≤ 6 words)
    if len(words) > 6:
        return False
    # Must not read like a sentence (≤1 stop/sentence word allowed)
    lower_words = [w.strip(".,;:").lower() for w in words]
    sentence_word_hits = sum(1 for w in lower_words if w in _SENTENCE_WORDS)
    if sentence_word_hits > 1:
        return False
    return True


def _match_section(stripped: str, lower: str) -> str | None:
    """
    Return canonical section name if line is a recognized section header, else None.
    Handles compound headers like 'SKILLS & CERTIFICATIONS' by splitting on & / AND.
    """
    if not stripped or len(stripped) >= 55 or not _looks_like_section_header(stripped):
        return None
    line_words = len(stripped.split())

    # Direct match
    for section_name, keywords in SECTION_MAP.items():
        for kw in keywords:
            if kw in lower:
                if len(kw.split()) / max(line_words, 1) >= 0.40:
                    return section_name

    # Compound header: split on & / AND and check each component independently
    if re.search(r'[&/]|\band\b', lower):
        parts = re.split(r'\s*[&/]\s*|\s+and\s+', lower)
        for part in parts:
            part = part.strip()
            if not part or not _looks_like_section_header(part):
                continue
            part_words = len(part.split())
            for section_name, keywords in SECTION_MAP.items():
                for kw in keywords:
                    if kw in part and len(kw.split()) / max(part_words, 1) >= 0.40:
                        return section_name

    return None


def detect_sections(text):
    """Split resume text into {SectionName: content} dict."""
    lines = text.split("\n")
    sections = {}
    current = "Header"
    buf = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        matched = _match_section(stripped, lower)
        if matched:
            if buf:
                existing = sections.get(current, "")
                new_chunk = "\n".join(buf).strip()
                # Concatenate instead of overwrite — prevents data loss when the
                # same section name is matched twice (e.g. two "Experience" headers)
                sections[current] = (existing + "\n" + new_chunk).strip() if existing else new_chunk
            current = matched
            buf = []
        elif stripped:
            buf.append(stripped)

    if buf:
        existing = sections.get(current, "")
        new_chunk = "\n".join(buf).strip()
        sections[current] = (existing + "\n" + new_chunk).strip() if existing else new_chunk

    return {k: v for k, v in sections.items() if v.strip()}


# ── Bullet analysis ───────────────────────────────────────────

# Patterns that indicate a header/label line rather than a bullet
_HEADER_RE = re.compile(
    r"(\b[A-Z][a-z]+,?\s+[A-Z]{2}\b"       # City, ST
    r"|^\d{4}\s*[–\-]"                       # date range start
    r"|\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b.*\d{4}"
    r"|^[A-Z][a-zA-Z/\s]+\s{3,}"            # job title with lots of whitespace
    r"|\t)"                                  # tab-separated formatting
)

# Degree prefixes that indicate an education line
_DEGREE_RE = re.compile(
    r"^(B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|MBA|Ph\.?D|A\.?A\.?|B\.?E\.?|"
    r"Bachelor|Master|Associate|Doctor|High School)\b",
    re.IGNORECASE
)

# Job header: "Title - Company (Year)" or "Title at Company"
_JOB_HEADER_RE = re.compile(
    r"[–\-—|]\s*.{2,40}\s*[\(\[]?\d{4}|"       # "- Company (2020"
    r"\d{4}\s*[–\-—]\s*(present|\d{4})|"         # "2020 - Present" or "2020-2022"
    r"\(20\d\d\s*[–\-]\s*(present|20\d\d)\)",    # "(2020-Present)"
    re.IGNORECASE
)


# Common function/preposition words — these being lowercase in a line signals
# it's a real sentence, not a pure proper-noun header.
_FUNC_WORDS = frozenset({
    "the", "and", "of", "for", "in", "at", "to", "a", "an", "or", "by",
    "on", "with", "as", "is", "are", "was", "were", "its", "their",
})


def _is_bullet_line(line):
    stripped = line.strip()
    cleaned  = stripped.lstrip("•-–*·▸▪◦").strip()

    # Too short or all-uppercase section header
    if len(cleaned.split()) < 5 or cleaned.isupper():
        return False

    # Contact info: has @ (email address)
    if "@" in cleaned:
        return False

    # Contact/header lines with | separators (e.g. "Name | Email | Phone")
    if cleaned.count("|") >= 1 and len(cleaned.split()) <= 8:
        return False

    # Phone numbers
    if re.search(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}", cleaned):
        return False

    # URL/LinkedIn
    if re.search(r"linkedin\.com|github\.com|http", cleaned, re.IGNORECASE):
        return False

    # Tab-separated formatting
    if "\t" in cleaned:
        return False

    # Education degree lines: "BS Statistics, University of Michigan, 2019"
    if _DEGREE_RE.match(cleaned):
        return False

    # Job header lines: "Senior Data Analyst - Acme Corp (2021-Present)"
    if _JOB_HEADER_RE.search(cleaned):
        return False

    # Date-only ranges
    if re.match(r"^\d{4}\s*[–\-—]\s*(present|\d{4})$", cleaned, re.IGNORECASE):
        return False

    # City/State header lines
    if _HEADER_RE.search(cleaned):
        return False

    # Organization / department name headers — nearly all title-cased words, no verb
    # e.g. "Charlotte Water Environmental Services Department"
    # e.g. "Department of Natural Resources Conservation Bureau"
    # e.g. "City of Charlotte Parks and Recreation Department"
    words_raw = [w.rstrip(",-;:.") for w in cleaned.split() if w]
    leading   = [w for w in words_raw[:7] if w]  # non-empty only
    if len(leading) >= 4:
        func_in_leading = sum(1 for w in leading if w.lower() in _FUNC_WORDS)
        non_func        = max(1, len(leading) - func_in_leading)
        cap_in_leading  = sum(1 for w in leading if w and w[0].isupper())
        verb_in_leading = any(w.lower() in STRONG_VERBS for w in leading)
        # "Nearly all non-function words are title-cased" AND no action verb present
        # → this is an org/dept header, not a bullet point
        if cap_in_leading >= non_func - 1 and non_func >= 3 and not verb_in_leading:
            return False

    return True


# ── Domain detection for context-aware feedback ──────────────────
# Each entry: (keyword signals, suggested verbs, metric hint)
_DOMAIN_PROFILES = [
    (
        {"revenue", "sales", "quota", "pipeline", "deal", "close", "sold", "upsell", "cross-sell", "arr", "mrr"},
        ["Grew", "Generated", "Exceeded", "Closed", "Drove"],
        "e.g. '$[X]K in revenue', 'X% above quota', or '[N] new accounts'"
    ),
    (
        {"budget", "cost", "expense", "spend", "saving", "savings", "overhead", "reduction"},
        ["Reduced", "Managed", "Optimized", "Cut", "Lowered"],
        "e.g. 'reduced costs by X%', 'managed $[X]K budget', or 'saved $[X]/year'"
    ),
    (
        {"customer", "client", "account", "user", "subscriber", "retention", "churn", "satisfaction", "nps"},
        ["Retained", "Served", "Improved", "Grew", "Supported"],
        "e.g. 'improved NPS by X pts', 'reduced churn X%', or 'managed [N] accounts'"
    ),
    (
        {"data", "analysis", "analytics", "model", "sql", "python", "dashboard", "report", "insight", "metric"},
        ["Analyzed", "Built", "Designed", "Automated", "Surfaced"],
        "e.g. 'reduced report time by X%', 'built dashboard used by [N] teams', or 'model accuracy of X%'"
    ),
    (
        {"engineer", "deploy", "architecture", "api", "backend", "frontend", "infrastructure", "devops", "cloud"},
        ["Built", "Deployed", "Engineered", "Migrated", "Scaled"],
        "e.g. 'reduced latency X%', 'deployed to [N] users', or 'cut build time by X%'"
    ),
    (
        {"marketing", "campaign", "content", "seo", "brand", "social", "email", "lead", "conversion", "growth"},
        ["Launched", "Grew", "Increased", "Drove", "Generated"],
        "e.g. 'grew traffic X%', 'generated [N] leads', or 'increased conversion X%'"
    ),
    (
        {"project", "cross-functional", "stakeholder", "roadmap", "milestone", "deadline", "delivery", "sprint", "agile"},
        ["Delivered", "Managed", "Coordinated", "Led", "Launched"],
        "e.g. 'delivered [N] projects on time', 'managed $[X]K project budget', or 'led X-person team'"
    ),
    (
        {"recruit", "hire", "onboard", "training", "hr", "talent", "performance", "engagement", "workforce"},
        ["Recruited", "Trained", "Developed", "Managed", "Improved"],
        "e.g. 'reduced time-to-hire X%', 'trained [N] employees', or 'improved retention X%'"
    ),
    (
        {"research", "study", "survey", "publish", "academic", "thesis", "laboratory", "experiment", "clinical"},
        ["Conducted", "Designed", "Published", "Analyzed", "Developed"],
        "e.g. 'conducted study of [N] participants', 'published in [journal]', or 'increased yield X%'"
    ),
    (
        {"finance", "accounting", "audit", "reconcile", "forecast", "variance", "gaap", "tax", "compliance"},
        ["Managed", "Reduced", "Reconciled", "Forecasted", "Audited"],
        "e.g. 'managed $[X]M portfolio', 'reduced variance X%', or 'identified $[X]K in savings'"
    ),
]


def _detect_domain(text: str):
    """Return the best-matching domain profile (or None) for the given text."""
    lower = text.lower()
    best_count, best_profile = 0, None
    for signals, verbs, hint in _DOMAIN_PROFILES:
        count = sum(1 for kw in signals if kw in lower)
        if count > best_count:
            best_count, best_profile = count, (signals, verbs, hint)
    return best_profile if best_count >= 2 else None


# ── Bullet scoring ─────────────────────────────────────────────

_WEAK_VERB_STARTS = frozenset({
    "helped", "assisted", "worked on", "was responsible for", "involved in",
    "participated in", "did", "handled", "made", "used", "did work on",
    "worked with", "supported with",
})

_METRIC_RE = re.compile(
    r"\d+\s*%"                          # percentages
    r"|\$\s*[\d,]+"                     # dollar amounts
    r"|\b\d+[km]?\b"                    # bare numbers
    r"|increased|decreased|reduced|grew|doubled|tripled|cut|saved|generated",
    re.IGNORECASE,
)

_ACTION_VERB_RE = re.compile(
    r"^(" + "|".join(sorted(STRONG_VERBS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


_PLACEHOLDER_RE = re.compile(r'\[.{3,}\]')


def _score_bullet(text: str) -> dict:
    """Score a single bullet point 0–100 and return issues + suggestion."""
    cleaned = text.strip().lstrip("•-–*·▸▪◦").strip()

    # Unfilled template placeholder — skip scoring, flag it clearly
    if _PLACEHOLDER_RE.search(cleaned):
        return {
            "text": text,
            "score": 0,
            "issues": ["Unfilled template placeholder — replace with your actual achievement"],
            "suggestion": "Replace [bracketed text] with: Action Verb + specific task + quantified result.",
            "is_placeholder": True,
        }

    score = 50
    issues = []

    # +20 for starting with a strong action verb
    if _ACTION_VERB_RE.match(cleaned):
        score += 20
    else:
        lower_start = cleaned.lower()
        if any(lower_start.startswith(w) for w in _WEAK_VERB_STARTS):
            score -= 15
            issues.append("Starts with a weak verb — replace with an action verb (Drove, Built, Reduced…)")
        else:
            score -= 5
            issues.append("Lead with a strong action verb (Delivered, Analyzed, Managed…)")

    # +20 for having a metric / quantified result
    if _METRIC_RE.search(cleaned):
        score += 20
    else:
        score -= 10
        issues.append("Add a quantified result — numbers make bullets 40% more memorable to recruiters")

    # −10 for being very short (fewer than 8 words)
    word_count = len(cleaned.split())
    if word_count < 8:
        score -= 10
        issues.append("Too brief — expand with what you did and why it mattered")
    elif word_count > 35:
        score -= 5
        issues.append("Bullet is too long — trim to under 30 words for scannability")

    # −5 for passive voice signals
    if re.search(r"\b(was|were|been)\s+\w+ed\b", cleaned, re.IGNORECASE):
        score -= 5
        issues.append("Passive voice detected — rewrite in active voice ('Managed' not 'Was responsible for managing')")

    # +10 for scope/context words
    if re.search(r"\b(team|cross-functional|stakeholder|company-wide|organization|department|million|thousand)\b",
                 cleaned, re.IGNORECASE):
        score += 10

    score = max(0, min(100, score))

    # Build a context-aware suggestion
    _is_cultural = bool(re.search(
        r"\b(study abroad|university|semester|program|cohort|international|"
        r"cross.cultural|language|culture|exposure|coursework|academic)\b",
        cleaned, re.IGNORECASE
    ))
    _is_technical = bool(re.search(
        r"\b(built|deployed|engineered|developed|fastapi|docker|api|backend|"
        r"database|system|pipeline|model|endpoint|architecture)\b",
        cleaned, re.IGNORECASE
    ))

    if issues:
        if not _ACTION_VERB_RE.match(cleaned):
            suggestion = f"Start with a strong verb — e.g. 'Delivered {cleaned[:60]}…'"
        elif not _METRIC_RE.search(cleaned):
            if _is_cultural:
                suggestion = (
                    f"{cleaned.rstrip('.')} — consider adding: program selectivity, "
                    f"duration, number of countries/peers, or a specific deliverable."
                )
            elif _is_technical:
                suggestion = (
                    f"{cleaned.rstrip('.')} — add: users served, latency improvement, "
                    f"endpoints built, or time/cost saved."
                )
            else:
                suggestion = f"{cleaned.rstrip('.')} — add a result: [X% improvement / $Y impact / N people/accounts]."
        else:
            suggestion = f"Tighten language and quantify scope: '{cleaned[:80]}…'"
    else:
        suggestion = "Strong bullet — consider adding scope (team size, budget, or timeline) if missing."

    return {"text": text, "score": score, "issues": issues, "suggestion": suggestion}


# ── Section scoring ────────────────────────────────────────────

_REQUIRED_SECTIONS = {"Experience", "Education", "Skills"}
_RECOMMENDED_SECTIONS = {"Summary", "Projects", "Certifications"}


def _score_section(name: str, content: str, all_sections: dict) -> dict:
    """Return {score, issues, suggestions} for one section."""
    score = 60
    issues = []
    suggestions = []
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    word_count = len(content.split())

    if name == "Summary":
        # Ideal: 1–2 punchy sentences (10–55 words). Research shows paragraph summaries
        # are skipped in the 6-second scan; a single positioning statement is the 2025 standard.
        if word_count < 8:
            score -= 20
            issues.append("Summary is too short — write 1–2 sentences that position you specifically")
        elif word_count <= 55:
            score += 20  # Sweet spot: tight and scannable
        elif word_count <= 80:
            score += 10  # Acceptable but pushing it
        else:
            score -= 15
            issues.append("Summary is too long — trim to 1–2 sentences; paragraph summaries get skipped")

        # Penalise generic buzzwords
        if re.search(
            r"\b(results[\s\-]driven|team[\s\-]player|hard[\s\-]work(?:ing)?|passionate|"
            r"detail[\s\-]oriented|self[\s\-]starter|go[\s\-]getter|synergy|leverage|"
            r"best[\s\-]of[\s\-]breed|seeking an opportunity|motivated professional)\b",
            content, re.IGNORECASE
        ):
            score -= 15
            issues.append("Remove overused buzzwords — 'results-driven', 'passionate', etc. say nothing specific")
        else:
            score += 10

        # Reward specificity: a named technology, company, credential, or concrete differentiator
        has_specific = bool(
            re.search(r"\b(python|fastapi|llm|rag|api|sql|aws|react|docker|gpt|claude|"
                      r"mba|cpa|cfa|pspo|scrum|certified|deployed|shipped|built|founded)\b",
                      content, re.IGNORECASE)
        )
        if has_specific:
            score += 10
        else:
            suggestions.append(
                "Name something concrete in your summary — a technology you've deployed, "
                "a credential you've earned, or a specific market/domain you know"
            )

    elif name == "Experience":
        bullet_lines = [l for l in lines if _is_bullet_line(l)]
        if len(bullet_lines) < 3:
            score -= 20
            issues.append(f"Only {len(bullet_lines)} bullet point(s) detected — aim for 3–6 per role")
        else:
            score += 20
        has_metrics = any(_METRIC_RE.search(b) for b in bullet_lines)
        if not has_metrics:
            score -= 15
            issues.append("No quantified results found — add percentages, dollar figures, or counts")
        else:
            score += 15
        if not re.search(r"\d{4}", content):
            score -= 10
            issues.append("Include dates for each role (years at minimum)")
        else:
            score += 5

    elif name == "Education":
        if not re.search(r"\d{4}", content):
            score -= 15
            issues.append("Include graduation year")
        else:
            score += 20
        if re.search(r"\b(gpa|grade point|cum laude|honors)\b", content, re.IGNORECASE):
            score += 15
        if word_count < 10:
            score -= 10
            issues.append("Education section is sparse — add degree, school name, and year")
        else:
            score += 10

    elif name == "Skills":
        # Count comma-separated skill tokens, not raw word tokens
        # Strip label prefixes like "Technical:", "Business:", "Certifications:" before counting
        skill_text = re.sub(r"^[A-Za-z &]+:\s*", "", content, flags=re.MULTILINE)
        skill_items = [s.strip() for s in re.split(r"[,|]", skill_text) if s.strip() and len(s.strip()) > 1]
        skill_count = len(skill_items)

        if skill_count < 6:
            score -= 20
            issues.append(f"Only ~{skill_count} skills detected — list 10–20 relevant skills")
        elif skill_count > 30:
            score -= 10
            suggestions.append("Trim to 20–25 skills — prioritize the most in-demand for your target roles")
        else:
            score += 20

        # Detect categories — covers both conventional labels and Josh-style labels
        if re.search(
            r"\b(technical|business|languages?|tools?|frameworks?|software|"
            r"methodolog|certifications?|additional|core competencies)\b",
            content, re.IGNORECASE
        ):
            score += 15
            suggestions.append("Good — skills are organized by category, which aids ATS parsing")
        else:
            suggestions.append("Organize skills into labeled categories (e.g. Technical, Business, Certifications)")

    elif name == "Projects":
        bullet_lines = [l for l in lines if _is_bullet_line(l)]
        if word_count < 30:
            score -= 15
            issues.append("Projects section is sparse — add 2–4 projects with outcomes")
        else:
            score += 20
        if re.search(r"(github|gitlab|huggingface|hf\.co|demo|live|http)", content, re.IGNORECASE):
            score += 15
            # Extra signal: HuggingFace Spaces is the current standard for AI/ML live demos
            if re.search(r"huggingface\.co/spaces|hf\.co/spaces", content, re.IGNORECASE):
                suggestions.append("Live demo on HuggingFace Spaces — strong signal for AI/ML roles")
        else:
            suggestions.append("Add a live demo link or GitHub repo — inline in the bullet, not a separate section")

    elif name == "Certifications":
        if re.search(r"\d{4}", content):
            score += 20
        else:
            suggestions.append("Add the year each certification was obtained")
        if word_count < 5:
            score -= 10
            issues.append("List full certification names and issuing organizations")
        else:
            score += 10

    else:
        # Generic section — score based on presence and length
        if word_count >= 20:
            score += 15
        elif word_count < 5:
            score -= 10

    score = max(0, min(100, score))
    return {"score": score, "issues": issues, "suggestions": suggestions}


# ── Dimension scoring ──────────────────────────────────────────

def _calc_dimensions(sections: dict, bullets: list, missing: list) -> dict:
    """Return impact/clarity/structure scores each 0–10."""
    real_bullets = [b for b in bullets if not b.get("is_placeholder")]
    # Impact: ratio of bullets with metrics
    if real_bullets:
        metriced = sum(1 for b in real_bullets if _METRIC_RE.search(b["text"]))
        impact = round(min(10, (metriced / len(real_bullets)) * 12))
    else:
        impact = 2

    # Clarity: average bullet score mapped to /10, penalise weak verbs
    if real_bullets:
        avg_b = sum(b["score"] for b in real_bullets) / len(real_bullets)
        clarity = round(min(10, avg_b / 10))
    else:
        clarity = 2

    # Structure: sections present vs. expected
    expected = set(SECTION_MAP.keys()) - {"Header", "Awards", "Leadership", "Volunteer",
                                           "Publications", "Languages", "Interests", "References"}
    present  = set(sections.keys())
    overlap  = len(present & expected)
    structure = round(min(10, (overlap / max(len(expected), 1)) * 13))

    return {"impact": impact, "clarity": clarity, "structure": structure}


# ── Action plan builder ────────────────────────────────────────

def _build_action_plan(section_analyses: dict, bullets: list,
                       dims: dict, missing: list) -> dict:
    quick_wins = []
    high_impact = []

    # Quick wins from missing sections
    for sec in missing:
        if sec in _REQUIRED_SECTIONS:
            quick_wins.append({
                "title": f"Add a {sec} section",
                "why": SECTION_COACH.get(sec, "Required section missing.").split(".")[0] + ".",
                "how": f"Create a clearly labeled '{sec}' heading with relevant content.",
                "example": "",
            })

    # Quick wins from low section scores
    for sec_name, sec_data in section_analyses.items():
        if sec_data["score"] < 55:
            for issue in sec_data["issues"][:1]:
                quick_wins.append({
                    "title": f"Fix {sec_name}: {issue[:60]}",
                    "why": f"Low {sec_name} score ({sec_data['score']}/100) is dragging down your overall resume.",
                    "how": issue,
                    "example": SECTION_COACH.get(sec_name, "").split(". ")[0],
                })

    # High impact from weak bullets
    weak_bullets = [b for b in bullets if b["score"] < 60]
    if weak_bullets:
        high_impact.append({
            "title": f"Strengthen {len(weak_bullets)} weak bullet point(s)",
            "why": "Bullet points are what recruiters read most carefully — weak ones reduce your chances significantly.",
            "how": "Lead each bullet with an action verb and add a quantified result (%, $, count, or timeframe).",
            "example": "Before: 'Responsible for managing social media.' → After: 'Grew Instagram following 3× in 6 months by launching weekly content calendar.'",
        })

    # High impact from low impact dimension
    if dims["impact"] < 5:
        high_impact.append({
            "title": "Add measurable results to your experience bullets",
            "why": "Resumes with quantified results are 40% more likely to get callbacks.",
            "how": "For each bullet, ask: 'How much? How many? How fast? What changed?' Add the answer.",
            "example": "Add: '…saving 4 hours/week', '…increasing revenue $12K', or '…improving accuracy by 22%'",
        })

    if dims["structure"] < 6 and missing:
        high_impact.append({
            "title": f"Add missing sections: {', '.join(missing[:3])}",
            "why": "ATS systems score resumes partly on section completeness.",
            "how": "Add clearly labeled sections for each missing category with relevant content.",
            "example": "",
        })

    return {"quick_wins": quick_wins[:5], "high_impact": high_impact[:4]}


# ── Score explainability ──────────────────────────────────────

def _build_score_explanation(section_analyses: dict, missing: list,
                              bullet_analyses: list, overall: int) -> dict:
    """
    Return a human-readable breakdown of WHY the resume scored what it did.
    Keys: summary (str), drivers (list of {sign, label, detail}), next_moves (list of str)
    """
    drivers = []
    next_moves = []

    # Positive drivers
    for name, data in section_analyses.items():
        if data["score"] >= 80:
            drivers.append({
                "sign": "+",
                "label": f"{name} section is strong ({data['score']}/100)",
                "detail": data.get("suggestions", ["Well-structured and complete."])[0]
                          if data.get("suggestions") else "Well-structured and complete.",
            })

    # Quantified bullets (exclude placeholders from counts and messaging)
    real_bullets = [b for b in bullet_analyses if not b.get("is_placeholder")]
    placeholder_bullets = [b for b in bullet_analyses if b.get("is_placeholder")]
    q_bullets = [b for b in real_bullets if any(c.isdigit() for c in b["text"])]
    weak_bullets = [b for b in real_bullets if b["score"] < 60]

    if placeholder_bullets:
        drivers.append({
            "sign": "~",
            "label": f"{len(placeholder_bullets)} unfilled template placeholder{'s' if len(placeholder_bullets)>1 else ''}",
            "detail": "Replace [bracketed placeholders] with real bullets before submitting: Action Verb + task + result.",
        })
        next_moves.append(f"Fill in {len(placeholder_bullets)} template placeholder bullet{'s' if len(placeholder_bullets)>1 else ''} with real achievements.")

    if q_bullets:
        drivers.append({
            "sign": "+",
            "label": f"{len(q_bullets)} of {len(real_bullets)} real bullets have metrics",
            "detail": "Quantified results make your experience concrete and memorable.",
        })
    if weak_bullets:
        loss = len(weak_bullets) * 3
        drivers.append({
            "sign": "−",
            "label": f"{len(weak_bullets)} bullet{'s' if len(weak_bullets)>1 else ''} score below 60 (−{loss} pts)",
            "detail": f"Weakest: \"{weak_bullets[0]['text'][:70]}…\" — {weak_bullets[0]['issues'][0] if weak_bullets[0]['issues'] else 'Needs a stronger verb and result.'}",
        })
        next_moves.append(f"Rewrite {len(weak_bullets)} weak bullet{'s' if len(weak_bullets)>1 else ''} — use the AI Rewrite button in Bullet Coach.")

    # Missing sections
    for sec in missing:
        penalty = 12 if sec in _REQUIRED_SECTIONS else 5
        drivers.append({
            "sign": "−",
            "label": f"No {sec} section (−{penalty} pts)",
            "detail": SECTION_COACH.get(sec, "").split(".")[0] + "." if SECTION_COACH.get(sec) else "",
        })
        next_moves.append(f"Add a labeled '{sec}' section to your resume.")

    # Low-scoring sections
    for name, data in section_analyses.items():
        if data["score"] < 55 and data["issues"]:
            drivers.append({
                "sign": "~",
                "label": f"{name} needs work ({data['score']}/100)",
                "detail": data["issues"][0],
            })
            if data.get("suggestions"):
                next_moves.append(f"{name}: {data['suggestions'][0]}")

    # No metrics at all
    if real_bullets and not q_bullets:
        drivers.append({
            "sign": "−",
            "label": "No quantified results in any bullet (−8 pts)",
            "detail": "Numbers — %, $, team size, time saved — make bullets 40% more compelling.",
        })
        next_moves.append("Add at least 2–3 specific metrics to your strongest bullets.")

    grade = "A" if overall >= 85 else "B" if overall >= 70 else "C" if overall >= 55 else "D" if overall >= 40 else "F"
    if overall >= 80:
        summary = f"Your resume is in strong shape at {overall}% ({grade}). Focus on the items below to push above 85."
    elif overall >= 60:
        summary = f"Your resume scores {overall}% ({grade}). A few targeted fixes below will make a measurable difference."
    else:
        summary = f"Your resume scores {overall}% ({grade}). Address the missing sections and bullet improvements below to significantly raise this."

    return {
        "summary": summary,
        "drivers": drivers[:8],
        "next_moves": next_moves[:5],
    }


# ── Main entry point ──────────────────────────────────────────

def full_analysis(text: str) -> dict:
    """
    Analyze a resume and return a comprehensive scoring dict.

    Keys: overall_score, grade, sections, missing_sections, missing_tips,
          section_analyses, bullet_analyses, dimension_scores, action_plan
    """
    sections = detect_sections(text)

    # Content-based cert inference: if cert-like content exists anywhere in the text
    # but there's no detected Certifications header, synthesize the section so it
    # doesn't get flagged as missing (covers "certified" bullets inside Skills, etc.)
    if "Certifications" not in sections and _CERT_CONTENT_RE.search(text):
        cert_lines = [
            l.strip() for l in text.split("\n")
            if l.strip() and _CERT_CONTENT_RE.search(l) and len(l.strip()) < 150
        ]
        if cert_lines:
            sections["Certifications"] = "\n".join(cert_lines[:12])

    # Required / recommended sections
    core_sections = _REQUIRED_SECTIONS | _RECOMMENDED_SECTIONS
    missing = [s for s in core_sections if s not in sections]
    missing_tips = {s: SECTION_COACH.get(s, "") for s in missing}

    # Per-section analysis
    section_analyses = {}
    for name, content in sections.items():
        if name in ("Header", "Languages", "Interests", "References"):
            continue
        section_analyses[name] = _score_section(name, content, sections)

    # Bullet analysis (from Experience + Projects sections)
    bullet_analyses = []
    for sec_name in ("Experience", "Projects"):
        content = sections.get(sec_name, "")
        for line in content.splitlines():
            if _is_bullet_line(line):
                bullet_analyses.append(_score_bullet(line))

    # Dimension scores
    dims = _calc_dimensions(sections, bullet_analyses, missing)

    # Overall score — weighted average of section scores + dimension bonus
    if section_analyses:
        sec_scores = [v["score"] for v in section_analyses.values()]
        sec_avg = sum(sec_scores) / len(sec_scores)
    else:
        sec_avg = 30

    dim_avg = (dims["impact"] + dims["clarity"] + dims["structure"]) / 3  # 0–10

    # Missing required sections penalise heavily
    missing_req = [s for s in missing if s in _REQUIRED_SECTIONS]
    missing_penalty = len(missing_req) * 12

    overall = round(sec_avg * 0.60 + dim_avg * 4.0 - missing_penalty)
    overall = max(5, min(99, overall))

    grade = "A" if overall >= 85 else "B" if overall >= 70 else "C" if overall >= 55 else "D" if overall >= 40 else "F"

    # Action plan
    action_plan = _build_action_plan(section_analyses, bullet_analyses, dims, missing)

    # Score explanation (why is it this score?)
    score_explanation = _build_score_explanation(section_analyses, missing, bullet_analyses, overall)

    return {
        "overall_score":    overall,
        "grade":            grade,
        "sections":         sections,
        "missing_sections": missing,
        "missing_tips":     missing_tips,
        "section_analyses": section_analyses,
        "bullet_analyses":  bullet_analyses,
        "dimension_scores": dims,
        "action_plan":      action_plan,
        "score_explanation": score_explanation,
    }
