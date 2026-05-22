from datetime import date, timedelta
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, STATUS_EMOJI, STATUS_COLOR, score_color, xe
import tracker

inject_css()

st.markdown("<div class='page-title'>Track Applications</div><div class='page-sub'>Pipeline Kanban, follow-up schedule, and your network CRM — all in one place.</div>", unsafe_allow_html=True)

tab_pipeline, tab_followup, tab_crm = st.tabs(["Pipeline", "Follow-Ups", "Network CRM"])

# ── Pipeline ──────────────────────────────────────────────────────
with tab_pipeline:
    apps = tracker.get_all(st.session_state.get("active_user_id", 1))

    if not apps:
        st.markdown(
            "<div class='card' style='text-align:center;padding:40px'>"
            "<div style='font-size:2rem;margin-bottom:12px'>📋</div>"
            "<div style='font-weight:700;color:#f1f5f9;font-size:16px;margin-bottom:8px'>No applications yet</div>"
            "<div style='color:#64748b;font-size:13px'>Save jobs from the Find Jobs page or the Dashboard to start tracking your pipeline.</div>"
            "</div>", unsafe_allow_html=True
        )
    else:
        STATUSES = ["saved", "applied", "interview", "offer", "rejected"]

        # Funnel summary row
        counts = {s: sum(1 for a in apps if a["status"] == s) for s in STATUSES}
        cols_hdr = st.columns(len(STATUSES))
        for i, s in enumerate(STATUSES):
            color = STATUS_COLOR[s]
            emoji = STATUS_EMOJI[s]
            cols_hdr[i].markdown(
                f"<div class='card' style='text-align:center;padding:12px 8px'>"
                f"<div style='font-size:18px'>{emoji}</div>"
                f"<div style='font-size:22px;font-weight:900;color:{color};margin:4px 0'>{counts[s]}</div>"
                f"<div style='font-size:11px;color:#64748b;text-transform:uppercase;font-weight:700'>{s}</div>"
                f"</div>", unsafe_allow_html=True
            )

        st.markdown("---")

        # Filters
        fc1, fc2, fc3 = st.columns([2, 2, 1])
        filter_status = fc1.selectbox("Filter by status", ["All"] + STATUSES, key="pipeline_filter")
        search_query  = fc2.text_input("Search by company or title", placeholder="Goldman, analyst…", key="pipeline_search")
        sort_by       = fc3.selectbox("Sort", ["Newest", "Score", "Company"], key="pipeline_sort")

        filtered = apps
        if filter_status != "All":
            filtered = [a for a in filtered if a["status"] == filter_status]
        if search_query:
            q = search_query.lower()
            filtered = [a for a in filtered if q in (a.get("company","") or "").lower() or q in (a.get("title","") or "").lower()]
        if sort_by == "Score":
            filtered = sorted(filtered, key=lambda a: a.get("score", 0), reverse=True)
        elif sort_by == "Company":
            filtered = sorted(filtered, key=lambda a: (a.get("company","") or "").lower())

        st.markdown(f"<div style='font-size:12px;color:#64748b;margin-bottom:12px'>{len(filtered)} application{'s' if len(filtered)!=1 else ''}</div>", unsafe_allow_html=True)

        for app in filtered:
            sc         = app.get("score", 0)
            status     = app.get("status", "saved")
            sc_color   = score_color(sc)
            st_color   = STATUS_COLOR.get(status, "#64748b")
            st_emoji   = STATUS_EMOJI.get(status, "•")
            date_str   = app.get("date_saved", "")[:10] if app.get("date_saved") else ""
            applied_str= app.get("date_applied","")[:10] if app.get("date_applied") else ""
            salary_str = ""
            if app.get("salary_min") and app.get("salary_max"):
                salary_str = f" · ${int(app['salary_min']):,}–${int(app['salary_max']):,}"
            ver_str = f" · v: {app['resume_version']}" if app.get("resume_version") else ""

            with st.container():
                st.markdown(
                    f"<div class='job-row'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                    f"<div style='flex:1'>"
                    f"<div style='font-weight:700;font-size:15px;color:#f1f5f9'>{xe(app['title'])}</div>"
                    f"<div style='color:#64748b;font-size:12px;margin-top:2px'>"
                    f"<b style='color:#94a3b8'>{xe(app['company'])}</b> · {xe(app['location'] or '—')}{salary_str}</div>"
                    f"<div style='margin-top:4px;font-size:11px;color:#475569'>"
                    f"Saved {date_str}{(' · Applied '+applied_str) if applied_str else ''}{ver_str}</div>"
                    f"</div>"
                    f"<div style='display:flex;flex-direction:column;align-items:flex-end;gap:6px;flex-shrink:0;margin-left:14px'>"
                    f"<div style='background:{sc_color};color:#fff;border-radius:10px;padding:6px 10px;"
                    f"font-weight:900;font-size:16px;min-width:48px;text-align:center'>{sc}%</div>"
                    f"<div style='background:{st_color}22;color:{st_color};border:1px solid {st_color}44;"
                    f"border-radius:8px;padding:3px 10px;font-size:11px;font-weight:700'>{st_emoji} {status}</div>"
                    f"</div>"
                    f"</div></div>",
                    unsafe_allow_html=True
                )

                act_cols = st.columns([1.5, 2.5, 1.5, 1])
                with act_cols[0]:
                    new_status = st.selectbox(
                        "Status", STATUSES,
                        index=STATUSES.index(status),
                        key=f"status_{app['id']}",
                        label_visibility="collapsed"
                    )
                    if new_status != status:
                        tracker.update_status(app["id"], new_status)
                        st.rerun()

                with act_cols[1]:
                    notes_val = app.get("notes") or ""
                    new_notes = st.text_input("Notes", value=notes_val, key=f"notes_{app['id']}", placeholder="Notes…", label_visibility="collapsed")
                    if new_notes != notes_val:
                        tracker.update_status(app["id"], status, new_notes)

                with act_cols[2]:
                    _jurl = str(app.get("url","")).strip()
                    if _jurl.startswith("http"):
                        st.link_button("Open posting ↗", _jurl, use_container_width=True)

                with act_cols[3]:
                    if st.button("🗑", key=f"del_{app['id']}", help="Delete application"):
                        tracker.delete_app(app["id"])
                        st.rerun()

# ── Follow-Ups ────────────────────────────────────────────────────
with tab_followup:
    st.markdown("<div class='section-tag'>Follow-Ups Due Now</div>", unsafe_allow_html=True)
    user_id = st.session_state.get("active_user_id", 1)
    due = tracker.get_due_followups(user_id)

    if not due:
        st.markdown(alert("No follow-ups due — you're on top of it. Follow-ups auto-schedule 7 days after you mark a job 'Applied'.", "green"), unsafe_allow_html=True)
    else:
        for fu in due:
            try:
                days_overdue = (date.today() - date.fromisoformat(fu["due_date"][:10])).days
            except (ValueError, TypeError):
                days_overdue = 0
            urgency_color = "#ef4444" if days_overdue >= 3 else "#f59e0b"

            st.markdown(
                f"<div class='job-row'>"
                f"<div style='display:flex;justify-content:space-between;align-items:flex-start'>"
                f"<div><div style='font-weight:700;font-size:15px;color:#f1f5f9'>{xe(fu['title'])}</div>"
                f"<div style='color:#94a3b8;font-size:12px;margin-top:2px'>{xe(fu['company'])} · Applied {xe(fu.get('date_applied','')[:10] if fu.get('date_applied') else '—')}</div>"
                f"</div>"
                f"<div style='color:{urgency_color};font-size:12px;font-weight:700;flex-shrink:0;margin-left:12px'>"
                f"Due {xe(fu['due_date'])} · {days_overdue}d overdue</div>"
                f"</div></div>",
                unsafe_allow_html=True
            )

            # Draft follow-up text
            default_draft = fu.get("draft_text","") or (
                f"Hi [Hiring Manager],\n\nI wanted to follow up on my application for the {fu['title']} position at {fu['company']}. "
                f"I applied on {fu.get('date_applied','')[:10] if fu.get('date_applied') else '[date]'} and remain very interested in the opportunity.\n\n"
                f"Please let me know if you need any additional information. I'd love the chance to discuss how my background aligns with the role.\n\n"
                f"Thank you,\n[Your name]"
            )
            draft = st.text_area("Follow-up email draft", value=default_draft, height=160, key=f"fu_draft_{fu['followup_id']}")

            fu_c1, fu_c2 = st.columns([1, 1])
            with fu_c1:
                if st.button("✅ Mark Sent", key=f"fu_done_{fu['followup_id']}", use_container_width=True, type="primary"):
                    tracker.save_followup_draft(fu["followup_id"], draft)
                    tracker.complete_followup(fu["followup_id"])
                    st.rerun()
            with fu_c2:
                if st.button("⏭ Skip", key=f"fu_skip_{fu['followup_id']}", use_container_width=True):
                    tracker.skip_followup(fu["followup_id"])
                    st.rerun()

    # All scheduled follow-ups
    with st.expander("View full follow-up schedule"):
        all_fu = tracker.get_all_followups(user_id)
        if all_fu:
            for fu in all_fu:
                st_icon = "✅" if fu["status"] == "sent" else "⏭" if fu["status"] == "skipped" else "🕐"
                color   = "#10b981" if fu["status"] == "sent" else "#64748b" if fu["status"] == "skipped" else "#f59e0b"
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;padding:8px 0;"
                    f"border-bottom:1px solid #1e293b;font-size:13px'>"
                    f"<span style='color:#e2e8f0'>{st_icon} {xe(fu['title'])} @ {xe(fu['company'])}</span>"
                    f"<span style='color:{color}'>{xe(fu['due_date'])} · {xe(fu['status'])}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        else:
            st.caption("No follow-ups scheduled yet.")

# ── Network CRM ───────────────────────────────────────────────────
with tab_crm:
    st.markdown("<div class='section-tag'>Network CRM</div>", unsafe_allow_html=True)
    st.caption("Track contacts, referrals, and outreach. 70% of jobs are filled through network — most people track none of it.")

    CONTACT_STATUSES = ["warm", "hot", "cold", "reached out", "replied", "met", "referred"]

    with st.expander("➕ Add a contact", expanded=False):
        c1, c2, c3 = st.columns(3)
        crm_name    = c1.text_input("Name *", placeholder="Sarah Johnson", key="crm_name")
        crm_company = c2.text_input("Company", placeholder="Goldman Sachs", key="crm_company")
        crm_role    = c3.text_input("Their role", placeholder="VP of Finance", key="crm_role")
        c4, c5, c6 = st.columns(3)
        crm_how_met  = c4.text_input("How you met", placeholder="LinkedIn, career fair, class…", key="crm_how_met")
        crm_email    = c5.text_input("Email", placeholder="sarah@gs.com", key="crm_email")
        crm_linkedin = c6.text_input("LinkedIn URL", placeholder="linkedin.com/in/…", key="crm_linkedin")
        c7, c8 = st.columns(2)
        crm_status = c7.selectbox("Status", CONTACT_STATUSES, key="crm_status")
        crm_next   = c8.text_input("Next action", placeholder="Send follow-up, ask for intro to hiring team…", key="crm_next")
        crm_notes  = st.text_area("Notes", placeholder="What did you discuss? Any commitments?", height=80, key="crm_notes")

        if st.button("Save Contact", type="primary", key="crm_save"):
            if crm_name.strip():
                tracker.save_contact(
                    name=crm_name, company=crm_company, role=crm_role,
                    how_met=crm_how_met, email=crm_email, linkedin=crm_linkedin,
                    status=crm_status, next_action=crm_next, notes=crm_notes,
                )
                st.success(f"Saved: {crm_name}")
                st.rerun()
            else:
                st.error("Name is required.")

    contacts = tracker.get_contacts()

    if not contacts:
        st.markdown(alert("No contacts yet. Add people from LinkedIn, career fairs, alumni events, and informational interviews.", "blue"), unsafe_allow_html=True)
    else:
        STATUS_COLORS_CRM = {
            "hot": "#ef4444", "warm": "#10b981", "referred": "#8b5cf6",
            "replied": "#3b82f6", "reached out": "#f59e0b",
            "met": "#06b6d4", "cold": "#64748b",
        }

        # Filter
        crm_filter = st.selectbox("Filter by status", ["All"] + CONTACT_STATUSES, key="crm_filter", label_visibility="collapsed")
        shown = contacts if crm_filter == "All" else [c for c in contacts if c["status"] == crm_filter]

        st.markdown(f"<div style='font-size:12px;color:#64748b;margin-bottom:10px'>{len(shown)} contact{'s' if len(shown)!=1 else ''}</div>", unsafe_allow_html=True)

        for c in shown:
            st_col = STATUS_COLORS_CRM.get(c["status"], "#64748b")
            with st.expander(f"{xe(c['name'])} — {xe(c.get('company',''))} · {xe(c['status'])}"):
                ec1, ec2 = st.columns(2)
                new_status = ec1.selectbox("Status", CONTACT_STATUSES, index=CONTACT_STATUSES.index(c["status"]) if c["status"] in CONTACT_STATUSES else 0, key=f"crm_st_{c['id']}")
                new_next   = ec2.text_input("Next action", value=c.get("next_action","") or "", key=f"crm_next_{c['id']}")
                new_notes  = st.text_area("Notes", value=c.get("notes","") or "", height=80, key=f"crm_notes_{c['id']}")

                st.markdown(
                    f"<div style='font-size:12px;color:#64748b;margin-bottom:8px'>"
                    f"Role: {xe(c.get('role','—'))} · How met: {xe(c.get('how_met','—'))}"
                    + (f" · <a href='{xe(c['linkedin'])}' target='_blank' style='color:#3b82f6'>LinkedIn</a>" if c.get("linkedin") else "")
                    + (f" · <a href='mailto:{xe(c['email'])}' style='color:#3b82f6'>{xe(c['email'])}</a>" if c.get("email") else "")
                    + f"</div>",
                    unsafe_allow_html=True
                )

                btn1, btn2 = st.columns([2, 1])
                with btn1:
                    if st.button("Save changes", key=f"crm_upd_{c['id']}", use_container_width=True, type="primary"):
                        tracker.update_contact(c["id"], status=new_status, next_action=new_next, notes=new_notes)
                        st.success("Updated.")
                        st.rerun()
                with btn2:
                    if st.button("🗑 Delete", key=f"crm_del_{c['id']}", use_container_width=True):
                        tracker.delete_contact(c["id"])
                        st.rerun()
