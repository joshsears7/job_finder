import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, xe
import profile_store as ps

inject_css()

st.markdown("<div class='page-title'>My Profile</div><div class='page-sub'>Your personal info, job search preferences, and background scanner settings.</div>", unsafe_allow_html=True)

user_id = st.session_state.get("active_user_id", 1)
profile = ps.get_profile(user_id)

tab_info, tab_search, tab_scanner, tab_alerts = st.tabs(["Personal Info", "Job Search", "Scanner Config", "Job Alerts"])

# ── Personal Info ─────────────────────────────────────────────────
with tab_info:
    st.markdown("<div class='section-tag'>Personal Information</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    name     = c1.text_input("Full name",       value=profile.get("name",""),              key="prof_name")
    email    = c2.text_input("Email",            value=profile.get("email",""),             key="prof_email")
    phone    = c1.text_input("Phone",            value=profile.get("phone",""),             key="prof_phone")
    location = c2.text_input("Current location",value=profile.get("current_location",""),  key="prof_location")

    st.markdown("<div class='section-tag' style='margin-top:16px'>Online Presence</div>", unsafe_allow_html=True)
    c3, c4 = st.columns(2)
    linkedin  = c3.text_input("LinkedIn URL",   value=profile.get("linkedin_url",""),      key="prof_linkedin")
    github    = c4.text_input("GitHub URL",     value=profile.get("github_url",""),        key="prof_github")
    portfolio = c3.text_input("Portfolio URL",  value=profile.get("portfolio_url",""),     key="prof_portfolio")

    st.markdown("<div class='section-tag' style='margin-top:16px'>Education & Background</div>", unsafe_allow_html=True)
    c5, c6 = st.columns(2)
    school   = c5.text_input("School",          value=profile.get("school",""),            key="prof_school")
    degree   = c6.text_input("Degree",          value=profile.get("degree",""),            key="prof_degree")
    majors   = c5.text_input("Major(s)",         value=profile.get("majors",""),            key="prof_majors")
    grad     = c6.text_input("Graduation date", value=profile.get("graduation_date",""),   key="prof_grad")
    work_auth= c5.text_input("Work authorization", value=profile.get("work_auth",""),      key="prof_auth")
    yrs_exp  = c6.number_input("Years of experience", min_value=0, max_value=50,
                                value=int(profile.get("years_experience",0) or 0),         key="prof_yrs")

    if st.button("Save Personal Info", type="primary", key="save_info"):
        profile.update({
            "name": name, "email": email, "phone": phone,
            "current_location": location, "linkedin_url": linkedin,
            "github_url": github, "portfolio_url": portfolio,
            "school": school, "degree": degree, "majors": majors,
            "graduation_date": grad, "work_auth": work_auth,
            "years_experience": yrs_exp,
        })
        ps.save_profile(profile, user_id)
        st.success("Personal info saved.")

# ── Job Search Preferences ────────────────────────────────────────
with tab_search:
    st.markdown("<div class='section-tag'>Job Type & Salary</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    job_type       = c1.selectbox("Job type", ["internship","full-time","both"],
                                   index=["internship","full-time","both"].index(profile.get("job_type","internship"))
                                   if profile.get("job_type") in ["internship","full-time","both"] else 0,
                                   key="prof_job_type")
    salary_type    = c2.selectbox("Salary type", ["hourly","annual"],
                                   index=["hourly","annual"].index(profile.get("salary_type","hourly"))
                                   if profile.get("salary_type") in ["hourly","annual"] else 0,
                                   key="prof_sal_type")
    open_remote    = c3.checkbox("Open to remote", value=bool(profile.get("open_to_remote", True)), key="prof_remote")
    c4, c5, c6 = st.columns(3)
    min_sal        = c4.number_input("Min salary", min_value=0, max_value=500000,
                                      value=int(profile.get("min_salary",0) or 0), key="prof_min_sal")
    max_sal        = c5.number_input("Max salary", min_value=0, max_value=500000,
                                      value=int(profile.get("max_salary",0) or 0), key="prof_max_sal")
    open_relocate  = c6.checkbox("Open to relocate", value=bool(profile.get("open_to_relocate", True)), key="prof_relocate")

    st.markdown("<div class='section-tag' style='margin-top:16px'>Target Roles</div>", unsafe_allow_html=True)
    st.caption("These feed the auto-detection on the dashboard and the background scanner.")
    roles_text = st.text_area(
        "Target roles (one per line)",
        value="\n".join(profile.get("target_roles", [])),
        height=140, key="prof_roles"
    )

    st.markdown("<div class='section-tag' style='margin-top:16px'>Target Cities</div>", unsafe_allow_html=True)
    cities_text = st.text_area(
        "Cities to search (one per line)",
        value="\n".join(profile.get("target_cities", [])),
        height=140, key="prof_cities"
    )

    st.markdown("<div class='section-tag' style='margin-top:16px'>Target Companies</div>", unsafe_allow_html=True)
    c7, c8 = st.columns(2)
    targets_text   = c7.text_area("Companies I want to work at (one per line)",
                                   value="\n".join(profile.get("target_companies", [])),
                                   height=120, key="prof_targets")
    blacklist_text = c8.text_area("Companies to skip (one per line)",
                                   value="\n".join(profile.get("blacklist_companies", [])),
                                   height=120, key="prof_blacklist")

    if st.button("Save Job Search Preferences", type="primary", key="save_search"):
        profile.update({
            "job_type": job_type,
            "salary_type": salary_type,
            "open_to_remote": open_remote,
            "open_to_relocate": open_relocate,
            "min_salary": min_sal,
            "max_salary": max_sal,
            "target_roles":       [r.strip() for r in roles_text.splitlines() if r.strip()],
            "target_cities":      [c.strip() for c in cities_text.splitlines() if c.strip()],
            "target_companies":   [c.strip() for c in targets_text.splitlines() if c.strip()],
            "blacklist_companies":[c.strip() for c in blacklist_text.splitlines() if c.strip()],
        })
        ps.save_profile(profile, user_id)
        st.success("Job search preferences saved.")

# ── Scanner Config ────────────────────────────────────────────────
with tab_scanner:
    st.markdown("<div class='section-tag'>Background Scanner Settings</div>", unsafe_allow_html=True)
    st.caption("The background scanner runs on a schedule to find new high-fit jobs and notify you. Configure thresholds here.")

    c1, c2 = st.columns(2)
    auto_save_threshold = c1.slider(
        "Auto-save threshold (fit score %)",
        min_value=0, max_value=100,
        value=int(profile.get("auto_save_threshold", 60) or 60),
        key="prof_auto_save",
        help="Jobs scoring at or above this threshold are automatically saved to your pipeline."
    )
    fresh_threshold = c2.slider(
        "Push notification threshold (fit score %)",
        min_value=0, max_value=100,
        value=int(profile.get("fresh_threshold", 72) or 72),
        key="prof_fresh",
        help="Jobs scoring at or above this threshold trigger an immediate macOS notification."
    )
    scan_interval = c1.selectbox(
        "Scan interval",
        [1, 2, 4, 6, 12, 24],
        index=[1,2,4,6,12,24].index(int(profile.get("scan_interval_hours",4) or 4))
        if int(profile.get("scan_interval_hours",4) or 4) in [1,2,4,6,12,24] else 2,
        key="prof_scan_interval",
        format_func=lambda x: f"Every {x} hour{'s' if x>1 else ''}",
    )
    notify_on_fresh = c2.checkbox(
        "Enable push notifications (ntfy)",
        value=bool(profile.get("notify_on_fresh", True)),
        key="prof_notify"
    )

    st.markdown(
        "<div class='card-slate' style='margin-top:12px;padding:14px 18px'>"
        "<div style='font-size:12px;color:#64748b;line-height:1.7'>"
        f"Scanner will: auto-save jobs scoring ≥ <b style='color:#3b82f6'>{auto_save_threshold}%</b> · "
        f"push-notify on jobs scoring ≥ <b style='color:#10b981'>{fresh_threshold}%</b> · "
        f"run <b style='color:#e2e8f0'>every {scan_interval} hour{'s' if scan_interval>1 else ''}</b>"
        "</div></div>",
        unsafe_allow_html=True
    )

    if st.button("Save Scanner Settings", type="primary", key="save_scanner"):
        profile.update({
            "auto_save_threshold": auto_save_threshold,
            "fresh_threshold": fresh_threshold,
            "scan_interval_hours": scan_interval,
            "notify_on_fresh": notify_on_fresh,
        })
        ps.save_profile(profile, user_id)
        st.success("Scanner settings saved.")

    st.markdown("---")
    st.markdown("<div class='section-tag'>Account</div>", unsafe_allow_html=True)
    if st.button("Sign Out", key="sign_out"):
        for k in ["auth_user_id", "auth_user_name", "active_user_id",
                  "resume", "resume_analysis", "resume_score",
                  "dashboard_jobs", "dashboard_search_role"]:
            st.session_state.pop(k, None)
        st.rerun()

# ── Job Alerts ─────────────────────────────────────────────────────
with tab_alerts:
    from job_alerts import load_config as _al_load, save_config as _al_save, add_alert, remove_alert, set_ntfy_topic, test_ntfy, set_alert_email, test_email
    from job_fetcher import CITY_PRESETS

    st.markdown("<div class='section-tag'>Push Notifications (ntfy)</div>", unsafe_allow_html=True)
    st.caption("ntfy is a free, open-source push notification service. No account needed — just pick a topic name.")

    al_cfg = _al_load()
    c_ntfy1, c_ntfy2 = st.columns([3, 1])
    ntfy_topic = c_ntfy1.text_input(
        "ntfy topic (e.g. careeriq-joshuasears-jobs)",
        value=al_cfg.get("ntfy_topic", ""),
        placeholder="careeriq-yourname-jobs",
        key="al_ntfy_topic",
    )
    if c_ntfy2.button("Test Notification", key="al_ntfy_test", use_container_width=True):
        if ntfy_topic.strip():
            set_ntfy_topic(ntfy_topic.strip())
            ok = test_ntfy(ntfy_topic.strip())
            if ok:
                st.success(f"Test sent! Open ntfy.sh/{ntfy_topic.strip()} or the ntfy app to confirm.")
            else:
                st.error("Failed to send — check your topic name and internet connection.")
        else:
            st.error("Enter an ntfy topic first.")

    if ntfy_topic.strip() != al_cfg.get("ntfy_topic", ""):
        if st.button("Save ntfy Topic", key="al_save_topic"):
            set_ntfy_topic(ntfy_topic.strip())
            st.success("Topic saved.")

    st.markdown(
        "<div class='card-slate' style='margin:12px 0;padding:12px 16px;font-size:12.5px;color:#64748b'>"
        "Install the free <b style='color:#e2e8f0'>ntfy app</b> on iOS/Android, subscribe to your topic, "
        "and you'll get a push notification whenever a new high-fit job is found. "
        "No account, no login — just pick a unique topic name."
        "</div>", unsafe_allow_html=True
    )

    st.markdown("<div class='section-tag' style='margin-top:16px'>Email Alerts</div>", unsafe_allow_html=True)
    st.caption("Get an email when a high-match job is found. Requires a free SendGrid API key (sendgrid.com) set as SENDGRID_API_KEY in your environment.")

    import os as _os
    _has_sg = bool(_os.getenv("SENDGRID_API_KEY", ""))
    c_email1, c_email2 = st.columns([3, 1])
    _alert_email = c_email1.text_input(
        "Email to notify",
        value=al_cfg.get("alert_email", ""),
        placeholder="you@email.com",
        key="al_email_input",
        disabled=not _has_sg,
    )
    if not _has_sg:
        st.caption("Add SENDGRID_API_KEY to your secrets to enable email alerts.")
    if _has_sg and c_email2.button("Test Email", key="al_email_test", use_container_width=True):
        if _alert_email.strip():
            set_alert_email(_alert_email.strip())
            ok = test_email(_alert_email.strip())
            st.success("Test email sent — check your inbox.") if ok else st.error("Send failed — verify your SENDGRID_API_KEY and email address.")
        else:
            st.error("Enter an email address first.")
    if _has_sg and _alert_email.strip() != al_cfg.get("alert_email", ""):
        if st.button("Save Email", key="al_save_email"):
            set_alert_email(_alert_email.strip())
            st.success("Email saved.")

    st.markdown("---")
    st.markdown("<div class='section-tag'>Alert Configurations</div>", unsafe_allow_html=True)
    st.caption("Each alert defines a role + cities to watch. You'll be notified when new matching jobs appear above your fit threshold.")

    alerts = al_cfg.get("alerts", [])

    with st.expander("➕ Add a new alert", expanded=not bool(alerts)):
        al_role = st.text_input("Role to watch", placeholder="e.g. Business Analyst, Data Analyst Intern", key="al_new_role")
        city_keys = [k for k in CITY_PRESETS]
        al_cities = st.multiselect("Cities to watch", city_keys, key="al_new_cities")
        al_min    = st.slider("Min fit score to notify", 40, 95, 65, key="al_new_min")
        if st.button("Add Alert", type="primary", key="al_add_btn"):
            if al_role.strip() and al_cities:
                add_alert(al_role.strip(), al_cities, al_min)
                st.success(f"Alert added: '{al_role.strip()}' in {len(al_cities)} cities (score ≥ {al_min}%)")
                st.rerun()
            else:
                st.error("Enter a role and select at least one city.")

    if not alerts:
        st.markdown(
            "<div class='card-slate' style='padding:20px;text-align:center;color:#64748b;font-size:13px'>"
            "No alerts configured yet. Add one above to start getting notified of new matching jobs."
            "</div>", unsafe_allow_html=True
        )
    else:
        for a in alerts:
            role_str  = a.get("role", "")
            cities    = a.get("cities", [])
            min_score = a.get("min_score", 60)
            al1, al2 = st.columns([5, 1])
            with al1:
                st.markdown(
                    f"<div class='card-slate' style='padding:12px 16px'>"
                    f"<div style='font-weight:700;font-size:13px;color:#e2e8f0'>{xe(role_str)}</div>"
                    f"<div style='font-size:12px;color:#64748b;margin-top:4px'>"
                    f"{len(cities)} cit{'y' if len(cities)==1 else 'ies'}: {xe(', '.join(cities[:3]))}"
                    f"{'…' if len(cities)>3 else ''} · "
                    f"notify at ≥ <b style='color:#3b82f6'>{min_score}%</b> fit</div>"
                    f"</div>", unsafe_allow_html=True
                )
            with al2:
                if st.button("🗑 Remove", key=f"al_del_{role_str[:20]}", use_container_width=True):
                    remove_alert(role_str, cities)
                    st.rerun()

    last_run = al_cfg.get("last_run")
    seen_count = len(al_cfg.get("seen_ids", []))
    if last_run:
        st.markdown(
            f"<div style='font-size:12px;color:#475569;margin-top:16px'>"
            f"Last alert check: {last_run[:16].replace('T',' ')} · {seen_count:,} job IDs tracked (dedup)</div>",
            unsafe_allow_html=True
        )
