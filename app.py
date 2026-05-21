import os
import re
import tempfile
from datetime import date as _date, timedelta as _td

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import analytics as _analytics
import auth as _auth

st.set_page_config(
    page_title="CareerIQ",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports ──────────────────────────────────────────────────────
from resume_parser import extract_text, parse_resume
from job_fetcher import fetch_jobs, has_adzuna
from scorer import score_job, get_skill_gaps, get_model
from resume_editor import full_analysis
import tracker
from utils import (
    inject_css, alert, chip, score_badge, score_color, progress_bar,
    STATUS_EMOJI, STATUS_COLOR, _todays_tasks, load_demo_resume, xe,
)

inject_css()

# ── Auth gate ─────────────────────────────────────────────────────
def _auth_gate():
    """Show login/register UI. Returns True if user is authenticated."""
    if st.session_state.get("auth_user_id"):
        return True

    st.markdown("""
<div style='text-align:center;padding:3rem 1rem 1.5rem'>
  <div style='font-size:2.6rem;font-weight:900;color:#f1f5f9;letter-spacing:-.04em;margin-bottom:.5rem'>
    Career<span style='color:#60a5fa'>IQ</span>
  </div>
  <div style='color:#64748b;font-size:1rem;margin-bottom:2rem;max-width:480px;margin-left:auto;margin-right:auto;line-height:1.6'>
    AI-powered career intelligence — resume scoring, job matching,<br>cover letters, interview prep, and application tracking.
  </div>
</div>
""", unsafe_allow_html=True)

    # ── One-click demo ────────────────────────────────────────────
    demo_col = st.columns([1, 2, 1])[1]
    with demo_col:
        if st.button("Try Live Demo", use_container_width=True, type="primary", key="try_demo"):
            with st.spinner("Loading demo…"):
                res = _auth.ensure_demo_user()
                if res["ok"]:
                    uid = res["user_id"]
                    # Seed demo resume if not already stored
                    try:
                        import profile_store as _ps
                        if not _ps.get_resume_text(uid):
                            from utils import DEMO_RESUME_TEXT
                            _ps.set_resume_text(DEMO_RESUME_TEXT, uid)
                    except Exception:
                        pass
                    st.session_state["auth_user_id"]  = uid
                    st.session_state["auth_user_name"] = res["name"]
                    st.session_state["active_user_id"] = uid
                    _analytics.track("session_start", user_id=uid)
                    st.rerun()

        st.markdown("<div style='text-align:center;color:#334155;font-size:11.5px;margin:.5rem 0 1.25rem'>Loads a sample resume &amp; pre-built profile — no sign-up needed</div>",
                    unsafe_allow_html=True)

    col = st.columns([1, 2, 1])[1]
    with col:
        tab_login, tab_reg = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            email = st.text_input("Email", key="login_email")
            pwd   = st.text_input("Password", type="password", key="login_pwd")
            if st.button("Sign In", use_container_width=True, type="primary", key="signin_btn"):
                res = _auth.login(email, pwd)
                if res["ok"]:
                    st.session_state["auth_user_id"]   = res["user_id"]
                    st.session_state["auth_user_name"]  = res["name"]
                    st.session_state["active_user_id"]  = res["user_id"]
                    _analytics.track("session_start", user_id=res["user_id"])
                    st.rerun()
                else:
                    st.error(res["error"])

        with tab_reg:
            name  = st.text_input("Full Name", key="reg_name")
            email = st.text_input("Email", key="reg_email")
            pwd   = st.text_input("Password (6+ chars)", type="password", key="reg_pwd")
            if st.button("Create Account", use_container_width=True, type="primary", key="register_btn"):
                res = _auth.register(email, name, pwd)
                if res["ok"]:
                    st.session_state["auth_user_id"]   = res["user_id"]
                    st.session_state["auth_user_name"]  = res["name"]
                    st.session_state["active_user_id"]  = res["user_id"]
                    _analytics.track("session_start", user_id=res["user_id"])
                    st.success(f"Welcome, {res['name']}!")
                    st.rerun()
                else:
                    st.error(res["error"])

    return False

# Wrapper resolves to _dashboard_impl at call time — defined later in this file
def _dashboard():
    globals()["_dashboard_impl"]()

# Logo (stSidebarHeader — above nav) and navigation must be set up BEFORE any
# st.stop() call, otherwise Streamlit falls back to filename-based auto-discovery.
st.logo("static/logo.svg")
_pg = st.navigation([
    st.Page(_dashboard,               title="Dashboard",        default=True),
    st.Page("pages/1_Resume.py",      title="Resume Editor"),
    st.Page("pages/2_Jobs.py",        title="Find Jobs"),
    st.Page("pages/11_Company.py",    title="Company Research"),
    st.Page("pages/9_Apply.py",       title="Apply Engine"),
    st.Page("pages/12_AutoApply.py",  title="Auto Apply"),
    st.Page("pages/7_Market.py",      title="Market Intel"),
    st.Page("pages/4_Write.py",       title="Writing Suite"),
    st.Page("pages/5_Interview.py",   title="Interview Prep"),
    st.Page("pages/3_LinkedIn.py",    title="LinkedIn"),
    st.Page("pages/6_Track.py",       title="Track Apps"),
    st.Page("pages/8_Profile.py",     title="My Profile"),
    st.Page("pages/10_Stats.py",      title="Analytics"),
])

# ── Sidebar — always rendered regardless of auth state ───────────
with st.sidebar:
    _sb_profile = st.session_state.get("resume")
    if _sb_profile:
        _sb_score    = st.session_state.get("resume_score", 0)
        _sb_sc       = score_color(_sb_score)
        _sb_analysis = st.session_state.get("resume_analysis") or {}
        _sb_grade    = _sb_analysis.get("grade", "—")
        _sb_ver      = st.session_state.get("active_resume_version")
        _sb_verline  = (f"<div style='font-size:10px;color:#7c3aed;font-weight:600;margin-top:2px'>v: {xe(_sb_ver)}</div>"
                        if _sb_ver else "")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:12px;padding:0'>"
            f"{score_badge(_sb_score, 44)}"
            f"<div style='min-width:0;flex:1'>"
            f"<div style='font-weight:700;font-size:14px;color:#f1f5f9;line-height:1.2'>{xe(_sb_profile['name'])}</div>"
            f"<div style='font-size:11.5px;color:{_sb_sc};font-weight:600'>{_sb_score}% &mdash; Grade {xe(_sb_grade)}</div>"
            f"<div style='font-size:11px;color:#475569;margin-top:1px'>{len(_sb_profile['skills'])} skills detected</div>"
            f"{_sb_verline}</div></div>",
            unsafe_allow_html=True
        )
    else:
        if st.button("Load Demo Resume", use_container_width=True, key="sb_demo"):
            with st.spinner("Loading…"):
                _p, _an = load_demo_resume()
                st.session_state.resume          = _p
                st.session_state.resume_analysis = _an
                st.session_state.resume_score    = _an["overall_score"]
            st.rerun()

    import profile_store as _ps
    _all_profiles = []
    try:
        _all_profiles = _ps.get_all_profiles()
    except Exception:
        pass

    if len(_all_profiles) > 1:
        _uid_opts  = [uid for uid, _ in _all_profiles]
        _name_opts = [name for _, name in _all_profiles]
        _cur_uid   = st.session_state.get("active_user_id", 1)
        _cur_idx   = _uid_opts.index(_cur_uid) if _cur_uid in _uid_opts else 0
        _sel_name  = st.selectbox("Active profile", _name_opts, index=_cur_idx,
                                  key="sb_user_select", label_visibility="collapsed")
        _sel_uid   = _uid_opts[_name_opts.index(_sel_name)]
        if _sel_uid != st.session_state.get("active_user_id", 1):
            st.session_state.active_user_id = _sel_uid
            for _k in ["resume","resume_analysis","resume_score","dashboard_jobs",
                       "dashboard_search_role","apply_pkg_job","apply_pkg_id"]:
                st.session_state.pop(_k, None)
            st.rerun()

if not _auth_gate():
    st.stop()

# ── Track session once per login ──────────────────────────────────
if not st.session_state.get("_session_tracked"):
    _analytics.track("session_start", user_id=st.session_state.get("auth_user_id", 1))
    st.session_state["_session_tracked"] = True

# ── Auto-load stored resume for active user if session is empty ───
def _try_autoload_resume():
    if st.session_state.get("resume"):
        return
    try:
        import profile_store as _pstore
        _uid = st.session_state.get("active_user_id", 1)
        # Always load the user profile into session state for salary scoring
        if not st.session_state.get("user_profile"):
            st.session_state.user_profile = _pstore.get_profile(_uid)
        _stored = _pstore.get_resume_text(_uid)
        if _stored and len(_stored) > 200:
            from resume_parser import parse_resume
            from resume_editor import full_analysis
            _p = parse_resume(_stored)
            _analysis = full_analysis(_stored)
            st.session_state.resume          = _p
            st.session_state.resume_analysis = _analysis
            st.session_state.resume_score    = _analysis["overall_score"]
    except Exception:
        pass

_try_autoload_resume()


# ── Dashboard-only helpers ────────────────────────────────────────

def generate_resume_suggestions(profile, analysis):
    """Generate personalized resume improvement suggestions from analysis."""
    suggestions = []

    for sec in analysis.get("missing_sections", []):
        tip = analysis.get("missing_tips", {}).get(sec, "")
        suggestions.append((f"Add a {sec} section",
                            tip or f"A {sec} section is expected by most ATS systems and recruiters."))

    bullets = analysis.get("bullet_analyses", [])
    weak = [b for b in bullets if b["score"] < 60]
    if weak:
        worst = sorted(weak, key=lambda x: x["score"])[0]
        suggestions.append((
            "Strengthen your weakest bullet points",
            f"Your weakest bullet: *\"{worst['text'][:80]}...\"*\n\n"
            f"Issues: {', '.join(worst['issues'][:2])}\n\n"
            f"Fix: {worst['suggestion']}"
        ))

    all_bullets = [b["text"] for b in bullets]
    has_numbers = sum(1 for b in all_bullets if any(c.isdigit() for c in b))
    if all_bullets and has_numbers == 0 and len(all_bullets) >= 4:
        suggestions.append((
            "Consider adding a few metrics where natural",
            f"None of your bullets currently include numbers. Where it fits naturally, "
            "a specific figure (%, $, time, team size) makes the impact more concrete — "
            "but only add them when they genuinely exist."
        ))

    if len(profile.get("skills", [])) < 5:
        suggestions.append((
            "Expand your Skills section",
            "Fewer than 5 skills detected. A dedicated Skills section dramatically improves ATS keyword match rates."
        ))

    if "Summary" in analysis.get("missing_sections", []):
        suggestions.append((
            "Add a professional summary at the top",
            "Recruiters spend ~6 seconds on first pass. A 2–3 sentence summary hooks them immediately.\n\n"
            "Template: *[Role] with [X] years of experience in [key areas]. Proven track record of [top achievement]. Seeking [target].*"
        ))

    for sec_name, sec_data in analysis.get("section_analyses", {}).items():
        if sec_data["score"] < 50 and sec_data.get("suggestions"):
            suggestions.append((
                f"Improve your {sec_name} section (score: {sec_data['score']}/100)",
                "\n\n".join(f"• {s}" for s in sec_data["suggestions"][:3])
            ))

    return suggestions[:6]


def infer_job_queries(profile):
    """Return (primary_role, explanation, secondary_roles) from resume signals."""
    ROLE_MATRIX = {
        "Software Engineer": {
            "title_kw": ["software engineer","software developer","swe","backend","frontend","full stack","web developer","devops"],
            "text_kw":  ["developed","built","deployed","implemented","architected","ci/cd","microservices","api","kubernetes"],
            "skill_kw": ["python","java","javascript","typescript","react","node","go","aws","gcp","azure","git","flask","django"],
            "degree_kw":["computer science","cs","software engineering","computer engineering","information systems"],
        },
        "Data Analyst": {
            "title_kw": ["data analyst","analytics analyst","reporting analyst","bi analyst","business intelligence"],
            "text_kw":  ["analyzed","dashboard","visualization","reporting","trends","kpi","metrics","tableau","power bi"],
            "skill_kw": ["sql","python","pandas","r","tableau","power bi","excel","statistics","data analysis"],
            "degree_kw":["statistics","mathematics","data science","economics","quantitative"],
        },
        "Data Scientist": {
            "title_kw": ["data scientist","ml engineer","machine learning","ai engineer","research scientist"],
            "text_kw":  ["model","prediction","algorithm","neural","deep learning","nlp","computer vision","training"],
            "skill_kw": ["pytorch","tensorflow","scikit-learn","machine learning","deep learning","nlp","python","spark"],
            "degree_kw":["data science","statistics","machine learning","artificial intelligence","computer science"],
        },
        "Business Analyst": {
            "title_kw": ["business analyst","management analyst","business systems","operations analyst","process analyst"],
            "text_kw":  ["requirements","stakeholders","process improvement","user stories","gap analysis","workflow","sop"],
            "skill_kw": ["sql","excel","visio","jira","confluence","agile","scrum","business analysis","powerpoint"],
            "degree_kw":["business","business administration","management","information systems","mba"],
        },
        "Product Manager": {
            "title_kw": ["product manager","product owner","group pm","director of product","vp product"],
            "text_kw":  ["roadmap","prioritization","user research","sprint","feature","launch","go-to-market","okr"],
            "skill_kw": ["product management","jira","roadmapping","agile","user research","analytics","a/b testing"],
            "degree_kw":["business","computer science","engineering","mba"],
        },
        "Marketing Coordinator": {
            "title_kw": ["marketing","digital marketing","content","social media","brand","growth","seo","sem"],
            "text_kw":  ["campaign","engagement","impressions","clicks","conversion","content","brand","social","seo"],
            "skill_kw": ["marketing","social media","content creation","seo","google analytics","hubspot","mailchimp","canva"],
            "degree_kw":["marketing","communications","advertising","public relations","journalism"],
        },
        "Financial Analyst": {
            "title_kw": ["financial analyst","finance analyst","fp&a","investment analyst","equity analyst"],
            "text_kw":  ["financial model","valuation","forecast","budget","variance","p&l","balance sheet","dcf"],
            "skill_kw": ["financial modeling","excel","bloomberg","python","sql","accounting","cfa","finance"],
            "degree_kw":["finance","accounting","economics","business","investment banking"],
        },
        "Project Manager": {
            "title_kw": ["project manager","program manager","pmo","scrum master","delivery manager"],
            "text_kw":  ["managed","coordinated","delivered","timeline","milestone","stakeholder","budget","risk"],
            "skill_kw": ["pmp","agile","scrum","jira","ms project","smartsheet","project management","risk management"],
            "degree_kw":["business","engineering","management","mba","information systems"],
        },
        "Consultant": {
            "title_kw": ["consultant","consulting","advisory","strategy analyst","associate consultant"],
            "text_kw":  ["recommendations","client","framework","analysis","presentation","deliverable","strategy","deck"],
            "skill_kw": ["consulting","excel","powerpoint","data analysis","sql","python","problem solving"],
            "degree_kw":["business","economics","engineering","mba","liberal arts"],
        },
        "Account Manager": {
            "title_kw": ["account manager","account executive","sales","territory manager","client success","customer success"],
            "text_kw":  ["revenue","quota","pipeline","prospect","client","renewal","upsell","crm","closed won"],
            "skill_kw": ["salesforce","crm","sales","account management","negotiation","prospecting","hubspot"],
            "degree_kw":["business","marketing","communications","sales"],
        },
    }

    raw    = profile.get("raw_text", "").lower()
    skills = [s.lower() for s in profile.get("skills", [])]
    titles = " ".join(t.lower() for t in profile.get("titles", []))

    scores = {}
    for role, cfg in ROLE_MATRIX.items():
        s = 0
        for kw in cfg["title_kw"]:
            if kw in titles: s += 5
        for kw in cfg["text_kw"]:
            if kw in raw: s += 2
        for kw in cfg["skill_kw"]:
            if kw in skills or kw in raw: s += 1
        for kw in cfg.get("degree_kw", []):
            if kw in raw: s += 1
        scores[role] = s

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    primary_role, _ = ranked[0]
    secondary = [r for r, sc in ranked[1:4] if sc > 0]

    winning_cfg = ROLE_MATRIX[primary_role]
    matched_skills = [kw for kw in winning_cfg["skill_kw"] if kw in skills or kw in raw][:4]
    matched_titles = [kw for kw in winning_cfg["title_kw"] if kw in titles][:2]
    reasons = []
    if matched_titles: reasons.append(f"job title: {matched_titles[0]}")
    if matched_skills: reasons.append(f"skills: {', '.join(matched_skills)}")
    if not reasons: reasons.append("general profile match")

    return primary_role, f"Based on {'; '.join(reasons)}", secondary


# ── Dashboard page ────────────────────────────────────────────────

def _dashboard_impl():
    profile = st.session_state.get("resume")

    if not profile:
        # ── Hero ──
        st.markdown("""
<div class='hero-section'>
  <div class='hero-badge'>100% Free · No Account Required · No Paywalls</div>
  <div class='hero-title'>The smartest free career tool<br><span>for your job search.</span></div>
  <div class='hero-sub'>Resume scoring &amp; editing · Job matching across 26 cities · AI writing suite · Application tracking — everything in one place.</div>
  <div class='stat-row'>
    <span class='stat-pill'><strong>26</strong> cities</span>
    <span class='stat-pill'><strong>3</strong> job sources</span>
    <span class='stat-pill'><strong>23</strong> writing tools</span>
    <span class='stat-pill'><strong>0</strong> paywalls</span>
    <span class='stat-pill'><strong>AI-powered</strong></span>
  </div>
</div>
""", unsafe_allow_html=True)

        col_up, col_demo = st.columns([3, 1])
        with col_up:
            uploaded = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf","docx"], label_visibility="collapsed")
        with col_demo:
            st.markdown("<div style='padding-top:8px'>", unsafe_allow_html=True)
            if st.button("Try Demo Resume", use_container_width=True):
                with st.spinner("Analyzing…"):
                    p, analysis = load_demo_resume()
                    st.session_state.resume          = p
                    st.session_state.resume_analysis = analysis
                    st.session_state.resume_score    = analysis["overall_score"]
                st.rerun()

        if uploaded:
            # Validate size (10 MB max) and extension before touching the filesystem
            _MAX_BYTES = 10 * 1024 * 1024
            if uploaded.size > _MAX_BYTES:
                st.error("File is too large (max 10 MB). Please upload a smaller resume.")
                st.stop()
            _raw_ext = uploaded.name.rsplit(".", 1)[-1].lower() if "." in uploaded.name else ""
            if _raw_ext not in ("pdf", "docx"):
                st.error("Only PDF and DOCX files are accepted.")
                st.stop()
            suffix = "." + _raw_ext
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.read())
                    tmp_path = tmp.name
                with st.spinner("Analyzing your resume — loading AI model on first run (30–60 s)…"):
                    text = extract_text(tmp_path)
                    if not text or len(text.strip()) < 50:
                        st.error("Could not read text from this file. Try a different PDF or paste your resume.")
                        st.stop()
                    p        = parse_resume(text)
                    get_model()
                    analysis = full_analysis(text)
                    _analytics.track("resume_analyzed")
                    st.session_state.resume          = p
                    st.session_state.resume_analysis = analysis
                    st.session_state.resume_score    = analysis["overall_score"]
                    try:
                        import profile_store as _ps
                        _uid = st.session_state.get("active_user_id", 1)
                        _ps.set_resume_text(text, _uid)
                        st.session_state.user_profile = _ps.get_profile(_uid)
                    except Exception:
                        pass
                    try:
                        from vector_store import index_resume as _vsi
                        import threading as _th
                        _th.Thread(
                            target=_vsi,
                            args=(st.session_state.get("active_user_id", 1), text, p.get("name", "")),
                            daemon=True,
                        ).start()
                    except Exception:
                        pass
                    for k in ["dashboard_jobs","dashboard_search_role","apply_pkg_job",
                              "apply_pkg_id","pkg_ats","pkg_cl","pkg_ty","pkg_bullets","tailor_results"]:
                        st.session_state.pop(k, None)
            except Exception as _e:
                st.error(f"Upload failed: {_e}")
                st.stop()
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            st.rerun()

        st.markdown("---")
        st.markdown("<div class='section-tag'>How it works</div>", unsafe_allow_html=True)
        st.markdown("""
<div class='howto-grid'>
  <div class='howto-step'>
    <div class='howto-icon'>📄</div>
    <div class='howto-num'>1</div>
    <div class='howto-title'>Upload your resume</div>
    <div class='howto-desc'>Get an instant score, section-by-section breakdown, bullet-point coaching, and specific rewrite suggestions.</div>
  </div>
  <div class='howto-step'>
    <div class='howto-icon'>🔍</div>
    <div class='howto-num'>2</div>
    <div class='howto-title'>Find &amp; match jobs</div>
    <div class='howto-desc'>AI semantically scores every live job against your resume across 26 cities worldwide — sorted by fit.</div>
  </div>
  <div class='howto-step'>
    <div class='howto-icon'>✍️</div>
    <div class='howto-num'>3</div>
    <div class='howto-title'>Apply smarter</div>
    <div class='howto-desc'>One-click Apply Package: cover letter + ATS scan + targeted bullets + thank-you email, all tailored to the job.</div>
  </div>
</div>
""", unsafe_allow_html=True)

        st.markdown("---")
        f1, f2, f3, f4 = st.columns(4)
        for col, icon, title, desc in [
            (f1, "📊", "Resume Analyzer", "Score, section breakdown, bullet coach, ATS scanner, and specific rewrites"),
            (f2, "🔍", "Job Matching", "Semantic AI scoring against live jobs across 26 cities in real-time"),
            (f3, "✍️", "Writing Suite", "23 tools: cover letters, essays, emails, LinkedIn — tailored to you and the job"),
            (f4, "📋", "App Tracker", "Pipeline dashboard from saved → applied → interview → offer"),
        ]:
            col.markdown(f"<div class='card' style='text-align:center'><div style='font-size:1.9rem;margin-bottom:10px'>{icon}</div><div style='font-weight:700;font-size:14px;margin-bottom:6px'>{title}</div><div style='color:#64748b;font-size:12.5px;line-height:1.5'>{desc}</div></div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            "<div style='text-align:center;color:#94a3b8;font-size:12px'>"
            "🔒 Resume scoring runs on-server — your data never leaves CareerIQ &nbsp;·&nbsp; "
            "📡 Live data from FRED, BLS, Adzuna, Jobicy &nbsp;·&nbsp; "
            "🤖 Semantic matching via sentence-transformers · Writing tools powered by Claude"
            "</div>", unsafe_allow_html=True
        )

    else:
        # ── Full Dashboard ─────────────────────────────────────────
        analysis = st.session_state.get("resume_analysis") or full_analysis(profile["raw_text"])

        # Header row
        hdr_l, hdr_r = st.columns([7, 1])
        _sc = score_color(analysis["overall_score"])
        hdr_l.markdown(
            f"<div style='font-size:1.7rem;font-weight:900;color:#f1f5f9;letter-spacing:-.025em;white-space:nowrap;overflow:visible'>"
            f"{profile['name']}</div>"
            f"<div style='font-size:13px;color:#64748b;margin-top:2px'>"
            f"Resume score: <b style='color:{_sc}'>"
            f"{analysis['overall_score']}% — Grade {analysis['grade']}</b></div>",
            unsafe_allow_html=True
        )
        if hdr_r.button("↺ New Resume", key="dash_new_resume"):
            for k in ["resume","resume_analysis","resume_score","dashboard_jobs",
                      "dashboard_search_role","apply_pkg_job","apply_pkg_id"]:
                st.session_state.pop(k, None)
            st.rerun()

        dash_tab1, dash_tab2, dash_tab3 = st.tabs(["Resume Health", "Job Matches", "Today's Actions"])

        # ──────── TAB 1: Resume Health ────────────────────────────
        with dash_tab1:
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(
                f"<div class='card' style='text-align:center'>"
                f"<div style='font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;letter-spacing:.05em'>Resume Score</div>"
                f"<div style='margin-top:8px'>{score_badge(analysis['overall_score'], 60)}</div>"
                f"<div style='font-size:24px;font-weight:800;margin-top:6px;color:#f1f5f9'>{analysis['grade']}</div>"
                f"</div>", unsafe_allow_html=True
            )
            c2.markdown(
                f"<div class='card' style='text-align:center'>"
                f"<div style='font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;letter-spacing:.05em'>Skills Detected</div>"
                f"<div style='font-size:42px;font-weight:800;color:#3b82f6;margin-top:8px'>{len(profile['skills'])}</div>"
                f"</div>", unsafe_allow_html=True
            )
            c3.markdown(
                f"<div class='card' style='text-align:center'>"
                f"<div style='font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;letter-spacing:.05em'>Sections Found</div>"
                f"<div style='font-size:42px;font-weight:800;color:#8b5cf6;margin-top:8px'>{len(analysis['sections'])}</div>"
                f"</div>", unsafe_allow_html=True
            )
            missing_n = len(analysis["missing_sections"])
            c4.markdown(
                f"<div class='card' style='text-align:center'>"
                f"<div style='font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;letter-spacing:.05em'>Missing Sections</div>"
                f"<div style='font-size:42px;font-weight:800;color:{'#ef4444' if missing_n else '#10b981'};margin-top:8px'>{missing_n}</div>"
                f"</div>", unsafe_allow_html=True
            )

            col_left, col_right = st.columns([5, 5])
            with col_left:
                st.markdown("<div class='section-tag' style='margin-top:12px'>Section Breakdown</div>", unsafe_allow_html=True)
                for sec_name, sec_data in analysis["section_analyses"].items():
                    s = sec_data["score"]
                    bar_color = score_color(s)
                    issues_html = "".join(f"<div style='font-size:12px;color:#fca5a5;margin-top:2px'>⚠ {i}</div>" for i in sec_data["issues"][:2])
                    sug_html    = "".join(f"<div style='font-size:12px;color:#93c5fd;margin-top:2px'>💡 {sg}</div>" for sg in sec_data["suggestions"][:1])
                    st.markdown(
                        f"<div style='margin-bottom:12px'>"
                        f"<div style='display:flex;justify-content:space-between'>"
                        f"<span style='font-weight:600;color:#e2e8f0'>{sec_name}</span>"
                        f"<span style='font-size:12px;font-weight:700;color:{bar_color}'>{s}%</span></div>"
                        f"{progress_bar(s, bar_color)}"
                        f"{issues_html}{sug_html}</div>",
                        unsafe_allow_html=True
                    )
                if analysis["missing_sections"]:
                    st.markdown("<div class='section-tag' style='margin-top:8px'>Missing Sections</div>", unsafe_allow_html=True)
                    for sec in analysis["missing_sections"]:
                        tip = analysis["missing_tips"].get(sec, "")
                        st.markdown(alert(f"<b>No {xe(sec)} section</b> — {xe(tip)}", "red"), unsafe_allow_html=True)

                # ── Score explanation ──────────────────────────────
                _expl = analysis.get("score_explanation", {})
                if _expl:
                    with st.expander(f"Why {analysis['overall_score']}%? — see what's moving your score", expanded=False):
                        st.markdown(
                            f"<div style='font-size:13px;color:#94a3b8;margin-bottom:12px;line-height:1.6'>"
                            f"{xe(_expl['summary'])}</div>",
                            unsafe_allow_html=True
                        )
                        for _d in _expl.get("drivers", []):
                            _sc = "#10b981" if _d["sign"] == "+" else "#ef4444" if _d["sign"] == "−" else "#f59e0b"
                            st.markdown(
                                f"<div style='display:flex;gap:10px;align-items:flex-start;margin-bottom:8px'>"
                                f"<span style='font-size:15px;font-weight:900;color:{_sc};flex-shrink:0;margin-top:1px'>{xe(_d['sign'])}</span>"
                                f"<div><div style='font-size:13px;font-weight:600;color:#e2e8f0'>{xe(_d['label'])}</div>"
                                f"<div style='font-size:12px;color:#64748b;margin-top:2px;line-height:1.5'>{xe(_d['detail'])}</div></div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        if _expl.get("next_moves"):
                            st.markdown("<div style='font-size:11px;font-weight:700;text-transform:uppercase;color:#3b82f6;margin:14px 0 6px;letter-spacing:.06em'>Next moves</div>", unsafe_allow_html=True)
                            for _mv in _expl["next_moves"]:
                                st.markdown(f"<div style='font-size:12.5px;color:#93c5fd;margin-bottom:4px'>→ {xe(_mv)}</div>", unsafe_allow_html=True)

            with col_right:
                st.markdown("<div class='section-tag' style='margin-top:12px'>Detected Skills</div>", unsafe_allow_html=True)
                st.markdown(" ".join(chip(s, "blue") for s in profile["skills"]), unsafe_allow_html=True)

                _exp_content = analysis["sections"].get("Experience", "")
                if _exp_content:
                    st.markdown("<div class='section-tag' style='margin-top:16px'>Work Experience</div>", unsafe_allow_html=True)
                    _exp_lines = [l.strip() for l in _exp_content.split("\n") if l.strip()]
                    # Heuristic: lines that look like job titles/companies vs bullet points
                    _roles, _bullets = [], []
                    for _ln in _exp_lines[:30]:
                        if _ln.startswith(("•", "-", "*", "–", "·")):
                            _bullets.append(_ln.lstrip("•-*–· "))
                        else:
                            _roles.append(_ln)
                    if _roles:
                        for _r in _roles[:6]:
                            st.markdown(
                                f"<div style='font-size:12.5px;font-weight:600;color:#e2e8f0;margin-top:6px'>{xe(_r)}</div>",
                                unsafe_allow_html=True
                            )
                    if _bullets:
                        with st.expander("Show responsibilities", expanded=False):
                            for _b in _bullets[:12]:
                                st.markdown(f"- {xe(_b)}")

                st.markdown("<div class='section-tag' style='margin-top:16px'>Top Resume Improvements</div>", unsafe_allow_html=True)
                suggestions = generate_resume_suggestions(profile, analysis)
                if suggestions:
                    for title, detail in suggestions[:4]:
                        with st.expander(title):
                            st.markdown(detail)
                else:
                    st.markdown(alert("Resume looks solid — head to Jobs to find your best matches.", "green"), unsafe_allow_html=True)

            # ── A/B Vault comparison ──
            from utils import _load_vault
            _vault_dash = _load_vault()
            _vstats_dash = tracker.get_version_stats()
            if len(_vault_dash) >= 2 and _vstats_dash:
                st.markdown("---")
                st.markdown("<div class='section-tag'>Resume A/B Performance</div>", unsafe_allow_html=True)
                _best = max(_vstats_dash, key=lambda v: _vstats_dash[v]["response_rate"]) if _vstats_dash else None
                _ab_cols = st.columns(min(len(_vstats_dash), 4))
                for _abi, (_vn, _vs) in enumerate(sorted(_vstats_dash.items(), key=lambda x: -x[1]["response_rate"])):
                    _rr = _vs.get("response_rate", 0)
                    _tapps = _vs.get("applied",0) + _vs.get("interview",0) + _vs.get("offer",0) + _vs.get("rejected",0)
                    _rr_c = "#10b981" if _rr >= 10 else "#f59e0b" if _rr >= 5 else "#ef4444"
                    _best_str = " 🏆" if _vn == _best and _tapps > 0 else ""
                    if _abi < len(_ab_cols):
                        _ab_cols[_abi].markdown(
                            f"<div class='card' style='text-align:center'>"
                            f"<div style='font-size:12px;font-weight:700;color:#94a3b8'>{_vn}{_best_str}</div>"
                            f"<div style='font-size:28px;font-weight:900;color:{_rr_c};margin:6px 0'>{_rr}%</div>"
                            f"<div style='font-size:11px;color:#64748b'>response rate<br>{_tapps} apps · {_vs.get('interview',0)} interviews</div>"
                            f"</div>", unsafe_allow_html=True
                        )

        # ──────── TAB 2: Job Matches ──────────────────────────────
        with dash_tab2:
            if "dashboard_search_role" not in st.session_state:
                inferred_role, infer_reason, infer_secondary = infer_job_queries(profile)
                st.session_state.dashboard_search_role  = inferred_role
                st.session_state.dashboard_infer_reason = infer_reason
                st.session_state.dashboard_secondary    = infer_secondary

            if "dashboard_jobs" not in st.session_state:
                with st.spinner("Finding best matches for you…"):
                    jobs = fetch_jobs(st.session_state.dashboard_search_role, "", 15)
                    _analytics.track("jobs_searched", meta=st.session_state.dashboard_search_role)
                    for j in jobs:
                        j["score"]   = score_job(profile["raw_text"], j["description"], j.get("title",""))
                        j["matched"], j["missing"] = get_skill_gaps(profile["raw_text"], j["description"])
                    jobs.sort(key=lambda j: j.get("score",0), reverse=True)
                    st.session_state.dashboard_jobs = jobs[:8]

            jobs         = st.session_state.get("dashboard_jobs", [])
            role_used    = st.session_state.get("dashboard_search_role","")
            infer_reason = st.session_state.get("dashboard_infer_reason","")
            secondary    = st.session_state.get("dashboard_secondary",[])

            col_rh, col_ref = st.columns([3,1])
            with col_rh:
                st.caption(f"Auto-detected: **{role_used}** · {infer_reason}")
                if secondary:
                    sec_btns = st.columns(min(len(secondary), 3))
                    for i, sec_role in enumerate(secondary[:3]):
                        with sec_btns[i]:
                            if st.button(f"Try: {sec_role}", key=f"sec_{i}"):
                                st.session_state.dashboard_search_role  = sec_role
                                st.session_state.dashboard_infer_reason = "manual selection"
                                st.session_state.pop("dashboard_jobs", None)
                                st.rerun()
            if col_ref.button("↺ Refresh", key="dash_ref"):
                for k in ["dashboard_jobs","dashboard_search_role","dashboard_infer_reason","dashboard_secondary"]:
                    st.session_state.pop(k, None)
                st.rerun()

            for j in jobs[:8]:
                s      = j.get("score", 0)
                bg     = score_color(s)
                salary = ""
                if j.get("salary_min") and j.get("salary_max"):
                    salary = f"  ·  ${int(j['salary_min']):,}–${int(j['salary_max']):,}"
                matched_chips = " ".join(chip(sk,"green") for sk in j.get("matched",[])[:4])
                missing_chips = " ".join(chip(sk,"red")   for sk in j.get("missing", [])[:2])
                # Escape all API-supplied fields before embedding in HTML
                _jt = xe(j['title']); _jc = xe(j['company']); _jl = xe(j['location'])
                st.markdown(
                    f"<div class='job-row'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                    f"<div style='flex:1'>"
                    f"<div style='font-weight:700;font-size:15px;color:#f1f5f9'>{_jt}</div>"
                    f"<div style='color:#64748b;font-size:12px;margin-top:2px'>"
                    f"<b style='color:#94a3b8'>{_jc}</b> · {_jl}{salary}</div>"
                    f"<div style='margin-top:6px'>{matched_chips}{missing_chips}</div>"
                    f"</div>"
                    f"<div style='background:{bg};color:#fff;border-radius:10px;padding:8px 12px;"
                    f"font-weight:900;font-size:18px;min-width:56px;text-align:center;"
                    f"margin-left:14px;flex-shrink:0'>{s}%</div>"
                    f"</div></div>",
                    unsafe_allow_html=True
                )
                da, db, _ = st.columns([1.3, 1.5, 4])
                with da:
                    if tracker.is_saved(j["id"]):
                        st.button("✅ Saved", key=f"dsv_{j['id']}", disabled=True, use_container_width=True)
                    else:
                        if st.button("Save", key=f"dsv_{j['id']}", use_container_width=True):
                            tracker.save_job(j, s); st.rerun()
                with db:
                    _jurl = str(j.get("url","")).strip()
                    if _jurl.startswith("https://") or _jurl.startswith("http://"):
                        st.link_button("Apply ↗", _jurl, use_container_width=True)

            st.markdown(
                "<div style='text-align:center;margin-top:12px'>"
                "<span style='font-size:13px;color:#64748b'>Want more results and filters? → </span>"
                "</div>", unsafe_allow_html=True
            )

        # ──────── TAB 3: Today's Actions ─────────────────────────
        with dash_tab3:
            _all_apps = tracker.get_all()
            _tasks = _todays_tasks(apps=_all_apps)

            # ── Job Search Health Score ───────────────────────────
            _hs = tracker.get_health_score()
            if _hs["total_applied"] > 0:
                _rr_color = "#10b981" if _hs["response_rate"] >= 10 else "#f59e0b" if _hs["response_rate"] >= 5 else "#ef4444"
                _rr_bench = "above avg ✓" if _hs["response_rate"] >= 5 else "below avg — try A/B testing your resume headline"
                _ir_color = "#10b981" if _hs["interview_rate"] >= 15 else "#f59e0b" if _hs["interview_rate"] >= 8 else "#ef4444"
                _h1, _h2, _h3, _h4 = st.columns(4)
                _h1.markdown(f"<div class='card' style='text-align:center'><div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Applied</div><div style='font-size:36px;font-weight:900;color:#f1f5f9'>{_hs['total_applied']}</div><div style='font-size:10px;color:#64748b'>{_hs['week_applied']} this week</div></div>", unsafe_allow_html=True)
                _h2.markdown(f"<div class='card' style='text-align:center'><div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Response Rate</div><div style='font-size:36px;font-weight:900;color:{_rr_color}'>{_hs['response_rate']}%</div><div style='font-size:10px;color:#64748b'>{_rr_bench}</div></div>", unsafe_allow_html=True)
                _h3.markdown(f"<div class='card' style='text-align:center'><div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Interviews</div><div style='font-size:36px;font-weight:900;color:{_ir_color}'>{_hs['total_interviews']}</div><div style='font-size:10px;color:#64748b'>{_hs['interview_rate']}% of apps</div></div>", unsafe_allow_html=True)
                _h4.markdown(f"<div class='card' style='text-align:center'><div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Follow-ups Due</div><div style='font-size:36px;font-weight:900;color:{'#ef4444' if _hs['due_followups'] else '#10b981'}'>{_hs['due_followups']}</div><div style='font-size:10px;color:#64748b'>{'action needed' if _hs['due_followups'] else 'all clear'}</div></div>", unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
            _TASK_STYLE = {
                "urgent":  ("#ef4444", "⏰"),
                "nudge":   ("#f59e0b", "📬"),
                "prep":    ("#8b5cf6", "🎓"),
                "network": ("#10b981", "🤝"),
            }

            _week_ago = _date.today() - _td(days=7)
            _apps_wk  = sum(1 for a in _all_apps
                            if a.get("date_applied") and a["status"] in ("applied","interview","offer","rejected")
                            and _date.fromisoformat(a["date_applied"][:10]) >= _week_ago)
            _wk_goal  = st.session_state.get("weekly_app_goal", 5)

            # Weekly pace bar
            _pct       = min(100, int(_apps_wk / max(_wk_goal, 1) * 100))
            _pct_color = "#10b981" if _pct >= 100 else "#3b82f6" if _pct >= 60 else "#f59e0b"
            _pace_c1, _pace_c2 = st.columns([4, 1])
            with _pace_c1:
                st.markdown(
                    f"<div style='margin-bottom:16px;background:#1e293b;border:1px solid #334155;"
                    f"border-radius:10px;padding:14px 18px'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:12px;"
                    f"font-weight:600;color:#94a3b8;margin-bottom:8px'>"
                    f"<span>Weekly Applications</span>"
                    f"<span style='color:{_pct_color}'>{_apps_wk}/{_wk_goal} this week</span></div>"
                    f"<div style='background:#334155;border-radius:6px;height:10px'>"
                    f"<div style='background:{_pct_color};width:{_pct}%;height:10px;border-radius:6px'></div></div>"
                    f"<div style='font-size:11px;color:#64748b;margin-top:6px'>"
                    f"{'✅ On pace!' if _pct >= 80 else f'Apply to {_wk_goal - _apps_wk} more this week to hit your goal'}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            with _pace_c2:
                _new_goal = st.number_input("Goal/wk", min_value=1, max_value=50, value=_wk_goal, step=1, key="weekly_goal_input")
                if _new_goal != _wk_goal:
                    st.session_state.weekly_app_goal = _new_goal

            # Action items
            st.markdown("<div class='section-tag'>Action Items</div>", unsafe_allow_html=True)
            if _tasks:
                for urgency, task_title, detail in _tasks:
                    clr, icon = _TASK_STYLE.get(urgency, ("#64748b", "•"))
                    st.markdown(
                        f"<div class='action-card action-{urgency}'>"
                        f"<span style='font-size:1.1rem'>{icon}</span>"
                        f"<div><div style='font-weight:700;font-size:13px;color:#f1f5f9'>{task_title}</div>"
                        f"<div style='font-size:12px;color:#94a3b8;margin-top:2px'>{detail}</div></div>"
                        f"</div>", unsafe_allow_html=True
                    )
            else:
                st.markdown(
                    "<div class='card-green'>✅ <b>No urgent tasks today.</b> Keep applying and follow-ups will appear here as you hear back.</div>",
                    unsafe_allow_html=True
                )

            # ── Job Search Intelligence ───────────────────────────
            _saved_apps = [a for a in _all_apps if a["status"] in ("saved", "applied", "interview")]
            if _saved_apps and profile:
                st.markdown("---")
                st.markdown("<div class='section-tag'>Job Search Intelligence</div>", unsafe_allow_html=True)

                # Role distribution
                from collections import Counter
                _role_counts = Counter()
                for _a in _saved_apps:
                    _t = (_a.get("title") or "").lower()
                    for _rk in ["engineer", "analyst", "scientist", "manager", "coordinator",
                                "consultant", "designer", "developer", "specialist", "associate"]:
                        if _rk in _t:
                            _role_counts[_rk.title()] += 1
                            break
                    else:
                        _role_counts["Other"] += 1

                _avg_score = int(sum(a.get("score", 0) for a in _saved_apps) / max(len(_saved_apps), 1))
                _best_app  = max(_saved_apps, key=lambda a: a.get("score", 0)) if _saved_apps else None

                _ic1, _ic2, _ic3 = st.columns(3)
                _ic1.markdown(
                    f"<div class='card' style='text-align:center'>"
                    f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Jobs Tracked</div>"
                    f"<div style='font-size:36px;font-weight:900;color:#f1f5f9'>{len(_saved_apps)}</div>"
                    f"<div style='font-size:11px;color:#64748b'>{len([a for a in _saved_apps if a['status']=='applied'])} applied · {len([a for a in _saved_apps if a['status']=='interview'])} interviewing</div>"
                    f"</div>", unsafe_allow_html=True
                )
                _ic2.markdown(
                    f"<div class='card' style='text-align:center'>"
                    f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Avg Fit Score</div>"
                    f"<div style='font-size:36px;font-weight:900;color:{score_color(_avg_score)}'>{_avg_score}%</div>"
                    f"<div style='font-size:11px;color:#64748b'>across tracked jobs</div>"
                    f"</div>", unsafe_allow_html=True
                )
                _ic3.markdown(
                    f"<div class='card' style='text-align:center'>"
                    f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Best Match</div>"
                    f"<div style='font-size:20px;font-weight:800;color:#10b981;margin-top:6px;line-height:1.3'>{xe(_best_app['title'][:22] + ('…' if len(_best_app.get('title','')) > 22 else '')) if _best_app else '—'}</div>"
                    f"<div style='font-size:11px;color:#64748b'>{xe(_best_app.get('company','')[:20]) if _best_app else ''} · {_best_app.get('score',0)}%</div>"
                    f"</div>", unsafe_allow_html=True
                )

                # Persistent skill gap: skills that appear in most targeted role families
                # Use the top role type the person is applying to and surface missing skills
                _resume_skills_lower = {s.lower() for s in profile.get("skills", [])}
                _raw_lower = profile.get("raw_text", "").lower()
                _top_role = _role_counts.most_common(1)[0][0].lower() if _role_counts else ""

                from linkedin_editor import ROLE_LINKEDIN_SKILLS
                _role_skill_map = {k.lower(): v for k, v in ROLE_LINKEDIN_SKILLS.items()}
                _role_target_skills = []
                for _rk, _rv in _role_skill_map.items():
                    if _top_role and (_top_role in _rk or any(w in _rk for w in _top_role.split())):
                        _role_target_skills = _rv
                        break

                if _role_target_skills:
                    _persistent_gaps = [
                        s for s in _role_target_skills
                        if s.lower() not in _resume_skills_lower
                        and s.lower().replace(" ", "") not in _raw_lower.replace(" ", "")
                    ][:5]
                    if _persistent_gaps:
                        st.markdown(
                            f"<div style='margin-top:12px;padding:14px 18px;background:#1e293b;"
                            f"border:1px solid #334155;border-radius:10px'>"
                            f"<div style='font-size:11px;font-weight:700;color:#f59e0b;text-transform:uppercase;"
                            f"letter-spacing:.06em;margin-bottom:8px'>Persistent skill gaps across your target roles</div>"
                            f"<div style='font-size:13px;color:#94a3b8;margin-bottom:10px'>"
                            f"These skills appear in most <b style='color:#e2e8f0'>{_top_role.title()}</b> roles you're tracking "
                            f"but aren't on your resume. Adding them could lift your match scores:</div>"
                            f"<div>{' '.join(chip(s, 'amber') for s in _persistent_gaps)}</div>"
                            f"<div style='font-size:12px;color:#64748b;margin-top:10px'>"
                            f"→ Add these to your Skills section and add a bullet for each one you can genuinely demonstrate.</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                # Best unacted opportunity
                _unacted = [a for a in _saved_apps if a["status"] == "saved"
                            and a.get("score", 0) >= 65]
                if _unacted:
                    _best_unacted = max(_unacted, key=lambda a: a.get("score", 0))
                    st.markdown(
                        f"<div style='margin-top:12px;padding:14px 18px;background:#0f2a1a;"
                        f"border:1px solid #166534;border-radius:10px'>"
                        f"<div style='font-size:11px;font-weight:700;color:#10b981;text-transform:uppercase;"
                        f"letter-spacing:.06em;margin-bottom:6px'>Best unacted opportunity</div>"
                        f"<div style='font-size:14px;font-weight:700;color:#f1f5f9'>"
                        f"{xe(_best_unacted['title'])} @ {xe(_best_unacted['company'])}</div>"
                        f"<div style='font-size:12px;color:#6ee7b7;margin-top:4px'>"
                        f"{_best_unacted.get('score', 0)}% match — saved but not yet applied. "
                        f"This is your strongest saved opportunity.</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )


_pg.run()

