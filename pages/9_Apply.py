import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, xe
from ai_tools import generate_cover_letter, ats_scan, generate_interview_questions
from claude_ai import stream_cover_letter_claude, stream_thankyou_claude
import tracker
import analytics as _analytics

inject_css()

st.markdown("<div class='page-title'>Apply Engine</div><div class='page-sub'>One-click Apply Package: ATS scan · cover letter · targeted bullets · thank-you email — all tailored to the specific job.</div>", unsafe_allow_html=True)

profile = st.session_state.get("resume")
if not profile:
    st.markdown(alert("Upload your resume on the Dashboard first — the Apply Package is fully tailored to your profile.", "blue"), unsafe_allow_html=True)
    st.stop()

# ── Job Selector ──────────────────────────────────────────────────
st.markdown("<div class='section-tag'>Select a Job</div>", unsafe_allow_html=True)

all_saved  = tracker.get_all(st.session_state.get("active_user_id", 1))
search_jobs = st.session_state.get("jobs", [])
prefill    = st.session_state.pop("apply_pkg_job", None)

# Build combined job list: saved apps + current search results
job_options = []
for a in all_saved:
    job_options.append({
        "id": f"saved_{a['id']}", "title": a["title"], "company": a["company"],
        "location": a["location"], "url": a.get("url",""), "description": "",
        "source": a.get("source",""), "_label": f"[Saved] {a['title']} @ {a['company']}",
    })
for j in search_jobs:
    job_options.append({**j, "_label": f"[Search] {j['title']} @ {j['company']}"})

if prefill:
    job_options.insert(0, {**prefill, "_label": f"[Selected] {prefill['title']} @ {prefill['company']}"})

sel_idx = 0
if st.session_state.get("apply_pkg_id"):
    for i, j in enumerate(job_options):
        if j["id"] == st.session_state["apply_pkg_id"]:
            sel_idx = i
            break

if job_options:
    labels = [j["_label"] for j in job_options]
    chosen_idx = st.selectbox("Choose job", range(len(labels)), format_func=lambda i: labels[i],
                               index=sel_idx, key="apply_job_sel", label_visibility="collapsed")
    selected_job = dict(job_options[chosen_idx])
    selected_job.pop("_label", None)
    # Clear stale package state when user switches to a different job
    if st.session_state.get("apply_pkg_id") != selected_job["id"]:
        for _k in ("pkg_ats", "pkg_cl", "pkg_qs", "pkg_ty", "pkg_bullets", "pkg_job"):
            st.session_state.pop(_k, None)
    st.session_state["apply_pkg_id"] = selected_job["id"]
else:
    selected_job = None

# Always allow manual entry / JD paste
with st.expander("⚙️ Manual override / paste job description", expanded=not bool(job_options)):
    c1, c2 = st.columns(2)
    manual_title   = c1.text_input("Job title",   value=selected_job["title"]   if selected_job else "", key="apply_manual_title")
    manual_company = c2.text_input("Company",     value=selected_job["company"] if selected_job else "", key="apply_manual_company")
    manual_jd      = st.text_area("Paste job description", value=selected_job.get("description","") if selected_job else "", height=140, key="apply_jd_paste")

if selected_job:
    selected_job["title"]       = manual_title   or selected_job["title"]
    selected_job["company"]     = manual_company or selected_job["company"]
    selected_job["description"] = manual_jd      or selected_job.get("description","")
else:
    selected_job = {"id": "manual", "title": manual_title, "company": manual_company,
                    "description": manual_jd, "location": "", "url": "", "source": "manual"}

# ── Generate Button ───────────────────────────────────────────────
st.markdown("---")
if st.button("Generate Full Apply Package", type="primary", use_container_width=True, key="gen_pkg"):
    if not selected_job["title"]:
        st.error("Select a job or enter a job title first.")
    else:
        with st.spinner("Building your Apply Package — loading AI on first run (30–60 s)…"):
            try:
                ats    = ats_scan(profile["raw_text"], selected_job["description"])
                cl     = generate_cover_letter(profile, selected_job)
                qs     = generate_interview_questions(profile, selected_job)
                bullets= []
                for kw in ats.get("missing_hard", [])[:5]:
                    tmpl = next((b["suggested_bullet"] for b in ats.get("suggested_bullets",[]) if b["keyword"]==kw), None)
                    if tmpl:
                        bullets.append((kw, tmpl))

                st.session_state["pkg_ats"]     = ats
                st.session_state["pkg_cl"]      = cl
                st.session_state["pkg_qs"]      = qs
                st.session_state["pkg_ty"]      = ""
                st.session_state["pkg_bullets"] = bullets
                st.session_state["pkg_job"]     = selected_job
                st.session_state.pop("pkg_ty_interviewer", None)
                _analytics.track("cover_letter_generated", meta=selected_job.get("title",""))
            except Exception as e:
                st.error(f"Package generation failed: {e}")

# ── Package Display ───────────────────────────────────────────────
pkg_ats     = st.session_state.get("pkg_ats")
pkg_cl      = st.session_state.get("pkg_cl","")
pkg_qs      = st.session_state.get("pkg_qs",[])
pkg_ty      = st.session_state.get("pkg_ty","")
pkg_bullets = st.session_state.get("pkg_bullets",[])
pkg_job     = st.session_state.get("pkg_job", selected_job)

if pkg_ats:
    st.markdown("---")
    job_title   = xe(pkg_job.get("title",""))
    job_company = xe(pkg_job.get("company",""))
    st.markdown(
        f"<div class='pkg-banner'>"
        f"<div><div style='font-weight:800;font-size:17px;color:#fff'>Apply Package Ready</div>"
        f"<div style='font-size:13px;color:#93c5fd;margin-top:2px'>{job_title} @ {job_company}</div></div>"
        f"<div style='font-size:13px;font-weight:700;color:#60a5fa;background:#1e3a5f;padding:6px 12px;border-radius:6px'>READY</div>"
        f"</div>", unsafe_allow_html=True
    )

    # ── ATS Score ─────────────────────────────────────────────────
    with st.expander(f"ATS Scan — Score: {pkg_ats['score']}%", expanded=True):
        verdict_color = {"strong": "#10b981", "medium": "#f59e0b", "weak": "#ef4444"}.get(pkg_ats["verdict"][0], "#64748b")
        st.markdown(
            f"<div style='display:flex;gap:24px;align-items:center;margin-bottom:16px'>"
            f"<div style='font-size:42px;font-weight:900;color:{verdict_color}'>{pkg_ats['score']}%</div>"
            f"<div><div style='font-weight:700;color:{verdict_color}'>{pkg_ats['verdict'][1]}</div>"
            f"<div style='font-size:12px;color:#64748b;margin-top:4px'>"
            f"Keyword: {pkg_ats['keyword_score']}% · Semantic: {pkg_ats['semantic_score']}%</div></div>"
            f"</div>", unsafe_allow_html=True
        )

        col_found, col_miss = st.columns(2)
        with col_found:
            st.markdown("<div style='font-size:12px;font-weight:700;color:#10b981;margin-bottom:6px'>✅ Keywords Found</div>", unsafe_allow_html=True)
            if pkg_ats["found_keywords"]:
                st.markdown(" ".join(chip(k, "green") for k in pkg_ats["found_keywords"][:16]), unsafe_allow_html=True)
            else:
                st.caption("None detected.")
        with col_miss:
            st.markdown("<div style='font-size:12px;font-weight:700;color:#ef4444;margin-bottom:6px'>❌ Missing Keywords</div>", unsafe_allow_html=True)
            if pkg_ats["missing_hard"]:
                st.markdown(" ".join(chip(k,"red") for k in pkg_ats["missing_hard"][:12]), unsafe_allow_html=True)
            if pkg_ats.get("missing_soft"):
                st.markdown(" ".join(chip(k,"amber") for k in pkg_ats["missing_soft"][:6]), unsafe_allow_html=True)

        if pkg_ats.get("cliches"):
            st.markdown(alert(f"⚠ Clichés detected: {', '.join(pkg_ats['cliches'][:4])} — remove these from your resume.", "amber"), unsafe_allow_html=True)

        with st.expander("ATS Formatting Tips"):
            for tip in pkg_ats["formatting_tips"]:
                st.markdown(f"<div style='font-size:12.5px;color:#64748b;margin-bottom:5px'>• {xe(tip)}</div>", unsafe_allow_html=True)

    # ── Cover Letter ──────────────────────────────────────────────
    with st.expander("Cover Letter", expanded=True):
        cl_col1, cl_col2 = st.columns([3, 1])
        with cl_col2:
            if st.button("⚡ Rewrite with Sonnet", key="regen_cl", help="Stream a higher-quality Sonnet rewrite"):
                st.session_state["pkg_cl"] = ""
                pkg_cl = ""
        with cl_col1:
            st.caption("Claude Sonnet · Personalized to this job")

        if not pkg_cl and pkg_job:
            with st.spinner("Writing your cover letter…"):
                streamed = st.write_stream(stream_cover_letter_claude(profile, pkg_job))
            st.session_state["pkg_cl"] = streamed
            pkg_cl = streamed
            st.rerun()

        edited_cl = st.text_area("Edit before sending", value=pkg_cl, height=440, key="pkg_cl_edit")

        # Quality eval badge
        if pkg_cl:
            try:
                from eval_engine import evaluate
                ev = evaluate(
                    pkg_cl, "cover_letter",
                    resume_text=profile.get("raw_text",""),
                    job_description=pkg_job.get("description",""),
                    persist=True,
                )
                grade_c = {"A":"#10b981","B":"#3b82f6","C":"#f59e0b","D":"#f97316","F":"#ef4444"}.get(ev["grade"],"#64748b")
                st.markdown(
                    f"<div style='display:flex;gap:16px;align-items:center;margin-bottom:8px'>"
                    f"<span style='font-size:11px;color:#64748b'>AI Quality:</span>"
                    f"<span style='font-size:13px;font-weight:900;color:{grade_c}'>Grade {ev['grade']} ({ev['overall']}%)</span>"
                    f"<span style='font-size:11px;color:#64748b'>"
                    f"Grounding: {ev['grounding']}% · Specificity: {ev['specificity']}% · JD Coverage: {ev['keyword_cov']}%"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )
                for flag in ev.get("flags", []):
                    st.caption(f"⚠ {flag}")
            except Exception:
                pass

        try:
            from pdf_export import cover_letter_pdf
            pdf_bytes = cover_letter_pdf(edited_cl, profile.get("name",""), pkg_job.get("company",""), pkg_job.get("title",""))
            st.download_button(
                "⬇ Download Cover Letter PDF", data=pdf_bytes,
                file_name=f"cover_letter_{pkg_job.get('company','').replace(' ','_')}.pdf",
                mime="application/pdf", use_container_width=True,
            )
        except Exception:
            pass

    # ── Targeted Bullets ──────────────────────────────────────────
    if pkg_bullets:
        with st.expander(f"Targeted Resume Bullets ({len(pkg_bullets)} missing keywords)", expanded=False):
            st.caption("Add these bullets to your resume to close the ATS keyword gap. Fill in the [brackets] with your real numbers.")
            for kw, bullet in pkg_bullets:
                st.markdown(
                    f"<div class='card-slate' style='padding:12px 16px;margin-bottom:8px'>"
                    f"<div style='font-size:10px;font-weight:800;color:#3b82f6;text-transform:uppercase;margin-bottom:5px'>{xe(kw)}</div>"
                    f"<div style='font-size:13px;color:#cbd5e1;line-height:1.6'>• {xe(bullet)}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

    # ── Interview Questions Preview ────────────────────────────────
    if pkg_qs:
        with st.expander(f"Likely Interview Questions ({len(pkg_qs)} questions)", expanded=False):
            st.caption("Generated from the job description — prep these before your interview.")
            for item in pkg_qs[:8]:
                st.markdown(
                    f"<div class='card-slate' style='padding:12px 16px;margin-bottom:8px'>"
                    f"<div style='font-size:13px;color:#e2e8f0;font-weight:600;margin-bottom:6px'>{xe(item['question'])}</div>"
                    f"<div style='font-size:12px;color:#64748b;line-height:1.6'>{xe(item['hint'])}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

    # ── Thank-You Note ────────────────────────────────────────────
    with st.expander("Thank-You Note (post-interview)", expanded=False):
        st.caption("Fill in the details below and Claude writes a fully personalized note — no brackets.")
        ty_c1, ty_c2 = st.columns(2)
        ty_interviewer = ty_c1.text_input(
            "Interviewer name", placeholder="e.g. Sarah Chen",
            value=st.session_state.get("pkg_ty_interviewer", ""), key="ty_name"
        )
        ty_topics = ty_c2.text_input(
            "What did you discuss?", placeholder="e.g. Python ML pipeline, team structure, growth path",
            value=st.session_state.get("pkg_ty_topics", ""), key="ty_topics"
        )

        if st.button("Generate Thank-You with AI", key="gen_ty", type="primary"):
            if ty_interviewer and ty_topics:
                st.session_state["pkg_ty_interviewer"] = ty_interviewer
                st.session_state["pkg_ty_topics"]      = ty_topics
                with st.spinner("Writing your thank-you note…"):
                    streamed_ty = st.write_stream(stream_thankyou_claude(
                        interviewer_name=ty_interviewer,
                        role=pkg_job.get("title", ""),
                        company=pkg_job.get("company", ""),
                        topics_discussed=ty_topics,
                        candidate_name=profile.get("name", ""),
                        resume_text=profile.get("raw_text", ""),
                    ))
                st.session_state["pkg_ty"] = streamed_ty
                st.rerun()
            else:
                st.warning("Add the interviewer name and topics to generate a personalized note.")

        pkg_ty = st.session_state.get("pkg_ty", "")
        if pkg_ty:
            edited_ty = st.text_area("Edit before sending", value=pkg_ty, height=280, key="pkg_ty_edit")
        else:
            st.info("Enter interviewer name and discussion topics above, then click Generate.")

    # ── Full PDF Package ──────────────────────────────────────────
    st.markdown("---")
    try:
        from pdf_export import apply_package_pdf
        col_pdf, col_mark = st.columns([2, 1])
        with col_pdf:
            pdf_bytes_full = apply_package_pdf(
                name=profile.get("name",""),
                job=pkg_job,
                ats=pkg_ats,
                cover_letter_text=edited_cl if "pkg_cl_edit" in st.session_state else pkg_cl,
                bullets_text="\n".join(f"• {b}" for _, b in pkg_bullets),
                thankyou_text=edited_ty if "pkg_ty_edit" in st.session_state else pkg_ty,
            )
            co = (pkg_job.get("company","") or "").replace(" ","_")
            st.download_button(
                "⬇ Download Full Apply Package PDF", data=pdf_bytes_full,
                file_name=f"apply_package_{co}.pdf",
                mime="application/pdf", use_container_width=True, type="primary",
            )
        with col_mark:
            _app_url = str(pkg_job.get("url","")).strip()
            if _app_url.startswith("http"):
                st.link_button("Apply Now ↗", _app_url, use_container_width=True)
    except Exception:
        pass

    # Track as applied — works for both pre-saved and freshly-generated packages
    _app_id_str = str(pkg_job.get("id", ""))
    if _app_id_str.startswith("saved_"):
        try:
            _real_id = int(_app_id_str.replace("saved_", ""))
            _current_status = next((a["status"] for a in all_saved if a["id"] == _real_id), None)
            if _current_status in (None, "saved"):
                if st.button("Mark as Applied", key="mark_applied"):
                    tracker.update_status(_real_id, "applied")
                    st.success("Marked as applied. Follow-up reminder scheduled for 7 days from now.")
                    st.rerun()
        except Exception:
            pass
    elif _app_id_str and _app_id_str != "manual":
        # Job came from a live search — save it first, then mark applied
        if st.button("Save & Mark as Applied", key="save_mark_applied"):
            tracker.save_job(pkg_job, score=pkg_ats.get("score", 0) if pkg_ats else 0)
            _saved_app = next((a for a in tracker.get_all(st.session_state.get("active_user_id", 1)) if a["job_id"] == _app_id_str), None)
            if _saved_app:
                tracker.update_status(_saved_app["id"], "applied")
            st.success("Saved and marked as applied. Follow-up reminder scheduled for 7 days from now.")
            st.rerun()
