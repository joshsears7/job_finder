import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, xe

inject_css()

st.markdown(
    "<div class='page-title'>Company Research</div>"
    "<div class='page-sub'>Agentic intelligence: news, funding, tech stack, hiring velocity, "
    "culture signals, and a tailored talking-points brief — all synthesized by Claude Sonnet.</div>",
    unsafe_allow_html=True,
)

profile = st.session_state.get("resume")

# ── Input ─────────────────────────────────────────────────────────
st.markdown("<div class='section-tag'>Company Details</div>", unsafe_allow_html=True)

prefill = st.session_state.pop("research_company_prefill", None)

c1, c2, c3 = st.columns([2, 2, 2])
company_name = c1.text_input(
    "Company name", value=prefill.get("company", "") if prefill else "",
    placeholder="e.g. Stripe", key="cr_company"
)
role_name = c2.text_input(
    "Role you're applying for", value=prefill.get("role", "") if prefill else "",
    placeholder="e.g. Business Analyst", key="cr_role"
)
website = c3.text_input(
    "Company website (optional — improves tech stack detection)",
    placeholder="e.g. stripe.com", key="cr_website"
)

go = st.button(
    "Research This Company", type="primary", use_container_width=True,
    key="cr_go", disabled=not company_name.strip()
)

# ── Research ──────────────────────────────────────────────────────
if go and company_name.strip():
    progress_bar = st.progress(0)
    status_msg   = st.empty()

    def _progress(msg, pct):
        progress_bar.progress(pct / 100)
        status_msg.caption(msg)

    try:
        from company_research import research_company
        resume_text = (profile.get("raw_text", "") if profile else "")
        dossier = research_company(
            company=company_name.strip(),
            role=role_name.strip(),
            company_website=website.strip(),
            resume_text=resume_text,
            progress_callback=_progress,
        )
        st.session_state["cr_dossier"] = dossier
    except Exception as e:
        st.error(f"Research failed: {e}")
        st.stop()
    finally:
        progress_bar.empty()
        status_msg.empty()

# ── Dossier display ───────────────────────────────────────────────
dossier = st.session_state.get("cr_dossier")
if not dossier:
    st.markdown(
        alert(
            "Enter a company name and click <b>Research This Company</b>. "
            "The agent pulls news, funding, tech stack, and HackerNews signals, "
            "then Claude Sonnet synthesizes everything into a tailored brief.", "blue"
        ),
        unsafe_allow_html=True,
    )
    st.stop()

d_company = xe(dossier.get("company", ""))
d_role    = xe(dossier.get("role", ""))
d_fetched = xe(dossier.get("fetched_at", ""))
stage     = dossier.get("company_stage", "unknown")

_stage_color = {
    "early-stage startup": "#f59e0b",
    "growth-stage":        "#3b82f6",
    "public company":      "#10b981",
    "enterprise":          "#7c3aed",
}.get(stage, "#64748b")

st.markdown(
    f"<div style='background:#0f172a;border:1px solid #1e293b;border-radius:12px;"
    f"padding:20px 24px;margin-bottom:20px'>"
    f"<div style='display:flex;justify-content:space-between;align-items:center'>"
    f"<div>"
    f"<div style='font-size:22px;font-weight:900;color:#f1f5f9'>{d_company}</div>"
    f"<div style='font-size:13px;color:#64748b;margin-top:2px'>{d_role} · {d_fetched}</div>"
    f"</div>"
    f"<div style='font-size:11px;font-weight:700;color:{_stage_color};"
    f"background:{_stage_color}18;padding:6px 14px;border-radius:20px;text-transform:uppercase;"
    f"letter-spacing:0.5px'>{xe(stage)}</div>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Summary ───────────────────────────────────────────────────────
if dossier.get("summary"):
    st.markdown("<div class='section-tag'>Company Overview</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='card-slate' style='padding:16px 20px;line-height:1.7;color:#cbd5e1;font-size:14px'>"
        f"{xe(dossier['summary'])}</div>",
        unsafe_allow_html=True,
    )

# ── Key metrics row ────────────────────────────────────────────────
raw = dossier.get("raw", {})
cb  = raw.get("cb", {})
hiring = raw.get("hiring", {})
news_count = len(raw.get("news", []))
hn_count   = len(raw.get("hn", []))

m1, m2, m3, m4 = st.columns(4)
_metric_style = "background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:14px 16px;text-align:center"

m1.markdown(
    f"<div style='{_metric_style}'>"
    f"<div style='font-size:22px;font-weight:900;color:#3b82f6'>{news_count}</div>"
    f"<div style='font-size:11px;color:#64748b;margin-top:2px'>News Articles</div>"
    f"</div>", unsafe_allow_html=True
)
m2.markdown(
    f"<div style='{_metric_style}'>"
    f"<div style='font-size:22px;font-weight:900;color:#f59e0b'>{hn_count}</div>"
    f"<div style='font-size:11px;color:#64748b;margin-top:2px'>HN Mentions</div>"
    f"</div>", unsafe_allow_html=True
)
m3.markdown(
    f"<div style='{_metric_style}'>"
    f"<div style='font-size:20px;font-weight:900;color:#10b981'>{cb.get('funding','—')}</div>"
    f"<div style='font-size:11px;color:#64748b;margin-top:2px'>Total Funding</div>"
    f"</div>", unsafe_allow_html=True
)
m4.markdown(
    f"<div style='{_metric_style}'>"
    f"<div style='font-size:22px;font-weight:900;color:#7c3aed'>{hiring.get('open_roles', '—')}</div>"
    f"<div style='font-size:11px;color:#64748b;margin-top:2px'>Open Roles</div>"
    f"</div>", unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

# ── Main tabs ─────────────────────────────────────────────────────
tab_brief, tab_intel, tab_news, tab_tech = st.tabs([
    "Interview Brief", "Culture & Fit", "News & HN", "Tech Stack"
])

# ── Interview Brief ────────────────────────────────────────────────
with tab_brief:
    talking = dossier.get("talking_points", [])
    if talking:
        st.markdown("<div class='section-tag'>Talking Points to Reference</div>", unsafe_allow_html=True)
        st.caption("Mention these in your cover letter and interviews to show you've done your homework.")
        for pt in talking:
            st.markdown(
                f"<div class='card-slate' style='padding:12px 16px;margin-bottom:8px;"
                f"border-left:3px solid #3b82f6'>"
                f"<div style='font-size:13.5px;color:#e2e8f0'>• {xe(pt)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    qs = dossier.get("likely_interview_qs", [])
    if qs:
        st.markdown("<div class='section-tag' style='margin-top:20px'>Likely Interview Questions</div>", unsafe_allow_html=True)
        st.caption("Predicted from news, hiring signals, and company signals — not generic.")
        for q in qs:
            st.markdown(
                f"<div class='card-slate' style='padding:12px 16px;margin-bottom:8px'>"
                f"<div style='font-size:13px;color:#cbd5e1;font-weight:600'>Q: {xe(q)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    rec_angle = dossier.get("recruiter_angle", "")
    if rec_angle:
        st.markdown("<div class='section-tag' style='margin-top:20px'>Recruiter Outreach Angle</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='card-slate' style='padding:14px 18px;border-left:3px solid #10b981'>"
            f"<div style='font-size:13.5px;color:#e2e8f0'>{xe(rec_angle)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Culture & Fit ─────────────────────────────────────────────────
with tab_intel:
    culture = dossier.get("culture_read", "")
    if culture:
        st.markdown("<div class='section-tag'>Culture Read</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='card-slate' style='padding:16px 20px;line-height:1.7;color:#cbd5e1;font-size:13.5px'>"
            f"{xe(culture)}</div>",
            unsafe_allow_html=True,
        )

    why = dossier.get("why_apply", [])
    if why:
        st.markdown("<div class='section-tag' style='margin-top:18px'>Why You Fit Here</div>", unsafe_allow_html=True)
        for item in why:
            st.markdown(
                f"<div style='padding:8px 0;border-bottom:1px solid #1e293b'>"
                f"<span style='color:#10b981;font-weight:700;margin-right:8px'>✓</span>"
                f"<span style='font-size:13px;color:#cbd5e1'>{xe(item)}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    red_flags = dossier.get("red_flags", [])
    if red_flags:
        st.markdown("<div class='section-tag' style='margin-top:18px'>Red Flags to Consider</div>", unsafe_allow_html=True)
        for flag in red_flags:
            st.markdown(
                f"<div class='card-slate' style='padding:12px 16px;margin-bottom:8px;"
                f"border-left:3px solid #ef4444'>"
                f"<div style='font-size:13px;color:#fca5a5'>⚠ {xe(flag)}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div style='font-size:13px;color:#10b981;padding:12px 0'>✅ No significant red flags detected from available signals.</div>",
            unsafe_allow_html=True,
        )

# ── News & HN ─────────────────────────────────────────────────────
with tab_news:
    news = raw.get("news", [])
    hn   = raw.get("hn", [])

    if news:
        st.markdown("<div class='section-tag'>Recent News</div>", unsafe_allow_html=True)
        for a in news:
            url = str(a.get("url", "")).strip()
            title = xe(a.get("title", ""))
            link_html = (
                f"<a href='{url}' target='_blank' style='color:#93c5fd;font-weight:600;"
                f"font-size:13.5px;text-decoration:none'>{title}</a>"
                if url.startswith("http") else
                f"<span style='color:#e2e8f0;font-weight:600;font-size:13.5px'>{title}</span>"
            )
            st.markdown(
                f"<div class='card-slate' style='padding:12px 16px;margin-bottom:6px'>"
                f"{link_html}"
                f"<div style='font-size:11px;color:#475569;margin-top:4px'>"
                f"{xe(a.get('source',''))} · {xe(a.get('date',''))}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No recent news found.")

    if hn:
        st.markdown("<div class='section-tag' style='margin-top:18px'>HackerNews Mentions</div>", unsafe_allow_html=True)
        for item in hn:
            url = str(item.get("url", "")).strip()
            title = xe(item.get("title", ""))
            link_html = (
                f"<a href='{url}' target='_blank' style='color:#f59e0b;font-weight:600;"
                f"font-size:13px;text-decoration:none'>{title}</a>"
                if url.startswith("http") else
                f"<span style='color:#e2e8f0;font-size:13px'>{title}</span>"
            )
            st.markdown(
                f"<div class='card-slate' style='padding:10px 16px;margin-bottom:6px'>"
                f"{link_html}"
                f"<div style='font-size:11px;color:#475569;margin-top:3px'>"
                f"⬆ {item.get('points', 0)} pts · {xe(item.get('date',''))}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── Tech Stack ────────────────────────────────────────────────────
with tab_tech:
    tech = raw.get("tech", [])
    hiring_roles = hiring.get("sample_roles", [])

    if tech:
        st.markdown("<div class='section-tag'>Detected Tech Stack</div>", unsafe_allow_html=True)
        st.caption(f"Signals detected from {xe(website or company_name)}'s public website.")
        st.markdown(
            " ".join(chip(t, "blue") for t in tech),
            unsafe_allow_html=True,
        )
    else:
        st.caption("No tech signals detected — provide the company website URL for tech stack analysis.")

    if hiring_roles:
        st.markdown("<div class='section-tag' style='margin-top:18px'>Current Open Roles</div>", unsafe_allow_html=True)
        st.caption(f"{hiring.get('open_roles', 0)} active postings detected via Jobicy.")
        for r_title in hiring_roles:
            st.markdown(
                f"<div style='padding:6px 0;border-bottom:1px solid #1e293b;"
                f"font-size:13px;color:#cbd5e1'>• {xe(r_title)}</div>",
                unsafe_allow_html=True,
            )
