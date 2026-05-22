"""
10_Stats.py — CareerIQ Analytics Dashboard
Internal stats page showing real platform usage and background scanner history.
"""
import streamlit as st
import analytics
import tracker
from utils import inject_css, xe

inject_css()

st.markdown("<div class='page-title'>Platform Stats</div><div class='page-sub'>Real usage — tracked automatically, no inflation.</div>", unsafe_allow_html=True)

tab_usage, tab_scanner, tab_pipeline, tab_ab, tab_eval = st.tabs([
    "Usage Stats", "Scanner History", "Pipeline Overview", "A/B Resume Tests", "AI Output Quality"
])

# ── Usage Stats ───────────────────────────────────────────────────
with tab_usage:
    stats = analytics.get_stats()

    if not any(stats.values()):
        st.info("No activity tracked yet — use the app and check back.")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Resumes Analyzed",    stats.get("resumes", 0))
        c2.metric("Job Searches",         stats.get("jobs_searched", 0))
        c3.metric("Cover Letters",        stats.get("cover_letters", 0))
        c4.metric("Applications Tracked", stats.get("applications", 0))
        c5.metric("Days Active",          stats.get("days_active", 0))

        st.divider()
        st.markdown("<div class='section-tag'>Recent Events</div>", unsafe_allow_html=True)
        events = analytics.get_recent_events(50)
        if events:
            import pandas as pd
            df = pd.DataFrame(events)[["event", "ts", "meta"]]
            df.columns = ["Event", "Timestamp", "Detail"]
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ChromaDB index stats
    st.divider()
    st.markdown("<div class='section-tag'>Vector Index (ChromaDB)</div>", unsafe_allow_html=True)
    try:
        from vector_store import store_stats
        vs = store_stats()
        vc1, vc2 = st.columns(2)
        vc1.metric("Jobs Indexed", vs.get("jobs_indexed", 0))
        vc2.metric("Resumes Indexed", vs.get("resumes_indexed", 0))
        st.caption("Jobs are indexed automatically after each search. Resumes are indexed on upload.")
    except Exception as e:
        st.caption(f"Vector store unavailable: {e}")


# ── Scanner History ────────────────────────────────────────────────
with tab_scanner:
    st.markdown("<div class='section-tag'>Background Scanner Run History</div>", unsafe_allow_html=True)
    user_id = st.session_state.get("active_user_id", 1)
    runs = tracker.get_scanner_runs(limit=50, user_id=user_id)

    if not runs:
        st.markdown(
            "<div class='card' style='text-align:center;padding:32px'>"
            "<div style='font-size:1.5rem;margin-bottom:8px'>🔍</div>"
            "<div style='font-weight:700;color:#f1f5f9;margin-bottom:6px'>No scanner runs yet</div>"
            "<div style='color:#64748b;font-size:13px'>The background scanner runs on the schedule you set in My Profile → Scanner Config. "
            "It will appear here after its first run.</div>"
            "</div>", unsafe_allow_html=True
        )
    else:
        # Summary metrics
        total_found   = sum(r.get("jobs_found", 0) for r in runs)
        total_saved   = sum(r.get("jobs_saved", 0) for r in runs)
        total_notified= sum(r.get("jobs_notified", 0) for r in runs)
        avg_duration  = sum(r.get("duration_secs", 0) for r in runs) / len(runs)

        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total Runs",      len(runs))
        sc2.metric("Jobs Found",      total_found)
        sc3.metric("Jobs Auto-Saved", total_saved)
        sc4.metric("Push Alerts Sent",total_notified)

        st.divider()

        # Chart — jobs found per run
        try:
            import pandas as pd
            df = pd.DataFrame(runs)
            df["run_at"] = pd.to_datetime(df["run_at"])
            df = df.sort_values("run_at")
            df = df.rename(columns={"run_at": "Run Date", "jobs_found": "Jobs Found",
                                     "jobs_saved": "Auto-Saved", "jobs_notified": "Alerts Sent"})
            st.markdown("<div class='section-tag'>Jobs Found per Run</div>", unsafe_allow_html=True)
            st.bar_chart(df.set_index("Run Date")[["Jobs Found", "Auto-Saved"]], height=220)
        except Exception:
            pass

        # Run table
        st.markdown("<div class='section-tag' style='margin-top:16px'>Run Log</div>", unsafe_allow_html=True)
        for r in runs[:20]:
            run_at   = (r.get("run_at") or "")[:16].replace("T", " ")
            found    = r.get("jobs_found", 0)
            saved    = r.get("jobs_saved", 0)
            notified = r.get("jobs_notified", 0)
            dur      = r.get("duration_secs", 0)
            roles    = xe(r.get("roles_scanned") or "—")
            cities   = xe(r.get("cities_scanned") or "—")
            st.markdown(
                f"<div class='card-slate' style='padding:10px 16px;margin-bottom:6px;font-size:12.5px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span style='color:#e2e8f0;font-weight:600'>{run_at}</span>"
                f"<span style='color:#64748b'>{dur:.0f}s</span>"
                f"</div>"
                f"<div style='color:#64748b;margin-top:4px'>"
                f"<b style='color:#3b82f6'>{found}</b> found · "
                f"<b style='color:#10b981'>{saved}</b> saved · "
                f"<b style='color:#f59e0b'>{notified}</b> notified"
                f"</div>"
                f"<div style='color:#475569;margin-top:2px;font-size:11px'>"
                f"Roles: {roles} · Cities: {cities}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )


# ── Pipeline Overview ─────────────────────────────────────────────
with tab_pipeline:
    st.markdown("<div class='section-tag'>Application Pipeline</div>", unsafe_allow_html=True)
    apps = tracker.get_all(user_id)

    if not apps:
        st.markdown("<div style='color:#64748b;font-size:13px'>No applications tracked yet.</div>", unsafe_allow_html=True)
    else:
        from collections import Counter
        import datetime as _dt

        statuses = ["saved", "applied", "interview", "offer", "rejected"]
        counts   = Counter(a["status"] for a in apps)

        # Funnel chart
        try:
            import pandas as pd
            df_funnel = pd.DataFrame({
                "Stage": [s.title() for s in statuses],
                "Count": [counts.get(s, 0) for s in statuses],
            })
            st.bar_chart(df_funnel.set_index("Stage"), height=200)
        except Exception:
            pass

        # Response rate
        applied_count  = sum(counts.get(s, 0) for s in ["applied", "interview", "offer", "rejected"])
        response_count = sum(counts.get(s, 0) for s in ["interview", "offer", "rejected"])
        if applied_count > 0:
            rate = round(response_count / applied_count * 100)
            r1, r2, r3 = st.columns(3)
            r1.metric("Total Applications", len(apps))
            r2.metric("Response Rate",      f"{rate}%")
            r3.metric("Interviews",         counts.get("interview", 0))

        # Score distribution
        scores = [a.get("score", 0) for a in apps if a.get("score")]
        if scores:
            avg_score = round(sum(scores) / len(scores))
            st.markdown(f"<div style='margin-top:12px;font-size:13px;color:#64748b'>Average fit score across saved applications: <b style='color:#3b82f6'>{avg_score}%</b></div>", unsafe_allow_html=True)

        # Resume version A/B stats (legacy tracker-based)
        vstats = tracker.get_version_stats()
        if vstats:
            st.divider()
            st.markdown("<div class='section-tag'>Resume Version A/B Performance</div>", unsafe_allow_html=True)
            for vname, vs in vstats.items():
                cols = st.columns([2, 1, 1, 1, 1])
                cols[0].markdown(f"<div style='font-size:13px;font-weight:600;color:#f1f5f9;padding-top:4px'>{xe(vname)}</div>", unsafe_allow_html=True)
                cols[1].metric("Applied",    vs.get("applied", 0))
                cols[2].metric("Interviews", vs.get("interview", 0))
                cols[3].metric("Offers",     vs.get("offer", 0))
                cols[4].metric("Response %", f"{vs.get('response_rate', 0)}%")


# ── A/B Resume Testing ────────────────────────────────────────────
with tab_ab:
    st.markdown("<div class='section-tag'>Resume A/B Testing</div>", unsafe_allow_html=True)
    st.caption(
        "Track multiple resume versions against real outcomes. "
        "Apply with Version A to 10 jobs and Version B to 10 more — "
        "then see which gets more responses."
    )

    try:
        from ab_testing import compute_stats, version_comparison, save_version, log_application, update_application_status, get_applications

        comparison = version_comparison()
        ab_stats   = comparison["stats"]

        if not ab_stats:
            st.markdown(alert("No resume versions tracked yet. Add a version below to start.", "blue"), unsafe_allow_html=True)
        else:
            if comparison.get("insight"):
                st.markdown(
                    f"<div class='card-slate' style='padding:14px 18px;border-left:3px solid #10b981;margin-bottom:16px'>"
                    f"<div style='font-size:13.5px;color:#e2e8f0'>{xe(comparison['insight'])}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # Version comparison table
            _header_cols = st.columns([3, 1, 1, 1, 1, 1, 1])
            _header_cols[0].markdown("<div style='font-size:11px;font-weight:700;color:#64748b'>VERSION</div>", unsafe_allow_html=True)
            for _lbl, _ci in [("APPS", 1), ("RESPONSES", 2), ("INTERVIEWS", 3), ("OFFERS", 4), ("RESP %", 5), ("AVG DAYS", 6)]:
                _header_cols[_ci].markdown(f"<div style='font-size:11px;font-weight:700;color:#64748b'>{_lbl}</div>", unsafe_allow_html=True)

            best_id = comparison.get("best_response", {}).get("id")
            for vs_row in ab_stats:
                is_best = vs_row["id"] == best_id and vs_row.get("apps", 0) >= 3
                row_bg  = "border-left:3px solid #10b981" if is_best else "border-left:3px solid #1e293b"
                cols = st.columns([3, 1, 1, 1, 1, 1, 1])
                cols[0].markdown(
                    f"<div style='font-size:13px;font-weight:600;color:#f1f5f9;padding-top:4px'>"
                    f"{'🏆 ' if is_best else ''}{xe(vs_row['name'])}"
                    f"<span style='font-size:11px;color:#64748b;margin-left:6px'>{xe(vs_row.get('label',''))}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                cols[1].metric("", vs_row.get("apps", 0))
                cols[2].metric("", vs_row.get("responses", 0))
                cols[3].metric("", vs_row.get("interviews", 0))
                cols[4].metric("", vs_row.get("offers", 0))
                rr = vs_row.get("response_rate", 0)
                rr_color = "#10b981" if rr >= 20 else "#f59e0b" if rr >= 10 else "#ef4444"
                cols[5].markdown(f"<div style='font-size:18px;font-weight:900;color:{rr_color};padding-top:4px'>{rr}%</div>", unsafe_allow_html=True)
                cols[6].markdown(f"<div style='font-size:14px;color:#64748b;padding-top:6px'>{vs_row.get('avg_days') or '—'}</div>", unsafe_allow_html=True)
                st.markdown("<div style='border-bottom:1px solid #1e293b;margin:4px 0'></div>", unsafe_allow_html=True)

        st.markdown("---")

        # Add new version
        with st.expander("➕ Track a new resume version"):
            ab_vname  = st.text_input("Version name", placeholder="e.g. Version A — Skills focus", key="ab_vname")
            ab_vlabel = st.text_input("Short label (optional)", placeholder="e.g. No objective", key="ab_vlabel")
            ab_vtext  = st.text_area("Paste resume text (for comparison)", height=120, key="ab_vtext")
            if st.button("Save Version", key="ab_save_ver") and ab_vname:
                from ab_testing import save_version as _sv
                _sv(ab_vname, ab_vtext, ab_vlabel)
                st.success(f"Version '{ab_vname}' saved.")
                st.rerun()

        # Log an application against a version
        with st.expander("📝 Log an application"):
            if ab_stats:
                ver_opts = {f"{s['name']} (ID {s['id']})": s["id"] for s in ab_stats}
                chosen_ver = st.selectbox("Resume version used", list(ver_opts.keys()), key="ab_log_ver")
                ab_title   = st.text_input("Job title", key="ab_log_title")
                ab_company = st.text_input("Company", key="ab_log_co")
                if st.button("Log Application", key="ab_log_btn") and ab_title and ab_company:
                    log_application(ver_opts[chosen_ver], ab_title, ab_company)
                    st.success("Logged.")
                    st.rerun()
            else:
                st.caption("Add a resume version first.")

    except Exception as e:
        st.error(f"A/B testing unavailable: {e}")


# ── AI Output Quality (Eval) ──────────────────────────────────────
with tab_eval:
    st.markdown("<div class='section-tag'>AI Output Quality Dashboard</div>", unsafe_allow_html=True)
    st.caption(
        "Every AI-generated output (cover letters, LinkedIn About sections, interview answers) "
        "is automatically evaluated across 5 dimensions. This is the quality feedback loop."
    )

    try:
        from eval_engine import get_eval_summary, get_eval_history

        summary = get_eval_summary()
        history = get_eval_history(limit=50)

        if summary.get("total", 0) == 0:
            st.markdown(alert("No evaluations yet — generate a cover letter, LinkedIn About, or interview coaching to populate this dashboard.", "blue"), unsafe_allow_html=True)
        else:
            # Summary metrics
            ev1, ev2, ev3, ev4 = st.columns(4)
            ev1.metric("Outputs Evaluated", summary["total"])
            ev2.metric("Avg Quality Score", f"{summary.get('avg_overall', 0)}%")
            ev3.metric("Avg Grounding",     f"{summary.get('avg_grounding', 0)}%")
            ev4.metric("Avg Specificity",   f"{summary.get('avg_specificity', 0)}%")

            # By output type
            by_type = summary.get("by_type", {})
            if by_type:
                st.markdown("<div class='section-tag' style='margin-top:16px'>Quality by Output Type</div>", unsafe_allow_html=True)
                type_cols = st.columns(len(by_type))
                _type_labels = {
                    "cover_letter":    "Cover Letters",
                    "linkedin_about":  "LinkedIn About",
                    "interview_answer":"Interview Answers",
                    "cold_dm":         "Cold DMs",
                    "other":           "Other",
                }
                for i, (t, avg) in enumerate(by_type.items()):
                    grade_color = "#10b981" if avg >= 75 else "#f59e0b" if avg >= 55 else "#ef4444"
                    type_cols[i].markdown(
                        f"<div style='text-align:center;padding:14px;background:#0f172a;"
                        f"border:1px solid #1e293b;border-radius:8px'>"
                        f"<div style='font-size:22px;font-weight:900;color:{grade_color}'>{avg:.0f}%</div>"
                        f"<div style='font-size:11px;color:#64748b;margin-top:4px'>"
                        f"{xe(_type_labels.get(t, t))}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

            # Recent evaluations
            if history:
                st.markdown("<div class='section-tag' style='margin-top:16px'>Recent Evaluations</div>", unsafe_allow_html=True)
                for ev in history[:15]:
                    grade = "A" if ev["overall"] >= 85 else "B" if ev["overall"] >= 70 else "C" if ev["overall"] >= 55 else "D" if ev["overall"] >= 40 else "F"
                    grade_c = {"A":"#10b981","B":"#3b82f6","C":"#f59e0b","D":"#f97316","F":"#ef4444"}.get(grade,"#64748b")
                    ts = (ev.get("created_at") or "")[:16].replace("T"," ")
                    flags = ev.get("flags") or []
                    flags_str = " · ".join(flags[:2]) if flags else "No issues detected"
                    st.markdown(
                        f"<div class='card-slate' style='padding:10px 16px;margin-bottom:6px'>"
                        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                        f"<div>"
                        f"<span style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>"
                        f"{xe(_type_labels.get(ev.get('output_type','other'), ev.get('output_type','')))}</span>"
                        f"<span style='font-size:11px;color:#475569;margin-left:8px'>{xe(ts)}</span>"
                        f"</div>"
                        f"<span style='font-size:16px;font-weight:900;color:{grade_c}'>Grade {grade} · {ev['overall']}%</span>"
                        f"</div>"
                        f"<div style='font-size:11px;color:#475569;margin-top:4px'>"
                        f"Relevance: {ev.get('relevance',0)}% · Grounding: {ev.get('grounding',0)}% · "
                        f"Specificity: {ev.get('specificity',0)}% · Tone: {ev.get('tone',0)}%"
                        f"</div>"
                        f"{'<div style=\"font-size:11px;color:#fca5a5;margin-top:3px\">⚠ ' + xe(flags_str) + '</div>' if flags else ''}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    except Exception as e:
        st.error(f"Eval dashboard unavailable: {e}")
