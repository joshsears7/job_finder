"""
utils.py
--------
Shared constants, CSS injection, and helper functions used across all
CareerIQ pages. Import from here rather than app.py.
"""

import os
import re
import html as _html
import streamlit as st

import tracker

def xe(s) -> str:
    """HTML-escape a value for safe embedding inside unsafe_allow_html blocks."""
    return _html.escape(str(s) if s is not None else "", quote=True)

# ── Status constants ──────────────────────────────────────────────
STATUS_EMOJI = {"saved": "🔖", "applied": "📤", "interview": "🎯", "offer": "🎉", "rejected": "❌"}
STATUS_COLOR = {
    "saved": "#64748b", "applied": "#2563eb",
    "interview": "#7c3aed", "offer": "#059669", "rejected": "#dc2626",
}

# ── Resume vault (SQLite-backed) ──────────────────────────────────

def _load_vault() -> dict:
    """Return {name: {text, score, saved}} from SQLite resume_versions table."""
    try:
        return tracker.get_vault()
    except Exception:
        return {}


def _save_vault(vault: dict):
    """Upsert all entries in vault dict into SQLite resume_versions table."""
    try:
        for name, v in vault.items():
            tracker.save_vault_version(
                name,
                v.get("text", ""),
                v.get("score", 0),
                v.get("saved", ""),
            )
    except Exception:
        pass


# ── Today's action items ──────────────────────────────────────────
def _todays_tasks(apps=None, contacts=None):
    """Return list of (urgency, title, detail) tuples.

    Pass pre-loaded ``apps`` / ``contacts`` lists to avoid redundant DB reads
    when the caller already fetched them.
    """
    from datetime import date
    tasks = []
    try:
        if apps is None:
            apps = tracker.get_all()
        if contacts is None:
            contacts = tracker.get_contacts()
        today = date.today()
        for a in apps:
            if a["status"] == "applied" and a.get("date_applied"):
                try:
                    days = (today - date.fromisoformat(a["date_applied"][:10])).days
                    _co = xe(a['company']); _ti = xe(a['title'])
                    if days >= 14:
                        tasks.append(("urgent", f"Follow up — {_co}", f"{_ti} · applied {days}d ago, no response."))
                    elif days >= 7:
                        tasks.append(("nudge", f"Consider follow-up — {_co}", f"{_ti} · {days}d since applying."))
                except Exception:
                    pass
            elif a["status"] == "interview":
                tasks.append(("prep", f"Interview prep — {xe(a['company'])}", f"Review questions for {xe(a['title'])}."))
        for c in contacts:
            if c.get("next_action") and c.get("status") in ("warm", "hot", "reached out"):
                tasks.append(("network",
                              f"Reach out: {xe(c['name'])} @ {xe(c.get('company', ''))}",
                              xe(c["next_action"])))
    except Exception:
        pass
    return tasks[:8]


# ── UI helpers ────────────────────────────────────────────────────
def score_color(s):
    return "#059669" if s >= 75 else "#d97706" if s >= 50 else "#dc2626"


def score_badge(s, size=72):
    bg = score_color(s)
    return (f"<div class='score-badge' style='background:{bg};width:{size}px;height:{size}px;"
            f"font-size:{int(size * 0.3)}px'>{s}%</div>")


def chip(label, kind="blue"):
    return f"<span class='chip chip-{kind}'>{xe(label)}</span>"


def progress_bar(pct, color="#2563eb"):
    return (f"<div class='prog-wrap'><div class='prog-fill' "
            f"style='width:{pct}%;background:{color}'></div></div>")


def alert(text, kind="blue"):
    return f"<div class='alert-strip alert-{kind}'>{text}</div>"


# ── CSS injection ────────────────────────────────────────────────
def inject_css():
    """Inject the full CareerIQ stylesheet. Call once per page."""
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ── Reset & base ───────────────────────────────────────────────── */
/* Hide Streamlit chrome — keep sidebar expand/collapse buttons visible */
#MainMenu, footer, [data-testid="stDecoration"] {
    visibility:hidden !important; display:none !important;
}
/* Hide all Streamlit chrome: Deploy button, Stop/running indicator, toolbar actions.
   stExpandSidebarButton and stSidebarCollapseButton must stay visible. */
[data-testid="stToolbarActions"],
[data-testid="stToolbarActionButton"],
[data-testid="stAppDeployButton"],
[data-testid="stStatusWidget"],
[data-testid="stHeaderActionElements"] {
    display:none !important;
}
[data-testid="stHeader"] {
    background:#080d1a !important;
    border-bottom:1px solid #1a2340 !important;
    min-height:0 !important;
    height:auto !important;
}
/* Ensure sidebar toggle is always clickable */
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"] {
    display:flex !important;
    visibility:visible !important;
    opacity:1 !important;
}
html, body, [class*="css"] {
    font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif !important;
    -webkit-font-smoothing:antialiased;
}
*, *::before, *::after { box-sizing:border-box; }
.block-container {
    padding-top:1.8rem !important;
    padding-bottom:4rem !important;
    padding-left:2rem !important;
    padding-right:2rem !important;
    max-width:1100px !important;
}

/* ── Sidebar shell ───────────────────────────────────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"],
[data-testid="stSidebarHeader"] {
    background:#080d1a !important;
    border-right:1px solid #1a2340 !important;
}
/* stSidebarHeader — rendered by st.logo(), sits ABOVE stSidebarNav — always visible */
[data-testid="stSidebarHeader"] {
    padding:16px 16px 10px !important;
    border-bottom:1px solid #1a2340 !important;
    flex-shrink:0 !important;
}
[data-testid="stSidebarHeader"] img {
    height:28px !important;
    width:auto !important;
}
/* Flex column on the full sidebar content area */
[data-testid="stSidebarContent"] {
    display:flex !important;
    flex-direction:column !important;
    height:100% !important;
    overflow:hidden !important;
}
/* Profile card block — CSS order puts it before the nav links */
[data-testid="stSidebarUserContent"] {
    order:-1 !important;
    flex:0 0 auto !important;
    padding:14px 12px 10px !important;
    border-bottom:1px solid #1a2340 !important;
}
/* Nav links — scrollable, fills remaining sidebar height */
[data-testid="stSidebarNav"] {
    order:0 !important;
    flex:1 1 auto !important;
    overflow-y:auto !important;
    overflow-x:hidden !important;
    min-height:0 !important;
    padding-top:4px !important;
}

/* ── Sidebar nav — Streamlit 1.51 testid hierarchy ──────────────── */
/* stSidebar > stSidebarContent > stSidebarNav > stSidebarNavItems >
   stSidebarNavLinkContainer > stSidebarNavLink (the <a> tag)       */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] {
    padding:2px 6px;
}
[data-testid="stSidebarNavLinkContainer"] {
    border-radius:8px;
    margin-bottom:2px;
    transition:background .12s;
}
[data-testid="stSidebarNavLinkContainer"]:hover {
    background:#111827 !important;
}
[data-testid="stSidebarNavLink"] {
    display:flex !important;
    align-items:center !important;
    gap:8px !important;
    padding:6px 12px !important;
    font-size:12.5px !important;
    font-weight:500 !important;
    color:#c8d3e8 !important;
    text-decoration:none !important;
    border-radius:6px !important;
}
[data-testid="stSidebarNavLink"]:hover {
    background:#111827 !important;
    color:#fff !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"],
[data-testid="stSidebarNavLinkContainer"]:has([aria-current="page"]) {
    background:#1e3a8a !important;
    border-radius:8px !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"] {
    color:#fff !important;
}
/* Nav link text spans and icons */
[data-testid="stSidebarNavLink"] span,
[data-testid="stSidebarNavLink"] p,
[data-testid="stSidebarNavLink"] div {
    color:#c8d3e8 !important;
    font-size:13px !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"] span,
[data-testid="stSidebarNavLink"][aria-current="page"] p,
[data-testid="stSidebarNavLink"][aria-current="page"] div {
    color:#fff !important;
}
/* "View more" button at bottom of nav */
[data-testid="stSidebarNavViewButton"] button {
    color:#64748b !important;
    font-size:12px !important;
}

[data-testid="stSidebarUserContent"] * { color:#c8d3e8 !important }

/* Legacy fallback for older Streamlit page link style */
[data-testid="stSidebar"] [data-testid="stPageLink"] a,
[data-testid="stSidebarUserContent"] a {
    font-size:13px; padding:7px 14px; border-radius:8px;
    transition:background .12s; color:#c8d3e8 !important;
    text-decoration:none; display:block; font-weight:500;
}

[data-testid="stSidebar"] .stRadio label {
    font-size:13px; padding:7px 14px; border-radius:8px;
    transition:background .12s; display:block; font-weight:500;
}

/* ── Metrics ────────────────────────────────────────────────────── */
div[data-testid="metric-container"] {
    background:#111827 !important; border:1px solid #1e293b !important;
    border-radius:12px; padding:16px 20px;
}
div[data-testid="metric-container"] label,
div[data-testid="metric-container"] [data-testid="stMetricValue"],
div[data-testid="metric-container"] [data-testid="stMetricDelta"] { color:#e2e8f0 !important }

/* ── Hero ───────────────────────────────────────────────────────── */
.hero-section {
    background:linear-gradient(145deg,#060c1a 0%,#0c1f5c 50%,#1035b0 100%);
    border-radius:18px; padding:52px 48px 44px; text-align:center;
    margin-bottom:32px; border:1px solid #1e3a8a30;
    box-shadow:0 20px 60px rgba(30,58,138,.25);
}
.hero-badge {
    display:inline-block; background:#ffffff0f; color:#93c5fd;
    border:1px solid #3b82f625; border-radius:100px;
    padding:5px 18px; font-size:11px; font-weight:700;
    margin-bottom:22px; letter-spacing:.08em; text-transform:uppercase;
}
.hero-title {
    font-size:3rem; font-weight:900; color:#fff;
    line-height:1.1; margin-bottom:16px; letter-spacing:-.04em;
}
.hero-title span { color:#60a5fa }
.hero-sub {
    font-size:1.05rem; color:#8ba3c7; max-width:540px;
    margin:0 auto 28px; line-height:1.65;
}
.stat-row { display:flex; justify-content:center; gap:24px; flex-wrap:wrap; margin-top:20px }
.stat-pill { color:#94a3b8; font-size:13px; font-weight:500 }
.stat-pill strong { color:#e2e8f0; font-weight:700 }

/* ── How it works ───────────────────────────────────────────────── */
.howto-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin:12px 0 }
.howto-step {
    background:#0d1424; border:1px solid #1a2847; border-radius:14px;
    padding:28px 22px; text-align:center; transition:box-shadow .2s, border-color .2s;
}
.howto-step:hover { box-shadow:0 6px 24px rgba(59,130,246,.12); border-color:#3b82f650 }
.howto-num {
    background:linear-gradient(135deg,#3b82f6,#2563eb); color:#fff;
    border-radius:50%; width:36px; height:36px;
    display:inline-flex; align-items:center; justify-content:center;
    font-weight:800; font-size:15px; margin-bottom:14px;
}
.howto-icon { font-size:1.9rem; margin-bottom:10px }
.howto-title { font-weight:700; font-size:14.5px; color:#e2e8f0; margin-bottom:7px }
.howto-desc { font-size:13px; color:#64748b; line-height:1.6 }

/* ── General cards ──────────────────────────────────────────────── */
.card {
    background:#0d1424; border-radius:14px; padding:22px 26px;
    margin-bottom:14px; border:1px solid #1a2847;
    box-shadow:0 2px 12px rgba(0,0,0,.4); color:#e2e8f0;
}
.card-blue   { background:#0f1f4a; border:1px solid #1e3a8a; border-radius:12px; padding:18px 22px; margin-bottom:12px; color:#bfdbfe }
.card-green  { background:#052010; border:1px solid #14532d; border-radius:12px; padding:18px 22px; margin-bottom:12px; color:#bbf7d0 }
.card-amber  { background:#180e00; border:1px solid #78350f; border-radius:12px; padding:18px 22px; margin-bottom:12px; color:#fde68a }
.card-red    { background:#150404; border:1px solid #7f1d1d; border-radius:12px; padding:18px 22px; margin-bottom:12px; color:#fecaca }
.card-slate  { background:#0d1424; border:1px solid #1a2847; border-radius:12px; padding:16px 20px; margin-bottom:10px; color:#e2e8f0 }
.card-pkg    { background:#0f1f4a; border:2px solid #1e3a8a; border-radius:16px; padding:24px 28px; margin:16px 0; color:#bfdbfe }

/* ── Score badge ────────────────────────────────────────────────── */
.score-badge {
    display:inline-flex; align-items:center; justify-content:center;
    border-radius:50%; font-weight:800; color:#fff;
}

/* ── Chips ──────────────────────────────────────────────────────── */
.chip        { display:inline-block; border-radius:6px; padding:3px 9px; font-size:11.5px; font-weight:600; margin:2px; letter-spacing:.01em }
.chip-blue   { background:#1e3a8a30; color:#93c5fd; border:1px solid #1e3a8a50 }
.chip-green  { background:#14532d30; color:#86efac; border:1px solid #14532d50 }
.chip-red    { background:#7f1d1d30; color:#fca5a5; border:1px solid #7f1d1d50 }
.chip-gray   { background:#1e293b60; color:#94a3b8; border:1px solid #33415560 }
.chip-purple { background:#4c1d9530; color:#c4b5fd; border:1px solid #4c1d9550 }
.chip-amber  { background:#78350f30; color:#fcd34d; border:1px solid #78350f50 }

/* ── Job cards ──────────────────────────────────────────────────── */
.job-row {
    background:#0d1424; border:1px solid #1a2847; border-radius:14px;
    padding:20px 22px; margin-bottom:12px;
    transition:box-shadow .18s, border-color .18s, transform .12s;
    color:#e2e8f0;
}
.job-row:hover {
    box-shadow:0 8px 28px rgba(59,130,246,.14);
    border-color:#2d4d9a; transform:translateY(-1px);
}
.job-row-inner {
    display:flex; justify-content:space-between; align-items:flex-start; gap:16px;
}
.job-row-body { flex:1; min-width:0; }
.job-title {
    font-weight:700; font-size:16px; color:#f1f5f9; line-height:1.4;
    word-break:break-word; overflow-wrap:break-word; white-space:normal;
    margin-bottom:4px;
}
.job-meta {
    color:#64748b; font-size:12.5px; margin-top:2px;
    white-space:normal; word-break:break-word; line-height:1.5;
}
.job-desc {
    margin-top:8px; font-size:13px; color:#64748b; line-height:1.6;
    word-break:break-word; overflow-wrap:break-word;
}
.job-score-col {
    display:flex; flex-direction:column; align-items:center;
    flex-shrink:0; min-width:70px;
}
.job-score-badge {
    color:#fff; border-radius:12px; padding:10px 14px;
    font-weight:900; font-size:20px; min-width:62px;
    text-align:center; line-height:1;
}

/* ── Package banner ─────────────────────────────────────────────── */
.pkg-banner {
    background:linear-gradient(90deg,#0c1f5c,#1d4ed8);
    border-radius:14px; padding:18px 26px; margin:14px 0;
    display:flex; align-items:center; justify-content:space-between;
    border:1px solid #1e3a8a;
}

/* ── Section label ──────────────────────────────────────────────── */
.section-tag {
    display:block; font-size:10px; font-weight:700;
    text-transform:uppercase; letter-spacing:.1em;
    color:#475569; margin-bottom:10px; margin-top:4px;
}

/* ── Progress bar ───────────────────────────────────────────────── */
.prog-wrap { height:7px; background:#1e2d45; border-radius:6px; overflow:hidden; margin:5px 0 3px }
.prog-fill { height:100%; border-radius:6px; transition:width .5s ease }

/* ── Alert strips ───────────────────────────────────────────────── */
.alert-strip {
    border-left:3px solid; border-radius:10px;
    padding:12px 16px; margin:8px 0; font-size:13.5px; line-height:1.6;
}
.alert-green { border-color:#22c55e; background:#052e1620; color:#86efac }
.alert-amber { border-color:#f59e0b; background:#78350f20; color:#fde68a }
.alert-red   { border-color:#ef4444; background:#7f1d1d20; color:#fca5a5 }
.alert-blue  { border-color:#3b82f6; background:#1e3a8a20; color:#93c5fd }

/* ── Writing tool cards ─────────────────────────────────────────── */
.tool-card {
    border:1px solid #1a2847; border-radius:10px; padding:13px 17px;
    margin-bottom:8px; background:#0d1424; cursor:pointer;
    transition:all .14s; color:#e2e8f0;
}
.tool-card:hover { border-color:#2d4d9a; background:#0f1f4a }
.tool-card-active { border-color:#3b82f6; background:#0f1f4a }

/* ── Page title ─────────────────────────────────────────────────── */
.page-title {
    font-size:1.75rem; font-weight:800; color:#f1f5f9;
    margin-bottom:4px; letter-spacing:-.03em; line-height:1.2;
}
.page-sub { font-size:14px; color:#64748b; margin-bottom:1.4rem; line-height:1.55 }

/* ── Divider ────────────────────────────────────────────────────── */
hr { border:none; border-top:1px solid #111827; margin:1.4rem 0 }

/* ── Sidebar branding ───────────────────────────────────────────── */

/* ── Buttons ────────────────────────────────────────────────────── */
.stButton > button {
    border-radius:9px !important; font-weight:600 !important;
    min-height:38px !important; font-size:13.5px !important;
    transition:opacity .12s !important;
}
.stButton > button:hover { opacity:.88 !important }

/* ── AI badge ───────────────────────────────────────────────────── */
.ai-badge {
    display:inline-flex; align-items:center; gap:5px;
    background:linear-gradient(135deg,#1e1b4b,#2d2683);
    color:#a5b4fc; border:1px solid #4338ca;
    border-radius:6px; padding:3px 9px; font-size:10.5px; font-weight:700;
    letter-spacing:.04em; text-transform:uppercase;
}

/* ── Today's actions ────────────────────────────────────────────── */
.action-card {
    background:#0d1424; border:1px solid #1a2847; border-radius:10px;
    padding:13px 17px; margin-bottom:8px;
    display:flex; align-items:flex-start; gap:12px;
}
.action-urgent { border-left:3px solid #ef4444 !important }
.action-nudge  { border-left:3px solid #f59e0b !important }
.action-prep   { border-left:3px solid #8b5cf6 !important }
.action-network{ border-left:3px solid #10b981 !important }

/* ── Copy output area ───────────────────────────────────────────── */
.copy-output {
    background:#060c1a; border:1px solid #1a2847; border-radius:10px;
    padding:18px 20px; font-size:13.5px; line-height:1.75;
    color:#e2e8f0; white-space:pre-wrap; word-break:break-word;
}

/* ── Inputs & textareas ─────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background:#0d1424 !important; border:1px solid #1a2847 !important;
    border-radius:9px !important; color:#e2e8f0 !important;
    font-size:14px !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
    border-color:#3b82f6 !important;
    box-shadow:0 0 0 3px rgba(59,130,246,.15) !important;
}

/* ── Tabs ───────────────────────────────────────────────────────── */
[data-testid="stTabs"] [role="tab"] {
    font-weight:600 !important; font-size:13.5px !important;
}

/* ── Expanders ──────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background:#0d1424 !important; border:1px solid #1a2847 !important;
    border-radius:10px !important;
}

/* ══ MOBILE — iPhone & small screens (≤640px) ═══════════════════ */
@media (max-width: 640px) {
    .block-container {
        padding-top:1rem !important; padding-left:1rem !important;
        padding-right:1rem !important;
    }
    .hero-section { padding:28px 20px 24px }
    .hero-title { font-size:1.9rem }
    .hero-sub { font-size:0.9rem }
    .stat-row { gap:12px }
    .howto-grid { grid-template-columns:1fr; gap:10px }

    /* Job cards stack on mobile — score badge goes under title */
    .job-row-inner { flex-direction:column; gap:12px }
    .job-score-col {
        flex-direction:row; justify-content:flex-start;
        align-items:center; gap:10px; min-width:0;
    }
    .job-score-badge { font-size:16px; padding:7px 12px }
    .job-title { font-size:15px }
    .job-row { padding:16px 16px }

    /* Full-width columns */
    [data-testid="column"] { width:100% !important; min-width:100% !important; }

    .card { padding:16px 18px }
    .page-title { font-size:1.4rem }
    div[data-testid="metric-container"] { padding:12px 14px }

    /* Ensure buttons are comfortably tappable */
    .stButton > button { min-height:44px !important; font-size:14px !important }
}

/* ── Medium screens (tablets ~641px–900px) ──────────────────────── */
@media (min-width:641px) and (max-width:900px) {
    .block-container { padding-left:1.2rem !important; padding-right:1.2rem !important }
    .howto-grid { grid-template-columns:1fr 1fr; gap:12px }
    .hero-title { font-size:2.2rem }
    .job-title { font-size:15px }
}
</style>
<script>
// Force sidebar open on every load — Streamlit only applies initial_sidebar_state once
(function() {
    function expandSidebar() {
        // Look for the expand button (sidebar is collapsed)
        var btn = document.querySelector('[data-testid="stExpandSidebarButton"] button');
        if (btn) { btn.click(); return true; }
        return false;
    }
    // Try immediately, then poll briefly in case the DOM isn't ready yet
    if (!expandSidebar()) {
        var attempts = 0;
        var poll = setInterval(function() {
            if (expandSidebar() || attempts++ > 20) clearInterval(poll);
        }, 150);
    }
})();
</script>
""", unsafe_allow_html=True)


# ── Demo resume ───────────────────────────────────────────────────
DEMO_RESUME_TEXT = """Alex Rivera
Marketing Analytics Manager | San Francisco, CA | alex.rivera@email.com

Summary
Results-driven marketing analytics professional with 3 years of experience turning data into revenue. Built dashboards, automated reporting, and led campaigns that grew pipeline by 40%.

Experience
Marketing Analytics Manager — GrowthCo, San Francisco, CA (2022–Present)
• Developed Python scripts to automate weekly reporting, saving 8 hours per week
• Built Tableau dashboards tracking 12 KPIs across 4 marketing channels
• Analyzed A/B test results for email campaigns, improving open rates by 22%
• Managed $500k annual digital advertising budget across Google and Meta

Marketing Analyst — Startup Labs, San Francisco, CA (2021–2022)
• Wrote SQL queries to extract and analyze 2M+ customer records
• Created Excel models forecasting quarterly lead generation targets
• Collaborated with sales team to improve lead scoring model accuracy by 35%

Education
B.S. Business Administration — UC Berkeley, 2021
Concentration in Marketing, Minor in Data Science

Skills
Python, SQL, Tableau, Excel, Google Analytics, Salesforce, HubSpot, Google Ads, Meta Ads, A/B Testing, Data Visualization, Marketing Analytics, Statistical Analysis, R

Certifications
Google Analytics Certified · HubSpot Marketing Hub Certified
"""


def load_demo_resume():
    from resume_parser import parse_resume
    from scorer import get_model
    from resume_editor import full_analysis
    p = parse_resume(DEMO_RESUME_TEXT)
    p["name"] = "Alex Rivera"
    p["years_experience"] = 3
    get_model()
    return p, full_analysis(DEMO_RESUME_TEXT)


# ── Resume examples library ───────────────────────────────────────
RESUME_EXAMPLES = {
    "Software Engineer": {
        "summary": "Full-stack software engineer with 4 years building scalable web applications in Python and React. "
                   "Led migration of monolithic app to microservices, reducing deploy time by 60%. "
                   "Strong background in system design, CI/CD, and cloud infrastructure (AWS).",
        "bullets": [
            "Reduced API latency by 42% by refactoring N+1 database queries and adding Redis caching",
            "Migrated legacy monolith to 12 microservices (Python/FastAPI), cutting deploy time from 45 min → 8 min",
            "Mentored 3 junior engineers; introduced code review standards that reduced bug rate by 28%",
            "Built real-time event processing pipeline handling 50K events/sec using Kafka + Spark",
            "Implemented OAuth 2.0 + JWT auth layer securing 3 internal APIs used by 200K monthly users",
        ],
    },
    "Data Analyst": {
        "summary": "Data analyst with 3 years turning raw business data into decisions at e-commerce and SaaS companies. "
                   "Proficient in SQL, Python, and Tableau. Built dashboards used daily by executive teams. "
                   "Known for translating complex findings into clear business narratives.",
        "bullets": [
            "Built executive Tableau dashboard tracking 12 KPIs — used weekly by VP and CMO for budget decisions",
            "Automated weekly reporting pipeline in Python (pandas + SFTP), saving 6 hours of analyst time per week",
            "Identified $340K in revenue leakage by analyzing cohort retention data across 8 customer segments",
            "Reduced churn by 18% by building predictive model (logistic regression) flagging at-risk customers 30 days early",
            "Queried and cleaned 200M+ row transaction database using SQL to support pricing strategy project",
        ],
    },
    "Product Manager": {
        "summary": "Product manager with 5 years launching consumer and B2B products at Series A–C startups. "
                   "Owned roadmap for a $4M ARR SaaS product from 0→1. "
                   "Skilled at balancing user research, technical constraints, and business strategy.",
        "bullets": [
            "Launched mobile onboarding redesign that improved 7-day activation rate from 31% to 54% (A/B tested)",
            "Owned roadmap for billing module — delivered 4 features in Q3 that drove $1.2M in expansion revenue",
            "Ran 40+ user interviews per quarter, synthesizing insights into 3 product bets approved by executive team",
            "Reduced time-to-value from 14 days to 3 days by redesigning onboarding flow with engineering and design",
            "Defined and tracked OKRs for 8-person product team; achieved 87% of targets in FY2023",
        ],
    },
    "Marketing Analyst": {
        "summary": "Marketing analyst with 3 years of experience driving growth through data at D2C and B2B SaaS companies. "
                   "Specializes in paid acquisition, attribution modeling, and conversion rate optimization. "
                   "Built reporting infrastructure from scratch at two startups.",
        "bullets": [
            "Decreased customer acquisition cost by 31% by reallocating paid budget using multi-touch attribution model",
            "Built automated weekly marketing dashboard in Google Data Studio, replacing 5 manual Sheets reports",
            "Grew email list from 12K to 47K subscribers in 9 months through segmentation and A/B testing",
            "Increased landing page conversion rate from 2.1% to 5.8% through iterative copy and UX testing (15 experiments)",
            "Managed $400K Google Ads budget achieving 3.2x ROAS — 40% above team target for the quarter",
        ],
    },
    "Financial Analyst": {
        "summary": "Financial analyst with 4 years of experience in FP&A and investment analysis at a Fortune 500 and a growth-stage PE portfolio company. "
                   "Built models covering $500M+ in annual budget. CFA Level 2 candidate.",
        "bullets": [
            "Built 5-year rolling forecast model for $120M business unit — adopted as standard by CFO across 3 divisions",
            "Reduced month-end close from 8 days to 4 days by automating variance reporting in Excel VBA",
            "Performed DCF analysis on 12 acquisition targets; 3 recommendations led to deals totaling $85M in EV",
            "Identified $2.3M in cost reduction opportunities through zero-based budgeting review across 6 cost centers",
            "Presented quarterly earnings variance analysis to board of directors — flagged $1.8M EBITDA risk 60 days early",
        ],
    },
    "Project Manager": {
        "summary": "PMP-certified project manager with 6 years delivering enterprise software and infrastructure projects on time and on budget. "
                   "Managed programs up to $8M across distributed teams of 20+. "
                   "Known for risk management and stakeholder communication.",
        "bullets": [
            "Delivered $4.2M ERP implementation 3 weeks ahead of schedule by proactively managing 14 scope risks",
            "Led cross-functional team of 22 (engineering, legal, finance) to launch new client portal — zero downtime",
            "Reduced project overhead costs by 18% by standardizing resource allocation templates across 6 project teams",
            "Managed vendor relationships with 4 third-party contractors, negotiating SLAs that improved delivery time by 25%",
            "Implemented Agile ceremonies across 3 waterfall teams, improving sprint predictability from 54% to 89%",
        ],
    },
    "UX Designer": {
        "summary": "Product designer with 4 years crafting intuitive, accessible experiences for mobile and web applications. "
                   "Led end-to-end design for products used by 500K+ users. "
                   "Strong background in user research, prototyping, and cross-functional collaboration with engineering.",
        "bullets": [
            "Redesigned checkout flow in Figma based on 30 user interviews — reduced cart abandonment by 23%",
            "Built and maintained design system with 80+ components, reducing design-to-dev handoff time by 35%",
            "Ran usability tests with 12 participants per sprint — findings shaped 6 major feature decisions in FY2023",
            "Increased task completion rate for onboarding from 61% to 84% through simplified 3-step wizard design",
            "Partnered with engineering to deliver WCAG 2.1 AA accessibility compliance across 4 core user flows",
        ],
    },
    "Account Manager": {
        "summary": "Account manager with 4 years managing enterprise SaaS accounts and growing revenue through expansion and referrals. "
                   "Consistently exceeded quota (127% average). "
                   "Skilled at multi-threading complex accounts and turning at-risk customers into advocates.",
        "bullets": [
            "Managed portfolio of 42 enterprise accounts ($3.2M ARR) with 94% retention and 121% net revenue retention",
            "Expanded 8 accounts from starter to enterprise tier — generated $480K in incremental ARR in 12 months",
            "Reduced churn in at-risk segment by 40% by implementing proactive QBR program with 90-day check-in cadence",
            "Closed 3 multi-year contract renewals totaling $1.1M by aligning product roadmap to customer strategic goals",
            "Achieved 127% of quota in FY2023 — ranked 3rd of 18 AMs nationally",
        ],
    },
}

EXAMPLE_TIPS = {
    "summary": [
        "Recruiters spend 7–17 seconds on first pass — your summary is the only section guaranteed to be seen",
        "Formula: [X years] + [specialty] → [top achievement] → [2–3 key tools/skills]",
        "3–5 sentences max — anything longer gets skipped",
        "Write in third-person implied: 'Senior analyst with 5 years...' (not 'I am...')",
        "Avoid filler: 'results-driven', 'team player', 'passionate about' add zero signal",
        "Include both full form and acronym on first use: 'Search Engine Optimization (SEO)'",
    ],
    "bullets": [
        "Start every bullet with an action verb — never 'Responsible for', 'Helped', or 'Assisted'",
        "Framework: [Action verb] + [what you did] + [measurable result]",
        "Add at least one metric per bullet — %, $, headcount, time saved, or volume (10k+ records)",
        "Quantified bullets are 40% more likely to get callbacks than duty-only bullets",
        "3–6 bullets per role; put your strongest, most quantified bullet FIRST",
        "Keep each bullet under 2 lines (30 words max) — recruiters rarely read past bullet 3",
        "Show achievement, not duty: assume the reader knows the generic job description",
        "Use past tense for old roles, present tense for your current role",
    ],
    "ats": [
        "75%+ of resumes are filtered by ATS before a human sees them — keyword matching dominates",
        "Target 10–15 keywords from the job description, placed naturally in summary, skills, and experience",
        "Use standard section headers: 'Work Experience', 'Education', 'Skills' — not creative alternatives",
        "Single-column layout only — tables and text boxes break ATS parsers",
        "Submit .docx or text-based PDF — never a scanned PDF, image, or .pages file",
        "Spell out both acronym and full name: 'Certified Public Accountant (CPA)'",
    ],
}
