import re
from resume_parser import COMMON_SKILLS

_model = None
_util  = None   # sentence_transformers.util — loaded lazily with the model


def get_model():
    """Load sentence-transformers model on first call; cached globally after that."""
    global _model, _util
    if _model is None:
        from sentence_transformers import SentenceTransformer, util as _st_util
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _util  = _st_util
    return _model


# ── Section detection for focused resume extract ─────────────────
_INCLUDE_SECTIONS = {"experience", "skills", "summary", "projects", "work", "profile"}
_EXCLUDE_SECTIONS = {"education", "awards", "certif", "hobbies", "references",
                      "volunteer", "activities", "leadership"}

_CONTACT_RE = re.compile(
    r"@|\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}|linkedin\.com|github\.com|http",
    re.IGNORECASE
)

# Skills that are short enough to produce false positive substring matches
# Use word-boundary matching for these instead of plain substring
_SHORT_SKILLS = {s for s in COMMON_SKILLS if len(s) <= 4 and s.isalpha()}


def _skill_in_text(skill: str, text_lower: str) -> bool:
    """Check if a skill appears in text. Uses word boundaries for short skills."""
    if skill in _SHORT_SKILLS:
        return bool(re.search(r'\b' + re.escape(skill) + r'\b', text_lower))
    return skill in text_lower


# ── Meaningful JD phrase extraction ──────────────────────────────
# Two-word phrases that signal required skills/competencies
_SKILL_PHRASE_TAILS = {
    "management", "analysis", "modeling", "development", "design",
    "strategy", "analytics", "reporting", "communication", "leadership",
    "coordination", "planning", "forecasting", "visualization",
    "automation", "integration", "engineering", "architecture",
    "optimization", "research", "operations", "assessment",
    "implementation", "presentation", "administration",
}

_SKILL_PHRASE_HEADS = {
    "data", "financial", "project", "product", "business", "technical",
    "strategic", "market", "content", "risk", "budget", "process",
    "performance", "client", "stakeholder", "account", "program",
    "customer", "revenue", "sales", "brand", "digital", "cloud",
    "software", "systems", "security", "network", "database",
}

_STOP = frozenset([
    "and", "the", "for", "with", "this", "that", "have", "will",
    "your", "our", "are", "you", "we", "to", "of", "in", "a", "an",
    "or", "is", "it", "at", "be", "as", "on", "by", "do", "not",
    "but", "was", "can", "all", "they", "their", "from", "about",
])


def _extract_jd_phrases(jd_text: str) -> list[str]:
    """
    Extract meaningful 2-word skill/requirement phrases from a job description.
    Returns up to 20 phrases like 'financial modeling', 'data analysis', etc.
    """
    text = jd_text.lower()

    # 1. Head + tail bigrams (e.g. "data analysis", "project management")
    words = re.findall(r"\b[a-z][a-z]+\b", text)
    bigrams = set()
    for i in range(len(words) - 1):
        w1, w2 = words[i], words[i + 1]
        if w1 in _SKILL_PHRASE_HEADS and w2 in _SKILL_PHRASE_TAILS:
            bigrams.add(f"{w1} {w2}")
        elif w1 in _SKILL_PHRASE_TAILS and w2 not in _STOP:
            # e.g. "analysis skills", "management experience" — use just the tail word
            pass

    # 2. Phrases from explicit requirement patterns
    patterns = [
        r"experience (?:with|in|using) ([a-z][a-z\s]{3,28}?)(?:,|\.|;|\n|$)",
        r"proficiency (?:with|in) ([a-z][a-z\s]{3,20}?)(?:,|\.|;|\n|$)",
        r"knowledge of ([a-z][a-z\s]{3,24}?)(?:,|\.|;|\n|$)",
        r"skilled in ([a-z][a-z\s]{3,20}?)(?:,|\.|;|\n|$)",
        r"ability to ([a-z][a-z\s]{3,24}?)(?:,|\.|;|\n|$)",
    ]
    extracted = list(bigrams)
    for pat in patterns:
        for m in re.findall(pat, text):
            phrase = m.strip().rstrip(" and")
            words_in = phrase.split()
            if 1 <= len(words_in) <= 4 and len(phrase) > 4:
                # Exclude pure stop-word phrases
                if not all(w in _STOP for w in words_in):
                    extracted.append(phrase)

    # Deduplicate, clean, return
    seen = set()
    result = []
    for p in extracted:
        p = p.strip()
        if p and p not in seen and len(p) > 4:
            seen.add(p)
            result.append(p)

    return result[:20]


def _extract_resume_core(resume_text: str) -> str:
    """
    Extract the most job-relevant parts of the resume:
    skills section + experience bullets + summary.
    Strips contact info, dates, company/title headers, education.
    """
    lines = resume_text.split("\n")
    core = []
    in_relevant = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        low = stripped.lower()

        if any(w in low for w in _INCLUDE_SECTIONS) and len(stripped) < 40:
            in_relevant = True
            continue
        if any(w in low for w in _EXCLUDE_SECTIONS) and len(stripped) < 40:
            in_relevant = False
            continue

        if not in_relevant:
            continue

        if _CONTACT_RE.search(stripped):
            continue

        if re.search(r"[–\-—]\s*.{3,40}\s*[\(\[]?\d{4}|"
                     r"\(20\d\d\s*[–\-]\s*(present|20\d\d)\)",
                     stripped, re.IGNORECASE):
            continue

        if re.match(r"^\d{4}\s*[–\-—]\s*(present|\d{4})\s*$", stripped, re.IGNORECASE):
            continue

        core.append(stripped)

    result = " ".join(core)
    return result if len(result.split()) >= 20 else resume_text


def score_job(resume_text: str, job_description: str, job_title: str = "") -> int:
    """
    Composite job match score 0-100:
      - 50% semantic similarity (sentence-transformer on focused resume extract)
      - 35% keyword overlap (COMMON_SKILLS present in JD vs resume)
      - 15% title/role match (job title words vs resume titles/summary)
    """
    if not job_description.strip():
        return 0

    core       = _extract_resume_core(resume_text)
    model      = get_model()
    # Increased from 2500/1500 — ensures full resumes and long JDs are scored completely
    core_trunc = core[:5000]
    jd_trunc   = job_description[:3000]

    embeddings = model.encode([core_trunc, jd_trunc], convert_to_tensor=True)
    raw_sim    = _util.cos_sim(embeddings[0], embeddings[1]).item()

    # Adaptive rescaling: normalize relative to observed min/max rather than fixed bounds.
    # Floor at 0.15 (near-random similarity), ceiling at 0.85 (near-identical text).
    _SIM_FLOOR   = 0.15
    _SIM_CEILING = 0.85
    semantic = max(0, min(100, int((raw_sim - _SIM_FLOOR) / (_SIM_CEILING - _SIM_FLOOR) * 100)))

    resume_lower = resume_text.lower()
    jd_lower     = job_description.lower()

    jd_skills = [s for s in COMMON_SKILLS if _skill_in_text(s, jd_lower)]
    if jd_skills:
        matched_count = sum(1 for s in jd_skills if _skill_in_text(s, resume_lower))
        keyword_score = int(matched_count / len(jd_skills) * 100)
    else:
        keyword_score = 0  # no known skills in JD — don't inflate with semantic

    # Title match: significant words in job title that appear in the resume
    # Include 2+ char words to catch acronyms like ML, AI, UX, PM
    title_score = 0
    if job_title:
        _stop = {"and", "or", "the", "a", "an", "of", "in", "at", "for", "to", "with"}
        title_words = [
            w.lower() for w in re.findall(r"[a-zA-Z]{2,}", job_title)
            if w.lower() not in _stop
        ]
        if title_words:
            hits = sum(1 for w in title_words if re.search(r'\b' + re.escape(w) + r'\b', resume_lower))
            title_score = int(hits / len(title_words) * 100)

    if job_title:
        return min(100, int(semantic * 0.50 + keyword_score * 0.35 + title_score * 0.15))
    else:
        return min(100, int(semantic * 0.60 + keyword_score * 0.40))


def get_skill_gaps(resume_text: str, job_description: str):
    """
    Returns (matched_skills, missing_skills).
    Combines COMMON_SKILLS matches with extracted JD-specific phrases for richer chips.
    Uses word-boundary matching for short skill names to avoid false positives.
    """
    resume_lower = resume_text.lower()
    job_lower    = job_description.lower()

    matched, missing = [], []

    # 1. COMMON_SKILLS (word-boundary safe)
    for skill in COMMON_SKILLS:
        if _skill_in_text(skill, job_lower):
            if _skill_in_text(skill, resume_lower):
                matched.append(skill)
            else:
                missing.append(skill)

    # 2. JD-extracted phrases not already covered by COMMON_SKILLS
    common_lower = {s.lower() for s in COMMON_SKILLS}
    for phrase in _extract_jd_phrases(job_lower):
        if phrase in common_lower:
            continue
        # Only surface if explicitly mentioned in JD (already filtered by extraction)
        if phrase in resume_lower:
            if phrase not in matched:
                matched.append(phrase)
        else:
            if phrase not in missing and len(missing) < 8:
                missing.append(phrase)

    return matched, missing


# ── Pipeline / ghost-job signal phrases ──────────────────────────
_GHOST_PIPELINE_PHRASES = [
    ("we are always looking for",  "📋 Always hiring — may be pipeline"),
    ("talent pool",                "📋 Talent pool — no confirmed opening"),
    ("future opportunities",       "📋 Speculative — no confirmed opening"),
    ("pipeline of candidates",     "📋 Pipeline posting"),
    ("join our growing team",      "⚠ Generic posting — verify role is active"),
    ("open to candidates",         "📋 May be exploratory"),
    ("evergreen",                  "📋 Evergreen posting — timeline unclear"),
]


def ghost_score(job: dict) -> tuple:
    """
    Estimate how likely a job posting is a ghost/stale listing.
    Returns (score: int 0-100, signals: list[str]).
    Thresholds used in 2_Jobs.py: ≥30 = badge shown, ≥60 = red badge.
    """
    score   = 0
    signals = []

    # Age signal — most reliable ghost indicator
    date_str = job.get("date", "")
    days_old = None
    if date_str:
        try:
            from datetime import date as _d
            days_old = (_d.today() - _d.fromisoformat(date_str[:10])).days
        except Exception:
            pass

    if days_old is not None:
        if days_old > 60:
            score += 60
            signals.append(f"🔴 {days_old}d old — likely stale")
        elif days_old > 30:
            score += 40
            signals.append(f"🟠 {days_old}d old — aging")
        elif days_old > 21:
            score += 25
            signals.append(f"🟡 {days_old}d old")

    # Description-based pipeline signals
    desc_lower = (job.get("description") or "").lower()
    for phrase, label in _GHOST_PIPELINE_PHRASES:
        if phrase in desc_lower:
            score += 20
            signals.append(label)
            break  # one pipeline flag is enough

    # No description is itself a weak signal (JDs stripped = likely aggregator repost)
    if not desc_lower.strip():
        score += 15
        signals.append("⚠ No job description")

    return min(score, 100), signals


def salary_adjusted_score(base_score: int, job: dict, user_profile) -> tuple:
    """
    Optionally adjust the fit score based on salary alignment.
    Returns (adjusted_score: int, salary_note: str).
    Note is an empty string when no adjustment is warranted.
    """
    if not user_profile:
        return base_score, ""

    u_min = user_profile.get("min_salary") or 0
    u_max = user_profile.get("max_salary") or 0
    if not u_min and not u_max:
        return base_score, ""

    j_min = job.get("salary_min") or 0
    j_max = job.get("salary_max") or 0
    if not j_min and not j_max:
        # No salary listed — can't compare; surface note if in pay-transparency state
        return base_score, ""

    # Use midpoint for comparison
    j_mid = (j_min + j_max) / 2 if j_min and j_max else (j_min or j_max)
    u_mid = (u_min + u_max) / 2 if u_min and u_max else (u_min or u_max)

    if u_mid > 0:
        ratio = j_mid / u_mid
        if ratio < 0.80:
            note = f"Below your ~${int(u_mid):,} target ({int(ratio*100)}% of target)"
            return max(0, base_score - 8), note
        if ratio < 0.90:
            note = f"Slightly below your target (${int(j_mid):,} vs ${int(u_mid):,})"
            return base_score, note

    return base_score, ""


def batch_score_jobs(resume_text: str, jobs: list, user_profile=None) -> None:
    """
    Score all jobs in-place. Adds keys to each job dict:
      score, matched, missing, ghost_score, ghost_signals, salary_note.
    Uses sentence-transformer batching for speed when description is available.
    """
    if not jobs:
        return

    from resume_parser import COMMON_SKILLS as _cs  # already imported at module level

    resume_lower = resume_text.lower()
    core         = _extract_resume_core(resume_text)

    # Collect all descriptions for batch embedding
    descs = [(job.get("description") or "")[:3000] for job in jobs]
    core_trunc = core[:5000]

    # Only load model when at least one job has a description
    has_desc = any(d.strip() for d in descs)
    if has_desc:
        model = get_model()
        texts     = [core_trunc] + descs
        embeddings = model.encode(texts, convert_to_tensor=True, show_progress_bar=False)
        resume_emb = embeddings[0]
        job_embs   = embeddings[1:]
    else:
        resume_emb = None
        job_embs   = [None] * len(jobs)

    _SIM_FLOOR   = 0.15
    _SIM_CEILING = 0.85

    for i, job in enumerate(jobs):
        desc = descs[i]
        title = job.get("title", "")

        # ── Semantic score ────────────────────────────────────────
        if desc.strip() and resume_emb is not None and job_embs[i] is not None:
            raw_sim  = _util.cos_sim(resume_emb, job_embs[i]).item()
            semantic = max(0, min(100, int((raw_sim - _SIM_FLOOR) / (_SIM_CEILING - _SIM_FLOOR) * 100)))
        else:
            semantic = 0

        # ── Keyword score ─────────────────────────────────────────
        jd_lower  = desc.lower()
        jd_skills = [s for s in _cs if _skill_in_text(s, jd_lower)]
        if jd_skills:
            mc = sum(1 for s in jd_skills if _skill_in_text(s, resume_lower))
            keyword_score = int(mc / len(jd_skills) * 100)
        else:
            keyword_score = 0  # no known skills in JD — don't inflate with semantic

        # ── Title score ───────────────────────────────────────────
        _stop = {"and","or","the","a","an","of","in","at","for","to","with"}
        # Include 2+ char words to catch acronyms like ML, AI, UX, PM
        title_words = [w.lower() for w in re.findall(r"[a-zA-Z]{2,}", title) if w.lower() not in _stop]
        if title_words:
            hits = sum(1 for w in title_words if re.search(r'\b' + re.escape(w) + r'\b', resume_lower))
            title_score = int(hits / len(title_words) * 100)
            final = min(100, int(semantic * 0.50 + keyword_score * 0.35 + title_score * 0.15))
        else:
            final = min(100, int(semantic * 0.60 + keyword_score * 0.40))

        # ── Skill gaps ────────────────────────────────────────────
        matched, missing = [], []
        for skill in _cs:
            if _skill_in_text(skill, jd_lower):
                if _skill_in_text(skill, resume_lower):
                    matched.append(skill)
                else:
                    missing.append(skill)
        common_lower_set = {s.lower() for s in _cs}
        for phrase in _extract_jd_phrases(jd_lower):
            if phrase in common_lower_set:
                continue
            if phrase in resume_lower:
                if phrase not in matched:
                    matched.append(phrase)
            elif phrase not in missing and len(missing) < 8:
                missing.append(phrase)

        # ── Ghost score ───────────────────────────────────────────
        g_score, g_signals = ghost_score(job)

        # ── Salary alignment ──────────────────────────────────────
        adjusted, sal_note = salary_adjusted_score(final, job, user_profile)

        job["score"]         = adjusted
        job["matched"]       = matched
        job["missing"]       = missing
        job["ghost_score"]   = g_score
        job["ghost_signals"] = g_signals
        job["salary_note"]   = sal_note
