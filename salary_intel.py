"""
salary_intel.py
---------------
Salary estimation using BLS OES 2023 percentile data + city cost-of-living
and experience level multipliers. Zero external API calls.
"""
import re

# ── BLS OES 2023 salary data (in $1,000 annual) ──────────────────
# p10/p25/p50/p75/p90 = percentile bands at national level
SALARY_DATA = {
    "business analyst": {
        "title": "Business / Management Analyst",
        "p10": 47, "p25": 60, "p50": 80, "p75": 107, "p90": 142,
        "growth": "+10% (2023–2033)", "bls": "13-1111",
        "notes": "Strong demand in fintech, consulting, and healthcare operations.",
    },
    "data analyst": {
        "title": "Data Analyst",
        "p10": 50, "p25": 66, "p50": 86, "p75": 112, "p90": 148,
        "growth": "+36% (2023–2033)", "bls": "15-2051",
        "notes": "One of the fastest-growing roles. Python + SQL are table-stakes.",
    },
    "financial analyst": {
        "title": "Financial Analyst",
        "p10": 48, "p25": 62, "p50": 81, "p75": 113, "p90": 162,
        "growth": "+8% (2023–2033)", "bls": "13-2051",
        "notes": "Buy-side roles (asset management) pay significantly more than sell-side.",
    },
    "marketing analyst": {
        "title": "Market Research Analyst",
        "p10": 38, "p25": 50, "p50": 68, "p75": 96, "p90": 132,
        "growth": "+19% (2023–2033)", "bls": "13-1161",
        "notes": "Digital marketing analytics roles pay 15-25% above traditional market research.",
    },
    "software engineer": {
        "title": "Software Developer / Engineer",
        "p10": 75, "p25": 96, "p50": 127, "p75": 168, "p90": 215,
        "growth": "+25% (2023–2033)", "bls": "15-1252",
        "notes": "FAANG and fintech pay well above median. Entry at strong companies often exceeds p75.",
    },
    "data scientist": {
        "title": "Data Scientist",
        "p10": 68, "p25": 88, "p50": 108, "p75": 142, "p90": 190,
        "growth": "+36% (2023–2033)", "bls": "15-2051",
        "notes": "ML specializations (NLP, CV) command 20-40% premium.",
    },
    "product manager": {
        "title": "Product Manager",
        "p10": 72, "p25": 96, "p50": 130, "p75": 178, "p90": 235,
        "growth": "+6% (2023–2033)", "bls": "11-2021",
        "notes": "Tech-focused PMs earn significantly more than traditional product roles.",
    },
    "operations analyst": {
        "title": "Operations Research Analyst",
        "p10": 50, "p25": 63, "p50": 84, "p75": 114, "p90": 152,
        "growth": "+23% (2023–2033)", "bls": "15-2031",
        "notes": "Supply chain and logistics ops roles surged post-pandemic.",
    },
    "consultant": {
        "title": "Management Consultant",
        "p10": 60, "p25": 78, "p50": 103, "p75": 140, "p90": 190,
        "growth": "+10% (2023–2033)", "bls": "13-1111",
        "notes": "MBB (McKinsey, BCG, Bain) starting salaries ~$110K; Big 4 ~$75–85K.",
    },
    "account manager": {
        "title": "Account Manager / Sales",
        "p10": 42, "p25": 55, "p50": 74, "p75": 105, "p90": 152,
        "growth": "+4% (2023–2033)", "bls": "11-2022",
        "notes": "Total comp (base + commission + bonus) often 1.5–2x base at target.",
    },
    "hr specialist": {
        "title": "Human Resources Specialist",
        "p10": 38, "p25": 48, "p50": 65, "p75": 86, "p90": 116,
        "growth": "+6% (2023–2033)", "bls": "13-1071",
        "notes": "HR Business Partner and Talent Acquisition roles pay above HR generalist.",
    },
    "project manager": {
        "title": "Project / Program Manager",
        "p10": 58, "p25": 74, "p50": 96, "p75": 127, "p90": 168,
        "growth": "+7% (2023–2033)", "bls": "11-9199",
        "notes": "PMP certification adds ~10–15% salary premium on average.",
    },
    "investment analyst": {
        "title": "Investment / Equity Analyst",
        "p10": 58, "p25": 76, "p50": 102, "p75": 148, "p90": 220,
        "growth": "+8% (2023–2033)", "bls": "13-2099",
        "notes": "Hedge fund and PE analyst roles far exceed p90. Bonus can exceed base.",
    },
    "supply chain analyst": {
        "title": "Supply Chain / Logistics Analyst",
        "p10": 45, "p25": 57, "p50": 77, "p75": 102, "p90": 132,
        "growth": "+18% (2023–2033)", "bls": "13-1081",
        "notes": "APICS/CSCP certification is a significant differentiator.",
    },
    "cybersecurity analyst": {
        "title": "Information Security Analyst",
        "p10": 64, "p25": 84, "p50": 112, "p75": 148, "p90": 188,
        "growth": "+32% (2023–2033)", "bls": "15-1212",
        "notes": "CISSP/Security+ cert adds 10–20% premium. Government roles offer strong stability.",
    },
    "accountant": {
        "title": "Accountant / Auditor",
        "p10": 40, "p25": 52, "p50": 77, "p75": 106, "p90": 137,
        "growth": "+4% (2023–2033)", "bls": "13-2011",
        "notes": "CPA license adds $10–25K premium and opens senior/manager track.",
    },
    "marketing coordinator": {
        "title": "Marketing Coordinator / Specialist",
        "p10": 34, "p25": 44, "p50": 60, "p75": 82, "p90": 112,
        "growth": "+10% (2023–2033)", "bls": "13-1161",
        "notes": "Growth-marketing and performance marketing roles command higher pay.",
    },
    "ux designer": {
        "title": "UX / Product Designer",
        "p10": 50, "p25": 66, "p50": 86, "p75": 117, "p90": 158,
        "growth": "+3% (2023–2033)", "bls": "27-1021",
        "notes": "Sr UX at tech cos often exceeds p90. Portfolio quality matters more than degree.",
    },
}

# ── Keyword → role key mapping ────────────────────────────────────
ROLE_KEYWORDS = {
    "business analyst":       ["business analyst", "management analyst", "biz analyst", "business intelligence"],
    "data analyst":           ["data analyst", "analytics analyst", "reporting analyst"],
    "financial analyst":      ["financial analyst", "finance analyst", "fp&a", "fpa"],
    "marketing analyst":      ["marketing analyst", "market research", "marketing coordinator",
                               "brand analyst", "consumer insights"],
    "software engineer":      ["software engineer", "software developer", "swe", "full stack",
                               "backend engineer", "frontend engineer", "dev "],
    "data scientist":         ["data scientist", "ml engineer", "machine learning", "ai engineer",
                               "deep learning"],
    "product manager":        ["product manager", "product owner", "pm ", "group pm"],
    "operations analyst":     ["operations analyst", "operations manager", "ops analyst",
                               "operations research"],
    "consultant":             ["consultant", "consulting", "advisory analyst"],
    "account manager":        ["account manager", "account executive", "sales rep",
                               "sales associate", "territory manager"],
    "hr specialist":          ["hr specialist", "human resources", "recruiter",
                               "talent acquisition", "hrbp"],
    "project manager":        ["project manager", "program manager", "pmo", "scrum master"],
    "investment analyst":     ["investment analyst", "portfolio analyst", "equity analyst",
                               "research analyst", "hedge fund"],
    "supply chain analyst":   ["supply chain", "logistics analyst", "procurement analyst",
                               "demand planning"],
    "cybersecurity analyst":  ["cybersecurity", "security analyst", "infosec",
                               "information security", "soc analyst"],
    "accountant":             ["accountant", "auditor", "cpa", "accounting", "controller"],
    "marketing coordinator":  ["marketing coordinator", "marketing specialist",
                               "digital marketing", "social media", "content"],
    "ux designer":            ["ux designer", "ui designer", "product designer",
                               "ux researcher", "interaction designer"],
}

# ── City cost-of-living multipliers ──────────────────────────────
CITY_MULTIPLIERS = {
    "san francisco": 1.40, "sf": 1.40,
    "new york":      1.33, "nyc": 1.33, "new york city": 1.33,
    "seattle":       1.26,
    "boston":        1.22,
    "washington":    1.19, "dc": 1.19, "washington dc": 1.19,
    "los angeles":   1.18, "la": 1.18,
    "chicago":       1.07,
    "denver":        1.03,
    "miami":         1.01,
    "austin":        1.00,
    "dallas":        0.97,
    "houston":       0.96,
    "atlanta":       0.95,
    "charlotte":     0.91,
    "raleigh":       0.91,
    "nashville":     0.93,
    "remote":        1.00,
    "":              1.00,
}

# ── Experience level multipliers ─────────────────────────────────
EXP_LEVELS = {
    "Entry Level (0–2 yrs)":       0.78,
    "Mid Level (3–5 yrs)":         1.00,
    "Senior (6–10 yrs)":           1.32,
    "Lead / Director (10+ yrs)":   1.68,
}


def match_role(query: str):
    """Return best-matching role key or None. Uses word-boundary matching to avoid false positives."""
    q = query.lower().strip()
    if q in SALARY_DATA:
        return q
    for role_key, kws in ROLE_KEYWORDS.items():
        if any(re.search(r'\b' + re.escape(kw) + r'\b', q) for kw in kws):
            return role_key
    return None


def city_mult(city: str) -> float:
    c = city.lower().strip()
    # Sort by key length descending so "san francisco" matches before "san"
    for key, m in sorted(CITY_MULTIPLIERS.items(), key=lambda x: -len(x[0])):
        if key and key in c:
            return m
    return 1.00


def estimate(role_query: str, city: str = "", exp: str = "Mid Level (3–5 yrs)"):
    """
    Returns salary estimate dict or None.
    Keys: role_title, p10..p90 (int $), p50_range (str), growth,
          city_mult, exp_mult, city, exp_level, notes
    """
    key = match_role(role_query)
    if not key:
        return None
    d   = SALARY_DATA[key]
    cm  = city_mult(city)
    em  = EXP_LEVELS.get(exp, 1.00)

    def adj(k):
        return int(d[k] * cm * em * 1_000)

    return {
        "role_title":  d["title"],
        "role_key":    key,
        "p10": adj("p10"), "p25": adj("p25"), "p50": adj("p50"),
        "p75": adj("p75"), "p90": adj("p90"),
        "p50_range":   f"${adj('p25'):,} – ${adj('p75'):,}",
        "growth":      d.get("growth", ""),
        "notes":       d.get("notes", ""),
        "city":        city or "National Average",
        "exp_level":   exp,
        "city_mult":   cm,
        "exp_mult":    em,
    }


def all_role_titles():
    return sorted(d["title"] for d in SALARY_DATA.values())
