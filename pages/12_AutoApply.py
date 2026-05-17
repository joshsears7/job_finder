import time
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, xe

inject_css()

st.markdown(
    "<div class='page-title'>Auto Apply</div>"
    "<div class='page-sub'>Agentic LinkedIn Easy Apply — finds matching jobs, scores them against your resume, "
    "writes tailored cover letters, and applies with your approval at every step.</div>",
    unsafe_allow_html=True,
)

profile = st.session_state.get("resume")
if not profile:
    st.markdown(alert("Upload your resume on the Dashboard first.", "blue"), unsafe_allow_html=True)
    st.stop()

# ── Requirements check ────────────────────────────────────────────
import os

# Auto Apply requires a local desktop environment — not available on cloud deployments
_IS_CLOUD = bool(os.getenv("SPACE_ID") or os.getenv("RAILWAY_ENVIRONMENT"))
if _IS_CLOUD:
    st.markdown(
        alert(
            "<b>Auto Apply is a desktop-only feature.</b> It requires a local browser (Playwright + Chromium) "
            "and your LinkedIn credentials stored locally in <code>.env</code>. "
            "Clone the repo and run locally to use this feature.",
            "blue"
        ),
        unsafe_allow_html=True,
    )
    st.stop()

_has_pw = False
try:
    import playwright
    _has_pw = True
except ImportError:
    pass

_has_creds = bool(os.getenv("LINKEDIN_EMAIL") and os.getenv("LINKEDIN_PASSWORD"))

if not _has_pw:
    st.markdown(
        alert(
            "<b>Playwright not installed.</b> Run in your terminal:<br>"
            "<code>pip install playwright && python -m playwright install chromium</code>",
            "amber"
        ),
        unsafe_allow_html=True,
    )
    st.stop()

if not _has_creds:
    st.markdown(
        alert(
            "<b>LinkedIn credentials not set.</b> Add to your <code>.env</code> file:<br>"
            "<code>LINKEDIN_EMAIL=your@email.com</code><br>"
            "<code>LINKEDIN_PASSWORD=yourpassword</code><br>"
            "Credentials are only used locally by Playwright and are never transmitted.",
            "amber"
        ),
        unsafe_allow_html=True,
    )
    st.stop()

st.markdown(
    "<div style='background:#0f172a;border:1px solid #f59e0b40;border-radius:10px;"
    "padding:14px 18px;margin-bottom:20px'>"
    "<div style='font-size:12px;font-weight:700;color:#f59e0b;margin-bottom:6px'>⚠ USE RESPONSIBLY</div>"
    "<div style='font-size:12.5px;color:#94a3b8;line-height:1.6'>"
    "Every application requires your explicit approval. "
    "A minimum 30-second delay is enforced between submissions. "
    "Session cap defaults to 20 applications. "
    "Apply only to roles you genuinely want — bulk-applying to irrelevant roles harms your LinkedIn reputation."
    "</div></div>",
    unsafe_allow_html=True,
)

# ── Configuration ─────────────────────────────────────────────────
st.markdown("<div class='section-tag'>Search Settings</div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)
role     = c1.text_input("Job title / keywords", placeholder="e.g. Business Analyst Intern", key="aa_role")
location = c2.text_input("Location", placeholder="e.g. New York, NY or Remote", key="aa_location")

c3, c4, c5 = st.columns(3)
exp_map = {
    "Any":        "",
    "Internship": "1",
    "Entry Level":"2",
    "Associate":  "3",
}
exp_choice  = c3.selectbox("Experience level", list(exp_map.keys()), key="aa_exp")
max_apps    = c4.number_input("Max applications this session", min_value=1, max_value=20, value=10, key="aa_max")
dry_run_on  = c5.checkbox("Dry run (don't actually submit)", value=True, key="aa_dry")

if dry_run_on:
    st.markdown(
        "<div style='font-size:12px;color:#10b981;padding:6px 0'>"
        "✅ Dry run mode — application forms will be filled but not submitted. "
        "Uncheck to go live.</div>",
        unsafe_allow_html=True,
    )

# ── Profile supplement ─────────────────────────────────────────────
with st.expander("Profile details for form autofill", expanded=False):
    st.caption("These fill in form fields automatically. LinkedIn profile data is auto-populated where available.")
    pf_c1, pf_c2 = st.columns(2)
    aa_phone    = pf_c1.text_input("Phone", key="aa_phone", placeholder="+1 555-555-5555")
    aa_location = pf_c2.text_input("Your city", key="aa_city", placeholder="Charlotte, NC")
    aa_linkedin = pf_c1.text_input("LinkedIn URL", key="aa_li_url", placeholder="linkedin.com/in/yourprofile")
    aa_website  = pf_c2.text_input("Portfolio / website", key="aa_website", placeholder="yoursite.com")

supplemented_profile = {
    **profile,
    "phone":        aa_phone,
    "location":     aa_location or profile.get("location", ""),
    "linkedin_url": aa_linkedin,
    "website":      aa_website,
    "email":        os.getenv("LINKEDIN_EMAIL", ""),
}

# ── Launch ─────────────────────────────────────────────────────────
st.markdown("---")
if not role.strip():
    st.info("Enter a job title to start.")
    st.stop()

if st.button("Start Auto Apply Session", type="primary", use_container_width=True, key="aa_start",
             disabled=not _has_creds):

    st.markdown("<div class='section-tag'>Session Progress</div>", unsafe_allow_html=True)
    status_box  = st.empty()
    results_box = st.container()

    applied_log = []

    def _status(msg):
        status_box.caption(msg)

    def _confirm(job, score, cover_letter):
        """Streamlit-compatible human confirmation via session state."""
        job_key = f"aa_confirm_{job['job_id']}"
        skip_key = f"aa_skip_{job['job_id']}"

        with results_box:
            score_color = "#10b981" if score >= 70 else "#f59e0b" if score >= 45 else "#ef4444"
            st.markdown(
                f"<div class='card-slate' style='padding:16px 20px;margin-bottom:12px'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'>"
                f"<div>"
                f"<div style='font-weight:700;font-size:14px;color:#e2e8f0'>{xe(job['title'])}</div>"
                f"<div style='font-size:12px;color:#64748b'>{xe(job['company'])} · {xe(job['location'])}</div>"
                f"</div>"
                f"<div style='font-size:22px;font-weight:900;color:{score_color}'>{score}%</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            with st.expander("Cover letter preview"):
                st.text(cover_letter[:600] + ("…" if len(cover_letter) > 600 else ""))

            col_apply, col_skip = st.columns(2)
            do_apply = col_apply.button("Apply", key=job_key, type="primary")
            do_skip  = col_skip.button("Skip", key=skip_key)

        if do_apply:
            return True
        if do_skip:
            return False
        # Default skip if neither button pressed yet
        return False

    try:
        from linkedin_applier import run_apply_session

        resume_text = profile.get("raw_text", "")
        exp_val     = exp_map[exp_choice]

        for outcome in run_apply_session(
            role=role,
            location=location,
            profile=supplemented_profile,
            resume_text=resume_text,
            confirm_callback=_confirm,
            status_callback=_status,
            max_per_session=int(max_apps),
            dry_run=dry_run_on,
            experience_filter=exp_val,
        ):
            applied_log.append(outcome)

    except Exception as e:
        st.error(f"Session error: {e}")

    # ── Summary ────────────────────────────────────────────────────
    if applied_log:
        st.markdown("---")
        st.markdown("<div class='section-tag'>Session Summary</div>", unsafe_allow_html=True)
        applied  = [r for r in applied_log if r["status"] == "applied"]
        skipped  = [r for r in applied_log if r["status"] == "skipped"]
        failed   = [r for r in applied_log if r["status"] == "failed"]

        m1, m2, m3 = st.columns(3)
        m1.metric("Applied", len(applied))
        m2.metric("Skipped", len(skipped))
        m3.metric("Failed",  len(failed))

        if applied:
            st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
            for r in applied:
                st.markdown(
                    f"<div style='padding:8px 0;border-bottom:1px solid #1e293b'>"
                    f"<span style='color:#10b981;font-weight:700'>✓</span> "
                    f"<span style='font-size:13px;color:#e2e8f0'>"
                    f"{xe(r['job']['title'])} @ {xe(r['job']['company'])}</span>"
                    f"<span style='font-size:11px;color:#64748b;margin-left:8px'>"
                    f"Score: {r['score']}%</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# ── How it works ───────────────────────────────────────────────────
with st.expander("How Auto Apply works"):
    st.markdown("""
**Step-by-step:**

1. Logs into LinkedIn in a visible browser window (you can watch it)
2. Searches Easy Apply jobs matching your role + location + filters
3. Scores each job against your resume using semantic AI matching
4. For every job above 30% match, generates a tailored cover letter with Claude Sonnet
5. **Shows you each application and asks for approval** — you click Apply or Skip
6. Fills the Easy Apply form: contact info, cover letter, and any simple questions
7. Waits 30+ seconds between submissions to avoid rate detection
8. Stops at your session cap

**Tips:**
- Start with dry run mode to see which jobs it finds and what the letters look like
- The browser opens visually so you always know what's happening
- Add your phone, location, and LinkedIn URL in the profile section for better autofill
- A 60-70%+ match score is a good threshold to apply to
""")
