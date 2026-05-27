import re
import streamlit as st
from collections import Counter
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, score_color, score_badge, xe
from job_fetcher import fetch_jobs, fetch_jobs_multicity, CITY_PRESETS, get_fetch_warnings
from scorer import score_job, get_skill_gaps, salary_adjusted_score, ghost_score, batch_score_jobs
from salary_intel import estimate as _bls_estimate, match_role as _bls_match
import tracker

inject_css()

st.markdown("<div class='page-title'>Find Jobs</div><div class='page-sub'>Search live job postings, score them against your resume, and build your application package.</div>", unsafe_allow_html=True)

profile = st.session_state.get("resume")
if not profile:
    st.markdown(alert("Load your resume on the Dashboard to see fit scores.", "blue"), unsafe_allow_html=True)

# ── Cached fetch wrappers ──────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _cached_fetch_multicity(role: str, cities_key: str, num: int):
    cities = list(cities_key.split("|||"))
    return fetch_jobs_multicity(role, cities, num)

@st.cache_data(ttl=1800, show_spinner=False)
def _cached_fetch_jobs(role: str, location: str, num: int):
    return fetch_jobs(role, location, num)

# ── Helper functions ───────────────────────────────────────────────
# States requiring salary ranges in job postings as of 2026
_PAY_TRANSPARENCY_STATES = frozenset([
    "california", " ca,", " ca ", "colorado", " co,", " co ", "hawaii", " hi,",
    "illinois", " il,", "chicago", "maine", " me,", "maryland", " md,",
    "massachusetts", " ma,", "minnesota", " mn,", "new jersey", " nj,",
    "new york", " ny,", "vermont", " vt,", "washington", " wa,",
    "connecticut", " ct,", "nevada", " nv,", "rhode island", " ri,",
])


def _pay_transparency_violation(location: str, has_salary: bool) -> bool:
    """Return True if job is in a pay-transparency state but lists no salary."""
    if has_salary:
        return False
    loc = " " + location.lower() + " "
    return any(s in loc for s in _PAY_TRANSPARENCY_STATES)


_STOP_WORDS = frozenset({"and","the","for","with","this","that","are","you","have",
                          "will","our","from","about","into","your","their"})


def _title_gap(job_title: str, resume_lower: str) -> str:
    """Return the most important title word missing from the resume, or ''."""
    words = [w.lower() for w in re.findall(r'[a-zA-Z]{5,}', job_title)
             if w.lower() not in _STOP_WORDS]
    if not words:
        return ""
    hits = sum(1 for w in words if w in resume_lower)
    if hits / max(len(words), 1) >= 0.5:
        return ""
    return next((w for w in words if w not in resume_lower), "")


_JD_RED_FLAGS = [
    ("rockstar",        "⚡ 'Rockstar' culture"),
    ("ninja",           "⚡ 'Ninja' culture"),
    ("guru",            "⚡ 'Guru' culture"),
    ("hustle",          "⚡ Hustle culture"),
    ("we are a family", "⚡ 'We're a family'"),
    ("like a family",   "⚡ 'Like a family'"),
    ("wear many hats",  "⚠ 'Wear many hats' — may be understaffed"),
    ("fast-paced",      "⚠ 'Fast-paced' — may signal chaos or overwork"),
    ("fast paced",      "⚠ 'Fast-paced' — may signal chaos or overwork"),
    ("startup mindset", "⚠ 'Startup mindset' — may mean unclear role scope"),
    ("competitive salary",       "💰 No salary listed — 'competitive' may be below market"),
    ("competitive compensation", "💰 No salary listed — 'competitive' may be below market"),
    ("commensurate with experience", "💰 No salary listed"),
    ("unlimited pto",           "⚠ 'Unlimited PTO' — research shows employees often take less"),
    ("unlimited vacation",      "⚠ 'Unlimited PTO' — research shows employees often take less"),
    ("self-starter",            "⚠ 'Self-starter' — may mean minimal management support"),
    ("comfortable with ambiguity", "⚠ 'Comfortable with ambiguity' — may signal poor planning"),
    ("above and beyond",        "⚡ 'Above and beyond' — may expect unpaid overtime"),
    ("work hard, play hard",    "⚡ 'Work hard, play hard'"),
    ("passionate",              "⚠ 'Passionate' — culture fit pressure"),
]

_PIPELINE_PHRASES = [
    ("we are always looking for", "📋 Always hiring — may be building a pipeline"),
    ("talent pool",               "📋 Talent pool posting — timeline unclear"),
    ("future opportunities",      "📋 Speculative posting — no confirmed opening"),
    ("pipeline of candidates",    "📋 Pipeline role — not an immediate opening"),
    ("join our growing team",     "⚠ Generic posting — verify role is active"),
    ("open to candidates",        "📋 May be exploratory — confirm headcount"),
]

def _jd_red_flags(description: str) -> list:
    desc_lower = description.lower()
    seen = set()
    flags = []
    for keyword, label in _JD_RED_FLAGS:
        if keyword in desc_lower and label not in seen:
            seen.add(label)
            flags.append(label)
    return flags

def _ghost_job_info(job: dict) -> dict:
    days_old = None
    date_str = job.get("date", "")
    if date_str:
        try:
            from datetime import date as _gdt
            days_old = (_gdt.today() - _gdt.fromisoformat(date_str[:10])).days
        except Exception:
            pass
    desc_lower = job.get("description", "").lower()
    pipeline_flags = [label for phrase, label in _PIPELINE_PHRASES if phrase in desc_lower]
    return {
        "days_old":      days_old,
        "is_stale":      days_old is not None and days_old > 21,
        "pipeline_flags": pipeline_flags,
    }

def _interview_prep_pack(job, profile):
    title   = job.get("title", "this role")
    company = job.get("company", "the company")
    desc    = job.get("description", "").lower()
    _COMP_PATTERNS = {
        "leadership":         ["led","managed","team","supervised","mentored","directed"],
        "data analysis":      ["data","analysis","reporting","metrics","kpi","sql","excel","tableau"],
        "communication":      ["presented","collaborated","stakeholder","communicated","cross-functional"],
        "problem-solving":    ["resolved","improved","optimized","solved","troubleshot","root cause"],
        "project management": ["deadline","project","timeline","delivery","coordinated","milestone"],
        "technical":          ["built","developed","implemented","engineered","designed","deployed"],
        "customer-facing":    ["client","customer","account","service","support","relationship"],
        "growth/results":     ["increased","grew","improved","reduced","saved","revenue","efficiency"],
    }
    _Q_MAP = {
        "leadership":         "Tell me about a time you led a team through a challenge.",
        "data analysis":      "Walk me through a time you used data to drive a business decision.",
        "communication":      "Describe a time you explained a complex topic to a non-technical audience.",
        "problem-solving":    "Give me an example of a difficult problem you solved and your approach.",
        "project management": "Tell me about a project you managed end-to-end. What was your process?",
        "technical":          "Walk me through a technical project you're most proud of.",
        "customer-facing":    "Describe a difficult customer situation and how you handled it.",
        "growth/results":     "What's the most impactful result you've delivered in a past role?",
    }
    detected = [c for c, kws in _COMP_PATTERNS.items() if any(k in desc for k in kws)][:4]
    if not detected:
        detected = ["problem-solving", "communication", "growth/results"]
    questions = [_Q_MAP[c] for c in detected if c in _Q_MAP]
    questions += [
        f"Why do you want to work at {company}?",
        f"Why are you interested in the {title} role specifically?",
        "Where do you see yourself in 3 years?",
    ]
    role_label = (profile.get("titles") or ["professional"])[0] if profile else "professional"
    skills_str = ", ".join((profile.get("skills") or [])[:3]) if profile else "relevant skills"
    tyab = (
        f"I'm a {role_label} with experience in {skills_str}. "
        f"In my most recent role, I [your top achievement here]. "
        f"I'm drawn to {company} because [one specific thing you researched about them], "
        f"and I see this {title} role as the opportunity to [connect your goal to their need]."
    )
    return {
        "questions": questions[:6],
        "tyab": tyab,
        "star": [
            "**S — Situation:** Set the scene. Where, when, what team?",
            "**T — Task:** What was YOUR specific responsibility?",
            "**A — Action:** What did YOU do? (say 'I', not 'we')",
            "**R — Result:** Measurable outcome — %, $, time saved, team size.",
        ],
        "detected": detected,
    }

def _draft_referral_ask(contact, job, profile):
    your_name = (profile.get("name", "") if profile else "") or "[Your Name]"
    role = (profile.get("titles") or [""])[0] if profile else ""
    role_ctx = f" as a {role}" if role else ""
    return (
        f"Hi {contact['name']},\n\n"
        f"Hope you're doing well! I came across a {job['title']} opening at {job['company']} "
        f"and it looks like a strong fit for my background{role_ctx}.\n\n"
        f"Since you work there, I wanted to reach out — would you be willing to pass my resume "
        f"along or point me to the right person to contact?\n\n"
        f"Happy to share more about my background. Here's the posting: {job.get('url', '[link]')}\n\n"
        f"Thanks so much — really appreciate it!\n\n"
        f"Best,\n{your_name}"
    )

def _generate_targeted_bullets(profile, job, missing_kw):
    templates = {
        "data analysis": "Analyzed {ctx} data sets using Python and Excel, extracting insights to support {out} decisions — add: [X% efficiency gain or key finding]",
        "sql": "Queried relational databases using SQL to aggregate and transform {ctx} data for {out} reporting — add: [table/dataset size or time saved]",
        "excel": "Built {ctx} Excel models with pivot tables and dynamic formulas to track {out} KPIs — add: [hours saved or decision supported]",
        "project management": "Coordinated {ctx} project timeline and cross-functional communication, ensuring on-time delivery of {out} deliverables — add: [team size, deadline met]",
        "python": "Automated {ctx} workflow in Python, eliminating manual processing for {out} operations — add: [X hours/week saved]",
        "financial modeling": "Developed {ctx} financial projection models in Excel to evaluate {out} scenarios for stakeholder decisions — add: [$ amount modeled]",
        "research": "Conducted {ctx} market and competitive research, synthesizing findings into actionable {out} recommendations — add: [number of sources, audience]",
        "leadership": "Led {ctx} initiative with {out} team members, setting milestones, delegating tasks, and resolving blockers — add: [outcome or impact]",
        "communication": "Presented {ctx} analysis findings to {out}, translating complex data into clear, decision-ready insights — add: [audience size]",
        "collaboration": "Partnered with {ctx} stakeholders to align on {out} requirements and deliver project outcomes on schedule — add: [team size or result]",
    }
    ctxs  = ["client-facing", "key operational", "cross-functional", "strategic"]
    outs  = ["business", "financial", "marketing", "operational"]
    lines = []
    for i, kw in enumerate(missing_kw[:3]):
        kw_l = kw.lower()
        tmpl = next((t for k, t in templates.items() if k in kw_l or kw_l in k),
                    "Applied {ctx} skills to {out} project, driving measurable impact — add: [specific metric]")
        line = tmpl.format(ctx=ctxs[i % len(ctxs)], out=outs[i % len(outs)])
        lines.append(f"• {line[0].upper()}{line[1:]}")
    if not lines:
        lines = ["• No specific missing keywords identified — your resume already aligns well with this role."]
    return "\n\n".join(lines)

# ── Semantic Search (ChromaDB) ─────────────────────────────────────
with st.expander("🔍 Semantic Search — search indexed jobs by meaning, not keywords", expanded=False):
    st.caption("Search jobs already indexed from your recent searches. Type what you're looking for in plain English.")
    sem_query = st.text_input(
        "Describe what you want",
        placeholder="e.g. build financial models at a fintech startup, Python data engineering role",
        key="sem_query",
        label_visibility="collapsed",
    )
    sem_n = st.slider("Results", 5, 30, 10, key="sem_n")
    if st.button("Search Semantic Index", type="primary", key="sem_search"):
        if sem_query.strip():
            try:
                from vector_store import search_jobs as _vs_search, store_stats as _vs_stats
                _stats = _vs_stats()
                if _stats["jobs_indexed"] == 0:
                    st.warning("No jobs indexed yet — run a regular search first to populate the index.")
                else:
                    with st.spinner(f"Searching {_stats['jobs_indexed']} indexed jobs…"):
                        _sem_results = _vs_search(sem_query.strip(), n_results=sem_n)
                    if _sem_results:
                        st.markdown(f"<div style='font-size:12px;color:#64748b;margin-bottom:8px'>{len(_sem_results)} semantic matches</div>", unsafe_allow_html=True)
                        for _sr in _sem_results:
                            _sc = _sr.get("score", 0)
                            _bg = score_color(_sc)
                            st.markdown(
                                f"<div class='card-slate' style='padding:12px 16px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center'>"
                                f"<div>"
                                f"<div style='font-weight:700;font-size:13px;color:#f1f5f9'>{xe(_sr.get('title',''))}</div>"
                                f"<div style='font-size:12px;color:#64748b;margin-top:2px'>{xe(_sr.get('company',''))} · {xe(_sr.get('location',''))}</div>"
                                f"</div>"
                                f"<div style='background:{_bg};color:#fff;border-radius:8px;padding:4px 10px;"
                                f"font-weight:800;font-size:14px;min-width:48px;text-align:center'>{_sc}%</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                    else:
                        st.info("No semantic matches found. Try different wording or run a regular search first.")
            except Exception as _e:
                st.error(f"Semantic search unavailable: {_e}")
        else:
            st.error("Enter a search query.")

st.markdown("---")

# ── Search Form ────────────────────────────────────────────────────
mode = st.radio("Search mode", ["City Presets", "Custom"], horizontal=True, label_visibility="collapsed")

with st.form("search_form"):
    col1, col2 = st.columns([3,1])
    role = col1.text_input("Role / Keywords", placeholder="e.g. Business Analyst, Marketing Coordinator")
    num  = col2.selectbox("Per city", [5, 10, 20], index=1)

    if mode == "City Presets":
        domestic = [k for k in CITY_PRESETS if CITY_PRESETS[k]["country"]=="us" or k=="🌍 Remote"]
        intl     = [k for k in CITY_PRESETS if CITY_PRESETS[k]["country"]!="us" and k!="🌍 Remote"]
        selected_cities = []

        st.markdown("<div style='font-weight:600;margin:8px 0 4px'>United States</div>", unsafe_allow_html=True)
        dom_cols = st.columns(5)
        DEFAULT_DOM = {"🗽 New York","🌲 Raleigh","🏙️ Charlotte"}
        for i, k in enumerate(domestic):
            with dom_cols[i % 5]:
                _label = k.split(" ", 1)[-1] if " " in k else k
                if st.checkbox(_label, value=(k in DEFAULT_DOM), key=f"c_{k}"):
                    selected_cities.append(k)

        st.markdown("<div style='font-weight:600;margin:8px 0 4px'>International</div>", unsafe_allow_html=True)
        intl_cols = st.columns(5)
        for i, k in enumerate(intl):
            with intl_cols[i % 5]:
                _label = k.split(" ", 1)[-1] if " " in k else k
                if st.checkbox(_label, value=False, key=f"c_{k}"):
                    selected_cities.append(k)
    else:
        custom_loc = st.text_input("Location", placeholder="e.g. Philadelphia, PA")

    submitted = st.form_submit_button("Search Jobs", type="primary", use_container_width=True)

if submitted:
    if not role.strip():
        st.error("Enter a role or keywords.")
    else:
        if mode == "City Presets":
            if not selected_cities:
                st.error("Select at least one city.")
            else:
                with st.spinner(f"Searching {len(selected_cities)} cities…"):
                    cities_key = "|||".join(sorted(selected_cities))
                    jobs = _cached_fetch_multicity(role.strip(), cities_key, num)
        else:
            with st.spinner("Fetching jobs…"):
                jobs = _cached_fetch_jobs(role.strip(), custom_loc if mode == "Custom" else "", num)

        for src, reason in get_fetch_warnings():
            st.warning(f"**{src}** unavailable: {reason}", icon="⚠️")

        if not jobs:
            st.error("No results. Try different keywords or add Adzuna keys.")
        else:
            if profile:
                _user_profile = st.session_state.get("user_profile")
                with st.spinner(f"Scoring {len(jobs)} jobs against your resume…"):
                    batch_score_jobs(profile["raw_text"], jobs, _user_profile)
                    jobs.sort(key=lambda j: j.get("score", 0), reverse=True)
            st.session_state.jobs      = jobs
            st.session_state.jobs_role = role
            for _k in ["apply_pkg_id","apply_pkg_job","pkg_ats","pkg_ats_id","pkg_cl","pkg_ty","pkg_bullets"]:
                st.session_state.pop(_k, None)

if "jobs" in st.session_state and st.session_state.jobs:
    jobs       = st.session_state.jobs
    role_label = st.session_state.get("jobs_role","")
    city_counts = Counter(j.get("city_label", j.get("location","")) for j in jobs)

    col_hdr, col_sort = st.columns([4,1])
    col_hdr.markdown(f"<div style='color:#64748b;font-size:13px;padding-top:8px'><b>{len(jobs)}</b> results for <b>{role_label}</b></div>", unsafe_allow_html=True)
    sort_by = col_sort.selectbox("Sort", ["Fit Score","Company","City","Date"], label_visibility="collapsed")

    if sort_by == "Fit Score": jobs = sorted(jobs, key=lambda j: j.get("score",0), reverse=True)
    elif sort_by == "Company": jobs = sorted(jobs, key=lambda j: j.get("company","").lower())
    elif sort_by == "City":    jobs = sorted(jobs, key=lambda j: j.get("city_label", j.get("location","")))
    elif sort_by == "Date":    jobs = sorted(jobs, key=lambda j: j.get("date",""), reverse=True)

    # ── Filters ──────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns(4)
    hide_stale    = fc1.checkbox("Hide stale (>21d)", value=False, key="filter_stale")
    remote_only   = fc2.checkbox("Remote / hybrid only", value=False, key="filter_remote")
    min_sal_label = fc3.selectbox("Min salary (listed only)", ["Any", "$50K+", "$75K+", "$100K+", "$125K+"], key="filter_salary")
    hide_no_sal   = fc4.checkbox("Only show jobs with salary listed", value=False, key="filter_has_sal")
    _MIN_SAL_MAP  = {"Any": 0, "$50K+": 50_000, "$75K+": 75_000, "$100K+": 100_000, "$125K+": 125_000}
    min_sal       = _MIN_SAL_MAP[min_sal_label]

    _total_before = len(jobs)
    _no_sal_count = sum(1 for j in jobs if not (j.get("salary_min") or j.get("salary_max")))

    def _passes_filters(j):
        if hide_stale:
            _gs = j.get("ghost_score")
            if _gs is None:
                _gs, _ = ghost_score(j)
            if _gs >= 30:
                return False
        if remote_only:
            loc = (j.get("location","") + j.get("city_label","")).lower()
            if "remote" not in loc and "hybrid" not in loc:
                return False
        has_sal = bool(j.get("salary_min") or j.get("salary_max"))
        if hide_no_sal and not has_sal:
            return False
        if min_sal > 0 and has_sal:
            sal = j.get("salary_max") if j.get("salary_max") is not None else j.get("salary_min", 0)
            if (sal or 0) < min_sal:
                return False
        return True

    jobs = [j for j in jobs if _passes_filters(j)]
    _filter_active = hide_stale or remote_only or min_sal > 0 or hide_no_sal
    if _filter_active:
        _sal_note = f" · {_no_sal_count} jobs have no salary listed" if not hide_no_sal and _no_sal_count > 0 else ""
        st.markdown(
            f"<div style='font-size:12px;color:#64748b;margin:2px 0 6px'>"
            f"Showing <b>{len(jobs)}</b> of {_total_before} jobs after filters{_sal_note}</div>",
            unsafe_allow_html=True
        )

    # ── Batch save ───────────────────────────────────────────
    if jobs:
        bs_col, _ = st.columns([2, 5])
        with bs_col:
            if st.button("Save All Visible", key="batch_save_btn", use_container_width=True):
                _rv = st.session_state.get("active_resume_version")
                saved_count = sum(1 for j in jobs if tracker.save_job(j, j.get("score", 0), resume_version=_rv))
                st.success(f"Saved {saved_count} new job(s).")
                st.rerun()

    st.markdown("---")
    for j in jobs:
        s     = j.get("score", 0)
        bg    = score_color(s)
        flag  = CITY_PRESETS.get(j.get("city_label",""), {}).get("flag","")
        salary = ""
        if j.get("salary_min") and j.get("salary_max"):
            salary = f" · ${int(j['salary_min']):,}–${int(j['salary_max']):,}"
        elif j.get("salary_min"):
            salary = f" · ${int(j['salary_min']):,}+"
        else:
            # BLS estimate fallback — shown in gray with ~ prefix
            _bls_key = _bls_match(j.get("title", ""))
            if _bls_key:
                _bls = _bls_estimate(_bls_key, j.get("location", ""), 2)
                if _bls and _bls.get("p25") and _bls.get("p75"):
                    salary = (
                        f" · <span style='color:#475569'>~${int(_bls['p25']):,}–"
                        f"${int(_bls['p75']):,} est.</span>"
                    )

        matched_all = j.get("matched", [])
        missing_all = j.get("missing", [])
        matched_c = " ".join(chip(sk,"green") for sk in matched_all[:3])
        if len(matched_all) > 3: matched_c += chip(f"+{len(matched_all)-3}", "gray")
        missing_c = " ".join(chip(sk,"red") for sk in missing_all[:2])
        if len(missing_all) > 2: missing_c += chip(f"+{len(missing_all)-2} missing", "amber")

        # Use scorer-computed ghost signals if available, else compute on the fly
        _g_signals = j.get("ghost_signals")
        _g_score   = j.get("ghost_score")
        if _g_signals is None:
            _g_score, _g_signals = ghost_score(j)
        ghost_html = ""
        if _g_score is not None and _g_score >= 30:
            _ghost_bg  = "#fef2f2" if _g_score >= 60 else "#fffbeb"
            _ghost_clr = "#991b1b" if _g_score >= 60 else "#92400e"
            for sig in _g_signals[:2]:
                ghost_html += (
                    f"<span style='display:inline-block;background:{_ghost_bg};color:{_ghost_clr};"
                    f"border:1px solid {_ghost_bg};border-radius:4px;padding:1px 7px;"
                    f"font-size:10.5px;font-weight:600;margin-right:4px'>{xe(sig)}</span>"
                )
        if ghost_html:
            ghost_html = f"<div style='margin-top:4px'>{ghost_html}</div>"
        # Salary mismatch note
        _sal_note = j.get("salary_note", "")
        sal_note_html = ""
        if _sal_note:
            sal_note_html = (
                f"<div style='margin-top:4px'>"
                f"<span style='display:inline-block;background:#fef3c7;color:#92400e;"
                f"border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600'>"
                f"💰 {xe(_sal_note)}</span></div>"
            )

        red_flags = _jd_red_flags(j.get("description",""))
        flags_html = ""
        if red_flags:
            flags_html = (
                "<div style='margin-top:6px'>"
                + " ".join(
                    f"<span style='display:inline-block;background:#fef3c7;color:#92400e;"
                    f"border-radius:4px;padding:1px 7px;font-size:11px;font-weight:600;margin:1px'>{f}</span>"
                    for f in red_flags[:4]
                )
                + "</div>"
            )

        # ── Timing badge ────────────────────────────────────────────
        _timing_html = ""
        _date_str = j.get("date", "")
        if _date_str:
            try:
                from datetime import date as _dobj
                _days_old = (_dobj.today() - _dobj.fromisoformat(_date_str[:10])).days
                if _days_old <= 3:
                    _timing_html = f"<span style='font-size:10.5px;font-weight:700;color:#10b981'>🟢 {_days_old}d old — apply now</span>"
                elif _days_old <= 7:
                    _timing_html = f"<span style='font-size:10.5px;font-weight:700;color:#f59e0b'>🟡 {_days_old}d old</span>"
                elif _days_old <= 21:
                    _timing_html = f"<span style='font-size:10.5px;font-weight:700;color:#f97316'>🟠 {_days_old}d old</span>"
                else:
                    _timing_html = f"<span style='font-size:10.5px;font-weight:700;color:#ef4444'>🔴 {_days_old}d old</span>"
            except Exception:
                pass

        # ── Salary transparency flag ─────────────────────────────────
        _trans_html = ""
        _has_sal = bool(j.get("salary_min") or j.get("salary_max"))
        if _pay_transparency_violation(j.get("location",""), _has_sal):
            _trans_html = (
                "<span style='display:inline-block;background:#eff6ff;color:#1d4ed8;"
                "border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600;margin-left:6px'>"
                "⚖️ Salary disclosure required by law — ask</span>"
            )

        # ── Easy Apply warning ───────────────────────────────────────
        _easy_html = ""
        if "linkedin.com" in j.get("url","").lower():
            _easy_html = (
                "<span style='display:inline-block;background:#052010;color:#86efac;"
                "border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600;margin-left:6px'>"
                "🔗 LinkedIn</span>"
            )

        # ── Title alignment insight ──────────────────────────────────
        _title_gap_html = ""
        if profile:
            _gap_word = _title_gap(j.get("title",""), profile["raw_text"].lower())
            if _gap_word:
                _title_gap_html = (
                    f"<div style='margin-top:4px'>"
                    f"<span style='display:inline-block;background:#1e1b4b;color:#a5b4fc;"
                    f"border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600'>"
                    f"💡 Add '{_gap_word}' to your resume → 10x more callbacks</span></div>"
                )

        # Score context label
        _score_label = "Strong fit" if s >= 75 else "Moderate fit" if s >= 50 else "Weak fit"
        _score_sublabel = (
            f"{len(matched_all)} matched · {len(missing_all)} missing"
            if profile else "Upload resume for score"
        )
        # Escape all API-supplied fields before embedding in HTML
        _jt = xe(j['title']); _jco = xe(j['company'])
        _jloc = xe(j['location']); _jsrc = xe(j['source'])
        _jdate = xe(j.get('date', ''))
        _jdesc = xe(j['description'][:220])
        st.markdown(
            f"<div class='job-row'>"
            f"<div class='job-row-inner'>"
            f"<div class='job-row-body'>"
            f"<div class='job-title'>{_jt}</div>"
            f"<div class='job-meta'>"
            f"<b style='color:#cbd5e1'>{_jco}</b> · {flag} {_jloc}{salary} · "
            f"<span style='color:#64748b'>{_jsrc}</span>"
            f"{(' · ' + _timing_html) if _timing_html else ((' · <span style=\"color:#64748b\">' + _jdate + '</span>') if _jdate else '')}"
            f"{_trans_html}{_easy_html}</div>"
            f"<div style='margin-top:8px;flex-wrap:wrap'>{matched_c}{missing_c}</div>"
            f"<div class='job-desc'>{_jdesc}…</div>"
            f"{ghost_html}{sal_note_html}{_title_gap_html}{flags_html}"
            f"</div>"
            f"<div class='job-score-col'>"
            f"<div class='job-score-badge' style='background:{bg}'>{s}%</div>"
            f"<div style='font-size:10px;font-weight:700;color:{bg};text-transform:uppercase;"
            f"letter-spacing:.05em;margin-top:5px;text-align:center'>{_score_label}</div>"
            f"<div style='font-size:10px;color:#64748b;margin-top:2px;text-align:center;white-space:nowrap'>{_score_sublabel}</div>"
            f"</div>"
            f"</div></div>",
            unsafe_allow_html=True
        )
        # Why this score expander
        if profile and (matched_all or missing_all) and j.get("description","").strip():
            with st.expander("📊 Why this score?", expanded=False):
                _ws1, _ws2 = st.columns(2)
                with _ws1:
                    if matched_all:
                        st.markdown("<div style='font-size:11px;font-weight:700;color:#10b981;margin-bottom:4px'>✅ Keywords you have</div>", unsafe_allow_html=True)
                        st.markdown(" ".join(chip(k, "green") for k in matched_all[:8]), unsafe_allow_html=True)
                with _ws2:
                    if missing_all:
                        st.markdown("<div style='font-size:11px;font-weight:700;color:#ef4444;margin-bottom:4px'>❌ Keywords you're missing</div>", unsafe_allow_html=True)
                        st.markdown(" ".join(chip(k, "red") for k in missing_all[:6]), unsafe_allow_html=True)
                        if len(missing_all) <= 3:
                            st.caption(f"Only {len(missing_all)} gaps — add these to your resume/LinkedIn to reach 90%+")
        ca, cb, cc, cd = st.columns([1.3, 1.5, 2.2, 1.5])
        with ca:
            if tracker.is_saved(j["id"]): st.button("✅ Saved", key=f"sv_{j['id']}", disabled=True, use_container_width=True)
            else:
                if st.button("Save", key=f"sv_{j['id']}", use_container_width=True):
                    tracker.save_job(j, s, resume_version=st.session_state.get("active_resume_version"))
                    st.rerun()
        with cb:
            _jurl2 = str(j.get("url","")).strip()
            if _jurl2.startswith("https://") or _jurl2.startswith("http://"):
                st.link_button("Apply ↗", _jurl2, use_container_width=True)
        with cc:
            is_active_pkg = st.session_state.get("apply_pkg_id") == j["id"]
            btn_label = "Package ✓" if is_active_pkg else "Apply Package"
            if st.button(btn_label, key=f"cl_{j['id']}", use_container_width=True, type="primary" if is_active_pkg else "secondary"):
                if is_active_pkg:
                    for k in ["apply_pkg_id","apply_pkg_job","pkg_ats","pkg_ats_id","pkg_cl","pkg_ty","pkg_bullets"]:
                        st.session_state.pop(k, None)
                else:
                    st.session_state.apply_pkg_id  = j["id"]
                    st.session_state.apply_pkg_job = j
                    for k in ["pkg_ats","pkg_ats_id","pkg_cl","pkg_ty","pkg_bullets"]:
                        st.session_state.pop(k, None)
                st.rerun()
        with cd:
            if st.button("🏢 Research", key=f"rc_{j['id']}", use_container_width=True):
                st.session_state[f"show_co_{j['id']}"] = not st.session_state.get(f"show_co_{j['id']}", False)

        btn_row2 = st.columns([1.8, 2, 2, 1.5])
        with btn_row2[0]:
            if st.button("🎓 Interview Pack", key=f"ip_{j['id']}", use_container_width=True):
                st.session_state[f"ip_{j['id']}"] = not st.session_state.get(f"ip_{j['id']}", False)
        if profile and j.get("description", "").strip():
            with btn_row2[1]:
                if st.button("🎯 What are my real chances?", key=f"chances_{j['id']}", use_container_width=True):
                    from claude_ai import assess_fit_claude
                    with st.spinner("Claude is assessing your fit…"):
                        fit = assess_fit_claude(profile, j)
                    st.session_state[f"fit_{j['id']}"] = fit
        with btn_row2[2]:
            if st.button("🔗 Similar Jobs", key=f"sim_{j['id']}", use_container_width=True):
                st.session_state[f"show_sim_{j['id']}"] = not st.session_state.get(f"show_sim_{j['id']}", False)

        if st.session_state.get(f"show_sim_{j['id']}"):
            try:
                from vector_store import get_similar_jobs as _vs_sim
                _sims = _vs_sim(str(j["id"]), n_results=5)
                if _sims:
                    st.markdown("<div style='font-size:11px;font-weight:700;color:#64748b;margin:6px 0 4px;text-transform:uppercase'>Similar jobs from index</div>", unsafe_allow_html=True)
                    for _sim in _sims:
                        _sc2 = _sim.get("score", 0)
                        st.markdown(
                            f"<div style='padding:8px 12px;margin-bottom:4px;background:#1e293b;"
                            f"border-radius:8px;display:flex;justify-content:space-between;align-items:center'>"
                            f"<div><span style='font-size:12.5px;color:#e2e8f0;font-weight:600'>{xe(_sim.get('title',''))}</span>"
                            f" <span style='font-size:11px;color:#64748b'>@ {xe(_sim.get('company',''))}</span></div>"
                            f"<span style='font-size:11px;font-weight:700;color:{score_color(_sc2)}'>{_sc2}%</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                else:
                    st.caption("No similar jobs in index yet — run more searches to populate it.")
            except Exception:
                st.caption("Similar jobs unavailable — ChromaDB index may be empty.")

        fit_result = st.session_state.get(f"fit_{j['id']}")
        if fit_result:
            st.markdown(
                f"<div class='card-slate' style='margin-bottom:6px;border-left:4px solid #7c3aed'>"
                f"<div style='font-size:11px;font-weight:700;color:#7c3aed;margin-bottom:6px'>🎯 YOUR HONEST FIT — {j['title']} @ {j['company']}</div>"
                f"<div style='font-size:13px;color:#cbd5e1;line-height:1.6;white-space:pre-line'>{fit_result}</div>"
                f"</div>", unsafe_allow_html=True
            )

        if st.session_state.get(f"ip_{j['id']}"):
            ip = _interview_prep_pack(j, profile)
            st.markdown(
                f"<div style='background:#1a1040;border:1px solid #4c1d95;border-radius:10px;"
                f"padding:16px 18px;margin-bottom:8px'>"
                f"<div style='font-size:11px;font-weight:700;color:#a78bfa;text-transform:uppercase;"
                f"letter-spacing:.06em;margin-bottom:10px'>🎓 Interview Prep Pack — {j['title']} @ {j['company']}</div>"
                f"</div>", unsafe_allow_html=True
            )
            ip_q, ip_star, ip_ty = st.tabs(["Likely Questions", "STAR Framework", "Tell Me About Yourself"])
            with ip_q:
                st.caption(f"Based on competencies detected in JD: {', '.join(ip['detected'])}")
                for i, q in enumerate(ip["questions"], 1):
                    st.markdown(
                        f"<div style='padding:8px 12px;margin-bottom:6px;background:#1a1040;"
                        f"border:1px solid #4c1d95;border-left:3px solid #7c3aed;border-radius:6px;"
                        f"font-size:13px;color:#e2e8f0'>"
                        f"<span style='font-weight:700;color:#7c3aed;margin-right:8px'>{i}.</span>{q}</div>",
                        unsafe_allow_html=True
                    )
            with ip_star:
                st.caption("Use the STAR method for every behavioural question — interviewers score you on this.")
                for step in ip["star"]:
                    st.markdown(f"<div class='card-slate' style='margin-bottom:8px;font-size:13px'>{step}</div>", unsafe_allow_html=True)
                st.markdown(alert("💡 Prepare 3–5 STAR stories before any interview. Most questions are variations of the same 8 themes.", "blue"), unsafe_allow_html=True)
            with ip_ty:
                st.caption("Personalise the brackets below — this is your opening pitch.")
                st.text_area("Your opener (edit before using):", value=ip["tyab"], height=150, key=f"tyab_{j['id']}")

        if st.session_state.get(f"show_co_{j['id']}"):
            import urllib.parse as _ul
            from claude_ai import company_intel_claude
            co_name = j["company"]
            co_key  = f"co_data_{j['id']}"
            ci_key  = f"co_intel_{j['id']}"
            if co_key not in st.session_state:
                with st.spinner(f"Looking up {co_name}…"):
                    try:
                        enc = _ul.quote(co_name.replace(" ", "_"))
                        r2  = __import__("requests").get(
                            f"https://en.wikipedia.org/api/rest_v1/page/summary/{enc}",
                            timeout=5, headers={"User-Agent": "CareerIQ/1.0"}
                        )
                        if r2.status_code == 200 and r2.json().get("type") == "standard":
                            d2 = r2.json()
                            st.session_state[co_key] = {
                                "summary":     d2.get("extract","")[:480],
                                "description": d2.get("description",""),
                                "wiki_url":    d2.get("content_urls",{}).get("desktop",{}).get("page",""),
                            }
                        else:
                            st.session_state[co_key] = None
                    except Exception:
                        st.session_state[co_key] = None
                if j.get("description","").strip() and ci_key not in st.session_state:
                    with st.spinner("AI decoding the company culture…"):
                        st.session_state[ci_key] = company_intel_claude(
                            co_name, j["description"], j.get("title","")
                        )
            co_data = st.session_state.get(co_key)
            ci_data = st.session_state.get(ci_key)
            co_encoded = _ul.quote_plus(co_name)
            st.markdown(
                f"<div class='card-slate' style='margin-bottom:6px'>"
                f"<div style='font-weight:700;font-size:14px;margin-bottom:6px'>🏢 {co_name}</div>"
                + (f"<div style='font-size:12px;color:#475569;margin-bottom:8px'><i>{co_data['description']}</i></div>"
                   f"<div style='font-size:13px;color:#cbd5e1;line-height:1.55'>{co_data['summary']}</div>"
                   if co_data else
                   f"<div style='font-size:12px;color:#94a3b8'>No Wikipedia entry found for this company.</div>")
                + f"<div style='margin-top:10px;display:flex;gap:12px;font-size:12px'>"
                f"<a href='https://www.glassdoor.com/Search/results.htm?keyword={co_encoded}' target='_blank' style='color:#2563eb'>Glassdoor Reviews ↗</a>"
                f"<a href='https://www.linkedin.com/company/{co_encoded}' target='_blank' style='color:#2563eb'>LinkedIn ↗</a>"
                f"<a href='https://news.google.com/search?q={co_encoded}' target='_blank' style='color:#2563eb'>News ↗</a>"
                + (f"<a href='{co_data['wiki_url']}' target='_blank' style='color:#2563eb'>Wikipedia ↗</a>" if co_data and co_data.get("wiki_url") else "")
                + f"</div></div>", unsafe_allow_html=True
            )
            if ci_data and isinstance(ci_data, dict):
                ci1, ci2 = st.columns(2)
                with ci1:
                    if ci_data.get("culture_signals"):
                        st.markdown("**🧭 Culture signals**")
                        for s in ci_data["culture_signals"]:
                            st.markdown(f"<div style='font-size:12px;padding:4px 0;border-bottom:1px solid #1e293b;color:#cbd5e1'>• {s}</div>", unsafe_allow_html=True)
                    if ci_data.get("red_flags"):
                        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
                        st.markdown("**🚩 Watch out for**")
                        for rf in ci_data["red_flags"]:
                            st.markdown(f"<div style='font-size:12px;padding:4px 0;color:#dc2626'>• {rf}</div>", unsafe_allow_html=True)
                with ci2:
                    if ci_data.get("day_in_life"):
                        st.markdown("**📅 What a week looks like**")
                        for d in ci_data["day_in_life"]:
                            st.markdown(f"<div style='font-size:12px;padding:4px 0;border-bottom:1px solid #1e293b;color:#cbd5e1'>• {d}</div>", unsafe_allow_html=True)
                    if ci_data.get("likely_questions"):
                        st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
                        st.markdown("**❓ They'll likely ask**")
                        for q in ci_data["likely_questions"]:
                            st.markdown(f"<div style='font-size:12px;padding:4px 0;color:#2563eb'>• {q}</div>", unsafe_allow_html=True)
            elif not j.get("description","").strip():
                st.caption("Paste a job description to unlock AI company intelligence.")

        # ── Referral Radar ──────────────────────────────────────
        _all_contacts = tracker.get_contacts()
        _co_lower = j["company"].lower().strip()
        _matches  = [c for c in _all_contacts if c.get("company","").lower().strip() == _co_lower]
        if _matches:
            _names = ", ".join(c["name"] for c in _matches[:3])
            st.markdown(
                f"<div style='background:#052010;border:1px solid #14532d;border-radius:8px;"
                f"padding:8px 14px;margin-bottom:6px;font-size:13px;color:#bbf7d0'>"
                f"🤝 <b>Referral Radar:</b> You know someone at <b>{j['company']}</b> — {_names}"
                f"</div>", unsafe_allow_html=True
            )
            if st.button("Draft Referral Ask", key=f"ref_{j['id']}", use_container_width=False):
                st.session_state[f"ref_msg_{j['id']}"] = _draft_referral_ask(_matches[0], j, profile)
            if st.session_state.get(f"ref_msg_{j['id']}"):
                st.text_area(
                    "Edit and send to your contact",
                    value=st.session_state[f"ref_msg_{j['id']}"],
                    height=180,
                    key=f"ref_edit_{j['id']}",
                )

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Market Intelligence panel ─────────────────────────────────
    st.markdown("---")
    with st.expander("📊 Market Intelligence — BLS outlook, hiring signals & job market news", expanded=False):
        _mi_tab1, _mi_tab2, _mi_tab3 = st.tabs(["BLS Outlook", "Hiring Signals", "Market News"])

        with _mi_tab1:
            try:
                from job_market import BLS_PROJECTIONS
                _mc1, _mc2 = st.columns(2)
                with _mc1:
                    st.markdown("<div style='font-size:12px;font-weight:700;color:#10b981;margin-bottom:8px'>Fastest Growing Roles</div>", unsafe_allow_html=True)
                    for _role, _pct, _sec in BLS_PROJECTIONS["fastest_growing"][:8]:
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;padding:6px 0;"
                            f"border-bottom:1px solid #1e293b'>"
                            f"<div><div style='font-size:12.5px;color:#e2e8f0;font-weight:600'>{_role}</div>"
                            f"<div style='font-size:11px;color:#64748b'>{_sec}</div></div>"
                            f"<div style='font-size:13px;font-weight:900;color:#10b981;flex-shrink:0;margin-left:8px'>{_pct}</div>"
                            f"</div>", unsafe_allow_html=True
                        )
                with _mc2:
                    st.markdown("<div style='font-size:12px;font-weight:700;color:#ef4444;margin-bottom:8px'>Fastest Declining Roles</div>", unsafe_allow_html=True)
                    for _role, _pct, _sec in BLS_PROJECTIONS["fastest_declining"][:8]:
                        st.markdown(
                            f"<div style='display:flex;justify-content:space-between;padding:6px 0;"
                            f"border-bottom:1px solid #1e293b'>"
                            f"<div><div style='font-size:12.5px;color:#e2e8f0;font-weight:600'>{_role}</div>"
                            f"<div style='font-size:11px;color:#64748b'>{_sec}</div></div>"
                            f"<div style='font-size:13px;font-weight:900;color:#ef4444;flex-shrink:0;margin-left:8px'>{_pct}</div>"
                            f"</div>", unsafe_allow_html=True
                        )
            except Exception:
                st.caption("BLS data unavailable.")

        with _mi_tab2:
            if st.button("Load HackerNews + GitHub Signals", key="jobs_load_signals") or st.session_state.get("market_intel"):
                if not st.session_state.get("market_intel"):
                    with st.spinner("Fetching hiring signals (20-40 s)…"):
                        try:
                            from market_intel import get_market_intel
                            _intel = get_market_intel()
                            if any(_intel.values()):
                                st.session_state["market_intel"] = _intel
                        except Exception as e:
                            st.error(f"Failed: {e}")
                _intel = st.session_state.get("market_intel", {})
                _sig_c1, _sig_c2 = st.columns(2)
                with _sig_c1:
                    st.markdown("<div style='font-size:12px;font-weight:700;color:#f59e0b;margin-bottom:8px'>HackerNews — Most-wanted skills</div>", unsafe_allow_html=True)
                    for _term, _cnt in (_intel.get("hn_skills") or [])[:12]:
                        _bpct = min(100, int(_cnt / max((_intel["hn_skills"][0][1] if _intel.get("hn_skills") else 1), 1) * 100))
                        st.markdown(
                            f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px'>"
                            f"<div style='font-size:12px;color:#e2e8f0;width:120px;flex-shrink:0'>{_term}</div>"
                            f"<div style='flex:1;background:#1e293b;border-radius:4px;height:8px'>"
                            f"<div style='background:#f59e0b;width:{_bpct}%;height:8px;border-radius:4px'></div></div>"
                            f"<div style='font-size:11px;color:#64748b;width:30px;text-align:right'>{_cnt}</div>"
                            f"</div>", unsafe_allow_html=True
                        )
                with _sig_c2:
                    st.markdown("<div style='font-size:12px;font-weight:700;color:#3b82f6;margin-bottom:8px'>GitHub — Trending repos</div>", unsafe_allow_html=True)
                    for _repo in (_intel.get("gh_repos") or [])[:8]:
                        st.markdown(
                            f"<div style='padding:6px 0;border-bottom:1px solid #1e293b'>"
                            f"<div style='font-size:12.5px;color:#93c5fd;font-weight:600'>{_repo.get('name','')}</div>"
                            f"<div style='font-size:11px;color:#64748b'>{_repo.get('language','')} · ⭐ {_repo.get('stars','')}</div>"
                            f"</div>", unsafe_allow_html=True
                        )
            else:
                st.caption("Click above to load live hiring signals from HackerNews and GitHub.")

        with _mi_tab3:
            if st.button("Load Job Market News", key="jobs_load_news") or st.session_state.get("job_news"):
                if not st.session_state.get("job_news"):
                    with st.spinner("Fetching headlines…"):
                        try:
                            from job_market import get_job_news
                            _news = get_job_news()
                            if _news:
                                st.session_state["job_news"] = _news
                        except Exception as e:
                            st.error(f"News fetch failed: {e}")
                for _item in (st.session_state.get("job_news") or []):
                    if _item.get("title"):
                        st.markdown(
                            f"<div style='padding:8px 0;border-bottom:1px solid #1e293b'>"
                            f"<a href='{_item.get('link','')}' target='_blank' style='color:#93c5fd;font-weight:600;"
                            f"font-size:13px;text-decoration:none'>{_item['title']}</a>"
                            f"<div style='font-size:11px;color:#475569;margin-top:2px'>"
                            f"{_item.get('source','')} · {_item.get('date','')}</div>"
                            f"</div>", unsafe_allow_html=True
                        )
            else:
                st.caption("Click above to load the latest job market headlines.")

    # ── Apply Package panel ──────────────────────────────────────
    pkg_job = st.session_state.get("apply_pkg_job")
    if pkg_job:
        from ai_tools import generate_cover_letter, ats_scan as _ats_scan
        from writing_suite import generate as ws_generate

        st.markdown(
            f"<div class='pkg-banner'>"
            f"<div><div style='color:#fff;font-weight:900;font-size:1.1rem'>📦 Apply Package</div>"
            f"<div style='color:#93c5fd;font-size:13px'>{pkg_job['title']} @ {pkg_job['company']} · {pkg_job.get('location','')}</div></div>"
            f"<div style='color:#bfdbfe;font-size:12px'>Generate everything you need for this application below</div>"
            f"</div>", unsafe_allow_html=True
        )

        if not profile:
            st.markdown(alert("Load your resume on the Dashboard to generate personalized content.", "blue"), unsafe_allow_html=True)
        else:
            if "pkg_ats" not in st.session_state or st.session_state.get("pkg_ats_id") != pkg_job["id"]:
                if pkg_job.get("description","").strip():
                    with st.spinner("Running ATS scan…"):
                        st.session_state.pkg_ats    = _ats_scan(profile["raw_text"], pkg_job["description"])
                        st.session_state.pkg_ats_id = pkg_job["id"]
                else:
                    st.session_state.pkg_ats    = None
                    st.session_state.pkg_ats_id = pkg_job["id"]

            ats = st.session_state.get("pkg_ats")

            st.markdown("<div class='section-tag' style='margin-top:8px'>ATS Compatibility</div>", unsafe_allow_html=True)
            if ats:
                vc_color = {"strong":"#059669","medium":"#d97706","weak":"#dc2626"}[ats["verdict"][0]]
                a1, a2, a3, a4 = st.columns([1,1,1,3])
                a1.markdown(f"<div style='text-align:center'><div style='font-size:2.2rem;font-weight:900;color:{vc_color}'>{ats['score']}%</div><div style='font-size:11px;color:#94a3b8'>ATS Score</div></div>", unsafe_allow_html=True)
                a2.metric("Keyword", f"{ats['keyword_score']}%")
                a3.metric("Semantic", f"{ats['semantic_score']}%")
                with a4:
                    _mh = ats.get("missing_hard") or ats.get("missing_keywords", [])
                    _ms = ats.get("missing_soft", [])
                    if _mh:
                        st.markdown("<span style='font-size:12px;font-weight:600;color:#dc2626'>Hard skills missing: </span>" + " ".join(chip(k,"red") for k in _mh[:5]), unsafe_allow_html=True)
                    if _ms:
                        st.markdown("<span style='font-size:12px;font-weight:600;color:#d97706'>Soft skills to highlight: </span>" + " ".join(chip(k,"amber") for k in _ms[:4]), unsafe_allow_html=True)
                    st.markdown(alert(ats["verdict"][1], "green" if ats["verdict"][0]=="strong" else "amber" if ats["verdict"][0]=="medium" else "red"), unsafe_allow_html=True)
            else:
                st.markdown(alert("Paste the job description in the search results to get ATS score.", "amber"), unsafe_allow_html=True)

            st.markdown("---")
            bc, cc, tc = st.columns(3)

            with bc:
                st.markdown("<div class='section-tag'>Targeted Resume Bullets</div>", unsafe_allow_html=True)
                st.caption("Bullets that address your gaps for this specific role")
                if st.button("Generate Bullets", key="pkg_bullets_btn", use_container_width=True):
                    missing_kw = ats["missing_keywords"][:3] if ats and ats.get("missing_keywords") else ["data analysis","project management","stakeholder communication"]
                    st.session_state.pkg_bullets = _generate_targeted_bullets(profile, pkg_job, missing_kw)
                if st.session_state.get("pkg_bullets"):
                    st.text_area("Add to your resume", value=st.session_state.pkg_bullets, height=200, key="pkg_b_edit", label_visibility="collapsed")

            with cc:
                st.markdown("<div class='section-tag'>Cover Letter</div>", unsafe_allow_html=True)
                st.caption("Full cover letter tailored to this job")
                if st.button("Generate Cover Letter", key="pkg_cl_btn", use_container_width=True, type="primary"):
                    with st.spinner("Writing…"):
                        st.session_state.pkg_cl = generate_cover_letter(profile, pkg_job)
                if st.session_state.get("pkg_cl"):
                    cl_text = st.session_state.pkg_cl
                    cl_wc = len(cl_text.split())
                    cl_color = "#059669" if 250 <= cl_wc <= 350 else "#d97706" if cl_wc < 250 else "#dc2626"
                    st.markdown(
                        f"<div style='font-size:11px;font-weight:700;color:{cl_color};margin-bottom:3px'>"
                        f"{cl_wc} words {'✓ ideal range' if 250<=cl_wc<=350 else '— aim for 250–350 words'}</div>",
                        unsafe_allow_html=True
                    )
                    st.text_area("Edit before sending", value=cl_text, height=200, key="pkg_cl_edit", label_visibility="collapsed")

            with tc:
                st.markdown("<div class='section-tag'>Thank-You Email</div>", unsafe_allow_html=True)
                st.caption("Send within 24 hours of your interview")
                if st.button("Generate Thank-You Email", key="pkg_ty_btn", use_container_width=True):
                    with st.spinner("Writing…"):
                        _, ty = ws_generate("thank_you", profile, pkg_job, "")
                        st.session_state.pkg_ty = ty
                if st.session_state.get("pkg_ty"):
                    st.text_area("Edit before sending", value=st.session_state.pkg_ty, height=200, key="pkg_ty_edit", label_visibility="collapsed")

            st.markdown("---")
            pkg_dl_col, pkg_tip_col = st.columns([1, 3])
            with pkg_dl_col:
                from pdf_export import apply_package_pdf
                pkg_pdf = apply_package_pdf(
                    name=profile.get("name", "Candidate"),
                    job=pkg_job,
                    ats=ats,
                    cover_letter_text=st.session_state.get("pkg_cl", ""),
                    bullets_text=st.session_state.get("pkg_bullets", ""),
                    thankyou_text=st.session_state.get("pkg_ty", ""),
                )
                safe_co = re.sub(r"[^\w]", "_", pkg_job.get("company","Company"))[:20]
                st.download_button(
                    "⬇ Download Full Package PDF",
                    data=pkg_pdf,
                    file_name=f"CareerIQ_Package_{safe_co}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                )
            with pkg_tip_col:
                st.markdown(alert("💡 Generate the sections above, then download your full application package as one PDF.", "blue"), unsafe_allow_html=True)

