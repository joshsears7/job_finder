import re
import datetime
import pdfplumber
import docx as _docx

# ── Skill aliases ─────────────────────────────────────────────────
# Maps abbreviations/alternate forms → canonical skill name in COMMON_SKILLS.
# Applied during parsing so "ML engineer" → matched as "scikit-learn" etc. is
# handled at scoring time, and abbreviations show up in the skills list.
SKILL_ALIASES: dict[str, str] = {
    "ml":             "scikit-learn",   # generic ML → closest canonical
    "ai":             "tensorflow",
    "js":             "javascript",
    "ts":             "typescript",
    "py":             "python",
    "rb":             "ruby",
    "k8s":            "kubernetes",
    "k8":             "kubernetes",
    "tf":             "terraform",
    "tf2":            "tensorflow",
    "pg":             "postgresql",
    "postgres":       "postgresql",
    "mongo":          "mongodb",
    "es":             "elasticsearch",
    "elastic":        "elasticsearch",
    "sklearn":        "scikit-learn",
    "scikit":         "scikit-learn",
    "torch":          "pytorch",
    "node":           "node.js",
    "nodejs":         "node.js",
    "next":           "next.js",
    "nextjs":         "next.js",
    "vue.js":         "vue",
    "vuejs":          "vue",
    "angularjs":      "angular",
    "gke":            "kubernetes",
    "eks":            "kubernetes",
    "gcs":            "gcp",
    "google cloud":   "gcp",
    "amazon web":     "aws",
    "azure cloud":    "azure",
    "mssql":          "sql",
    "t-sql":          "sql",
    "plsql":          "sql",
    "pl/sql":         "sql",
    "powerbi":        "power bi",
    "looker":         "tableau",   # BI tool family
    "dask":           "pandas",
    "xgboost":        "scikit-learn",
    "lightgbm":       "scikit-learn",
    "bash script":    "bash",
    "shell":          "bash",
    "linux/unix":     "linux",
    "unix":           "linux",
    "agile/scrum":    "agile",
    "google ads":     "google analytics",
    "hubspot":        "salesforce",
    "github":         "git",
    "gitlab":         "git",
    "bitbucket":      "git",
    "sketch":         "figma",
    "adobe xd":       "figma",
}

COMMON_SKILLS = [
    # Languages
    "python", "javascript", "typescript", "java", "c++", "c#", "golang", "rust",
    "ruby", "php", "swift", "kotlin", "r programming", "scala", "matlab", "bash", "sql",
    # Web / Frontend
    "react", "angular", "vue", "node.js", "django", "flask", "fastapi",
    "express", "html", "css", "rest api", "graphql", "next.js",
    # Data / ML
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "spark", "hadoop", "airflow", "dbt", "tableau", "power bi",
    # Cloud / DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "jenkins", "git", "linux", "ci/cd",
    # Business / Finance
    "excel", "financial modeling", "bloomberg", "valuation", "accounting",
    "google analytics", "salesforce", "jira", "agile", "scrum",
    # Analytics / Research
    "data analysis", "data visualization", "statistics", "a/b testing",
    "market research", "forecasting", "business intelligence", "reporting",
    # Design / Product
    "figma", "product management", "user research", "wireframing",
    "product strategy", "roadmapping",
    # Soft / Business skills (used in JD matching)
    "project management", "stakeholder management", "communication",
    "leadership", "collaboration", "problem solving", "presentation",
    "strategic planning", "cross-functional", "negotiation",
]

# ── Common job titles for extraction ────────────────────────────────
_TITLE_PATTERNS = [
    r"\b(software engineer|data scientist|data analyst|business analyst|"
    r"product manager|project manager|marketing analyst|financial analyst|"
    r"operations analyst|account manager|hr specialist|consultant|"
    r"machine learning engineer|devops engineer|backend engineer|"
    r"frontend engineer|full.?stack engineer|ux designer|ui designer|"
    r"data engineer|cloud engineer|security engineer|systems analyst|"
    r"research analyst|investment analyst|quantitative analyst|"
    r"supply chain analyst|it analyst|management consultant|"
    r"marketing manager|sales analyst|content strategist|"
    r"strategy analyst|corporate analyst|intern)\b",
]

_YEAR_RE = re.compile(
    r"(\d+)\s*\+?\s*year[s]?\s+(?:of\s+)?(?:professional\s+)?experience",
    re.IGNORECASE,
)

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}")
_CONTACT_LINE_RE = re.compile(r"@|\d{3}[\s.\-]\d{3}|linkedin|github|http|www\.", re.I)


# ── File text extraction ───────────────────────────────────────────

def extract_text(file_path: str) -> str:
    """Extract plain text from a PDF or DOCX file path."""
    ext = file_path.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        parts = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
        except Exception as e:
            raise ValueError(f"Could not read PDF: {e}")
        return "\n".join(parts)
    elif ext in ("docx", "doc"):
        try:
            doc = _docx.Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise ValueError(f"Could not read DOCX: {e}")
    else:
        raise ValueError(f"Unsupported file type: .{ext}. Use PDF or DOCX.")


# ── Resume parsing ─────────────────────────────────────────────────

def _resolve_aliases(text_lower: str, skills: list) -> list:
    """Expand alias tokens found in text into canonical skill names."""
    extra = []
    for alias, canonical in SKILL_ALIASES.items():
        if re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
            if canonical not in skills and canonical not in extra:
                extra.append(canonical)
    return extra


def parse_resume(text: str) -> dict:
    """
    Parse plain-text resume into a structured profile dict.

    Returns:
        {
            raw_text        : str   — original text
            name            : str   — best-guess full name
            email           : str
            phone           : str
            skills          : list[str] — canonical matched skills
            titles          : list[str] — detected job titles
            years_experience: int
        }
    """
    text_lower = text.lower()

    # ── Skills ─────────────────────────────────────────────────────
    skills = []
    for skill in COMMON_SKILLS:
        skill_l = skill.lower()
        # Word-boundary for short skills to avoid false positives
        if len(skill_l) <= 4 and skill_l.isalpha():
            if re.search(r'\b' + re.escape(skill_l) + r'\b', text_lower):
                skills.append(skill)
        else:
            if skill_l in text_lower:
                skills.append(skill)

    # Expand abbreviations / aliases
    skills += _resolve_aliases(text_lower, skills)

    # ── Titles ─────────────────────────────────────────────────────
    titles = []
    seen = set()
    for pat in _TITLE_PATTERNS:
        for m in re.finditer(pat, text_lower, re.IGNORECASE):
            t = m.group(1).strip().lower()
            if t not in seen:
                seen.add(t)
                titles.append(t)

    # ── Years of experience ─────────────────────────────────────────
    years_experience = 0
    m = _YEAR_RE.search(text)
    if m:
        years_experience = int(m.group(1))
    else:
        # Count date ranges like "2020–2024" or "2020 - Present"
        date_ranges = re.findall(
            r"(\d{4})\s*[–\-—]\s*(present|\d{4})",
            text, re.IGNORECASE
        )
        current_year = datetime.date.today().year
        total = 0
        for start, end in date_ranges:
            try:
                s = int(start)
                e = current_year if end.lower() == "present" else int(end)
                if 1990 <= s <= current_year and s <= e <= current_year:
                    total += e - s
            except ValueError:
                pass
        years_experience = min(total, 40)

    # ── Contact info ────────────────────────────────────────────────
    email_m = _EMAIL_RE.search(text)
    email   = email_m.group(0) if email_m else ""

    phone_m = _PHONE_RE.search(text)
    phone   = phone_m.group(0) if phone_m else ""

    # ── Name: first non-empty non-contact line, title-cased ─────────
    name = ""
    for line in text.splitlines():
        stripped = line.strip()
        if (stripped
                and len(stripped) >= 4
                and len(stripped) <= 50
                and not _CONTACT_LINE_RE.search(stripped)
                and not re.match(r"^\d", stripped)
                and not any(stripped.lower().startswith(k) for k in
                            ("education", "experience", "skills", "summary",
                             "objective", "work", "projects", "resume"))):
            name = stripped
            break

    return {
        "raw_text":         text,
        "name":             name,
        "email":            email,
        "phone":            phone,
        "skills":           skills,
        "titles":           titles,
        "years_experience": years_experience,
    }
