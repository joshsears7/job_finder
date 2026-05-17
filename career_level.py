"""
career_level.py
---------------
Detects career seniority level from resume signals and computes
achievement density and scope metrics.
"""

import re
from typing import Literal

CareerLevel = Literal["entry", "mid", "senior", "exec"]

# ── Title keyword lists ────────────────────────────────────────────

_EXEC_TITLES = [
    "chief executive", "chief operating", "chief financial", "chief marketing",
    "chief revenue", "chief technology", "chief product", "chief people",
    "chief information", "chief data", "ceo", "coo", "cfo", "cmo", "cro",
    "cto", "cpo", "chro", "ciso", "president", "managing director",
    "managing partner", "general partner", "executive vice president",
    "senior vice president", "evp", "svp", "global head",
]

_SENIOR_TITLES = [
    "vice president", "vp of", "vp,", "director of", "director,",
    "senior director", "principal", "head of", "group manager",
    "senior manager", "associate director", "associate vp",
    "partner", "lead architect", "distinguished engineer",
    "staff engineer", "principal engineer",
]

_MID_TITLES = [
    "manager", "team lead", "senior analyst", "senior associate",
    "senior specialist", "senior consultant", "project manager",
    "program manager", "senior engineer", "senior developer",
    "senior designer", "analyst ii", "analyst iii",
]

_EXEC_KEYWORDS = [
    "p&l", "profit and loss", "ebitda", "board of directors", "board member",
    "c-suite", "c suite", "ipo", "m&a", "merger", "acquisition",
    "turnaround", "transformation", "strategic plan", "go-to-market",
    "fundrais", "series a", "series b", "series c", "venture capital",
    "private equity", "due diligence", "organizational design", "restructur",
    "market expansion", "capital allocation", "shareholder",
]

_SCOPE_PATTERNS = [
    (r"\$\s*[\d,.]+\s*[bB](?:illion)?", "Billion-dollar scope"),
    (r"\$\s*[\d,.]+\s*[mM](?:illion)?", "Million-dollar scope"),
    (r"\d+\s*(?:direct\s+)?reports?", "Direct reports"),
    (r"(?:led|managed|built|scaled|grew)\s+(?:a\s+)?(?:team\s+of\s+)?\d+", "Team leadership"),
    (r"\d+\s*(?:countries?|markets?|regions?)", "Multi-market scope"),
    (r"(?:series\s+[a-c]|ipo|acquisition|merger)", "Corporate transaction"),
    (r"(?:p&l|profit\s+and\s+loss)", "P&L ownership"),
    (r"\d+%\s*(?:yoy|year.over.year|growth|increase|improvement)", "Growth metrics"),
]


# ── Extraction helpers ─────────────────────────────────────────────

def _detect_team_size(text: str) -> int:
    """Return the largest team / org size mentioned."""
    sizes = []
    for pat in [
        r"(?:led|managed|supervised|oversaw|built|grew|scaled|hired)\s+(?:a\s+)?(?:team\s+of\s+)?(\d{1,4})\+?\s*(?:people|person|employee|staff|member|direct|report)",
        r"(\d{1,4})\+?\s*(?:direct\s+reports?|full.time\s+employee|fte)",
        r"(?:team|organization|org|department)\s+of\s+(\d{1,4})",
        r"(\d{1,4})\+?\s*person\s+(?:team|org)",
    ]:
        for m in re.finditer(pat, text.lower()):
            try:
                sizes.append(int(m.group(1)))
            except (IndexError, ValueError):
                pass
    return max(sizes) if sizes else 0


def _detect_budget_scope_m(text: str) -> float:
    """Return the largest dollar figure mentioned, in millions."""
    amounts = []
    for m in re.finditer(r"\$\s*(\d+(?:\.\d+)?)\s*([bBmMkK])", text):
        val = float(m.group(1))
        suffix = m.group(2).lower()
        if suffix == "b":
            amounts.append(val * 1000)
        elif suffix == "m":
            amounts.append(val)
        elif suffix == "k":
            amounts.append(val / 1_000)
    for m in re.finditer(r"\$([\d,]{5,})", text):
        try:
            amounts.append(float(m.group(1).replace(",", "")) / 1_000_000)
        except ValueError:
            pass
    return round(max(amounts), 1) if amounts else 0.0


# ── Main detection ─────────────────────────────────────────────────

def detect_career_level(profile: dict) -> dict:
    """
    Detect career level from resume signals.

    Returns:
        level        : 'entry' | 'mid' | 'senior' | 'exec'
        confidence   : int 0-100
        signals      : list[str] — top evidence phrases
        team_size    : int — largest org/team size found
        budget_scope_m: float — largest dollar figure in millions
        exec_keywords: list[str] — executive vocabulary found
        years        : int — years of experience
    """
    text  = profile.get("raw_text", "").lower()
    titles_raw = profile.get("titles", [])
    titles = " ".join(t.lower() for t in titles_raw)
    years  = profile.get("years_experience", 0) or 0

    score   = 0
    signals = []

    # ── Title signals (strongest) ──────────────────────────────────
    top_block = text[:600]  # focus on header/summary
    found_title = False
    for t in _EXEC_TITLES:
        if t in titles or t in top_block:
            score += 45
            signals.append(f"Exec title: {t.title()}")
            found_title = True
            break
    if not found_title:
        for t in _SENIOR_TITLES:
            if t in titles or t in top_block:
                score += 22
                signals.append(f"Senior title: {t.title()}")
                found_title = True
                break
    if not found_title:
        for t in _MID_TITLES:
            if t in titles or t in top_block:
                score += 10
                signals.append(f"Mid-level title: {t.title()}")
                break

    # ── Years of experience ────────────────────────────────────────
    if years >= 15:
        score += 25
        signals.append(f"{years}+ years of experience")
    elif years >= 8:
        score += 15
        signals.append(f"{years} years of experience")
    elif years >= 3:
        score += 5

    # ── Team / org size ────────────────────────────────────────────
    team_size = _detect_team_size(text)
    if team_size >= 200:
        score += 28
        signals.append(f"Led {team_size}+ person org")
    elif team_size >= 50:
        score += 20
        signals.append(f"Led {team_size}+ person team")
    elif team_size >= 10:
        score += 12
        signals.append(f"Led team of {team_size}+")
    elif team_size >= 3:
        score += 5

    # ── Budget / revenue scope ─────────────────────────────────────
    budget_m = _detect_budget_scope_m(text)
    if budget_m >= 500:
        score += 28
        signals.append(f"${budget_m:.0f}M+ scope")
    elif budget_m >= 50:
        score += 18
        signals.append(f"${budget_m:.0f}M+ scope")
    elif budget_m >= 5:
        score += 8
        signals.append(f"${budget_m:.1f}M scope")

    # ── Executive vocabulary ───────────────────────────────────────
    exec_kw = [kw for kw in _EXEC_KEYWORDS if kw in text]
    if len(exec_kw) >= 5:
        score += 22
        signals.append(f"Executive language: {', '.join(exec_kw[:3])}")
    elif len(exec_kw) >= 3:
        score += 12
        signals.append(f"Strategic language: {', '.join(exec_kw[:2])}")
    elif len(exec_kw) >= 1:
        score += 5

    # ── Classify ──────────────────────────────────────────────────
    if score >= 75:
        level = "exec"
    elif score >= 38:
        level = "senior"
    elif score >= 16:
        level = "mid"
    else:
        level = "entry"

    return {
        "level":          level,
        "confidence":     min(95, score),
        "signals":        signals[:5],
        "team_size":      team_size,
        "budget_scope_m": budget_m,
        "exec_keywords":  exec_kw[:6],
        "years":          years,
    }


# ── Achievement density ────────────────────────────────────────────

def achievement_density(bullet_analyses: list) -> dict:
    """
    Score how well-quantified the resume bullets are.
    Quantified = contains at least one digit or dollar sign.
    """
    if not bullet_analyses:
        return {
            "density_pct": 0, "grade": "F",
            "quantified": 0, "total": 0,
            "advice": "No bullets detected.",
            "unquantified_examples": [],
        }

    quantified = [b for b in bullet_analyses if re.search(r"[\d$%]", b.get("text", ""))]
    unquantified = [b for b in bullet_analyses if b not in quantified]
    pct = int(len(quantified) / len(bullet_analyses) * 100)

    if pct >= 80:
        grade, advice = "A", "Excellent quantification. Your impact is concrete and credible to hiring managers."
    elif pct >= 65:
        grade, advice = "B", "Good, but the top 20% of candidates hit 80%+. Add numbers to your 3–4 vaguest bullets."
    elif pct >= 45:
        grade, advice = "C", "Under half your bullets have metrics. Prioritize adding %, $, team size, or time savings."
    elif pct >= 25:
        grade, advice = "D", "Too few metrics. Without numbers, achievements blend into every other candidate's resume."
    else:
        grade, advice = "F", "Almost no quantified achievements — this is your single highest-leverage improvement."

    return {
        "density_pct": pct,
        "grade":       grade,
        "quantified":  len(quantified),
        "total":       len(bullet_analyses),
        "advice":      advice,
        "unquantified_examples": [b["text"][:100] for b in unquantified[:3]],
    }


# ── Scope signal extraction ────────────────────────────────────────

def scope_signals(text: str) -> list:
    """Return list of scope/scale signal labels found in the text."""
    found = []
    for pattern, label in _SCOPE_PATTERNS:
        if re.search(pattern, text.lower()) and label not in found:
            found.append(label)
    return found


# ── Display helpers ────────────────────────────────────────────────

def level_label(level: str) -> str:
    return {
        "entry":  "Entry Level",
        "mid":    "Mid-Level",
        "senior": "Senior Professional",
        "exec":   "Executive",
    }.get(level, "Professional")


def level_color(level: str) -> str:
    return {
        "entry":  "#64748b",
        "mid":    "#2563eb",
        "senior": "#7c3aed",
        "exec":   "#d97706",
    }.get(level, "#64748b")


def level_benchmarks(level: str) -> dict:
    """Return benchmark data for this career level."""
    return {
        "entry": {
            "density_target": 50,
            "focus": "Skills, education, early impact — prove you can do the job",
            "top_mistakes": ["Listing responsibilities, not achievements", "No metrics at all", "Generic objective statement"],
        },
        "mid": {
            "density_target": 65,
            "focus": "Specialization and impact — prove you're a strong individual contributor",
            "top_mistakes": ["Underselling scope", "Not showing career progression", "Missing quantified wins"],
        },
        "senior": {
            "density_target": 75,
            "focus": "Leadership, strategy, and cross-functional impact — prove you elevate the team",
            "top_mistakes": ["Too operational, not strategic", "Missing team/budget scope", "No narrative arc"],
        },
        "exec": {
            "density_target": 80,
            "focus": "Vision, P&L, transformation — prove you can run a business unit",
            "top_mistakes": ["Leading with tasks not outcomes", "Missing board/C-suite context", "Weak executive summary", "No career arc story"],
        },
    }.get(level, {})
