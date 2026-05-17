import os
import re
import random
import tempfile
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import (
    inject_css, alert, chip, score_badge, score_color, progress_bar,
    _load_vault, _save_vault, RESUME_EXAMPLES, EXAMPLE_TIPS,
)
from resume_parser import parse_resume
from resume_editor import full_analysis
from scorer import get_model
import tracker

inject_css()

profile = st.session_state.get("resume")
if not profile:
    st.markdown("<div class='page-title'>Resume Analyzer</div>", unsafe_allow_html=True)
    st.markdown("<div class='page-sub'>Upload your resume to get an instant score, section breakdown, bullet coaching, and ATS keyword analysis.</div>", unsafe_allow_html=True)

    uploaded = st.file_uploader("Upload your resume (PDF or DOCX)", type=["pdf", "docx"], label_visibility="visible")
    if uploaded:
        _MAX = 10 * 1024 * 1024
        if uploaded.size > _MAX:
            st.error("File too large (max 10 MB).")
            st.stop()
        suffix = "." + uploaded.name.rsplit(".", 1)[-1].lower()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name
            with st.spinner("Analyzing your resume — loading AI model on first run (30–60 s)…"):
                from resume_parser import extract_text
                text = extract_text(tmp_path)
                if not text or len(text.strip()) < 50:
                    st.error("Could not extract text from this file. Try a different PDF or paste your resume as text.")
                    st.stop()
                p = parse_resume(text)
                get_model()
                analysis = full_analysis(text)
                st.session_state.resume = p
                st.session_state.resume_analysis = analysis
                st.session_state.resume_score = analysis["overall_score"]
                try:
                    import profile_store as _ps
                    _ps.set_resume_text(text, st.session_state.get("active_user_id", 1))
                except Exception:
                    pass
                for k in ["dashboard_jobs", "cover_letter", "ats_result", "interview_qs",
                          "apply_pkg_job", "apply_pkg_id", "pkg_ats", "pkg_cl", "tailor_results"]:
                    st.session_state.pop(k, None)
        except Exception as e:
            st.error(f"Upload failed: {e}")
            st.stop()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        st.rerun()
    else:
        st.stop()

analysis = st.session_state.get("resume_analysis") or full_analysis(profile["raw_text"])

tab_edit, tab_analyze, tab_bullets, tab_suggestions, tab_tailor, tab_examples = st.tabs([
    "Edit", "Section Analysis", "Bullet Coach", "Suggestions", "Tailor for Job", "Examples"
])

# ── Edit tab ──
with tab_edit:
    st.caption("Edit your resume directly. Changes update your live analysis.")
    edited_text = st.text_area(
        "Resume Text",
        value=profile["raw_text"],
        height=900,
        label_visibility="collapsed"
    )
    col_update, col_dl, _ = st.columns([1, 1, 4])
    with col_update:
        if st.button("Update Analysis", type="primary"):
            new_profile = parse_resume(edited_text)
            new_profile["name"] = profile["name"]
            new_analysis = full_analysis(edited_text)
            st.session_state.resume = new_profile
            st.session_state.resume_analysis = new_analysis
            st.session_state.resume_score = new_analysis["overall_score"]
            for k in ["dashboard_jobs","cover_letter","ats_result","interview_qs"]:
                st.session_state.pop(k, None)
            st.success(f"Updated! New score: {new_analysis['overall_score']}% (Grade {new_analysis['grade']})")

    # ── Resume Vault ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-tag'>Resume Vault — A/B Testing</div>", unsafe_allow_html=True)
    st.caption("Save named versions of your resume to track which performs best in applications.")

    from datetime import datetime as _dt
    vault = _load_vault()
    _vault_col1, _vault_col2 = st.columns([2, 2])
    with _vault_col1:
        _ver_name = st.text_input("Version name", placeholder="e.g. Tech v1, Finance focus, Short version", key="vault_name_input")
        if st.button("Save Current as Version", key="vault_save_btn") and _ver_name.strip():
            vault[_ver_name.strip()] = {
                "text": edited_text,
                "score": st.session_state.get("resume_score", 0),
                "saved": _dt.now().isoformat()[:10],
            }
            _save_vault(vault)
            st.session_state.active_resume_version = _ver_name.strip()
            st.success(f"Saved '{_ver_name.strip()}' to vault. Jobs saved from now will be tagged with this version.")
            st.rerun()

    with _vault_col2:
        if vault:
            _load_ver = st.selectbox(
                "Load a saved version",
                ["— select —"] + list(vault.keys()),
                key="vault_load_sel",
            )
            if st.button("Load Version", key="vault_load_btn") and _load_ver != "— select —":
                _vdata = vault[_load_ver]
                new_p = parse_resume(_vdata["text"])
                new_p["name"] = profile["name"]
                new_a = full_analysis(_vdata["text"])
                st.session_state.resume = new_p
                st.session_state.resume_analysis = new_a
                st.session_state.resume_score = new_a["overall_score"]
                st.session_state.active_resume_version = _load_ver
                st.success(f"Loaded '{_load_ver}'.")
                st.rerun()
        else:
            st.caption("No saved versions yet — save your first version above.")

    _active_ver = st.session_state.get("active_resume_version")
    if _active_ver:
        st.markdown(
            f"<div style='font-size:12px;color:#7c3aed;font-weight:600;margin-top:4px'>"
            f"Active version: <b>{_active_ver}</b> — jobs you save will be tagged with this version</div>",
            unsafe_allow_html=True
        )
    if vault:
        with st.expander(f"Vault — {len(vault)} saved version(s)", expanded=False):
            _vstats = tracker.get_version_stats()
            for _vn, _vd in vault.items():
                _vs = _vstats.get(_vn, {})
                _resp = _vs.get("response_rate", "—")
                _apps = _vs.get("applied", 0) + _vs.get("interview", 0) + _vs.get("offer", 0) + _vs.get("rejected", 0)
                _row_left, _row_right, _row_del = st.columns([4, 2, 1])
                _row_left.markdown(
                    f"<div style='padding:6px 0'><b style='font-size:13px'>{_vn}</b>"
                    f"<span style='color:#94a3b8;font-size:11px;margin-left:8px'>saved {_vd.get('saved','')} · score {_vd.get('score',0)}%</span></div>",
                    unsafe_allow_html=True
                )
                _row_right.markdown(
                    f"<div style='font-size:12px;color:#475569;padding:10px 0'>{_apps} apps · "
                    f"<b style='color:#2563eb'>{_resp}% response</b></div>",
                    unsafe_allow_html=True
                )
                if _row_del.button("🗑", key=f"del_vault_{_vn}", help=f"Delete '{_vn}'"):
                    tracker.delete_vault_version(_vn)
                    if st.session_state.get("active_resume_version") == _vn:
                        st.session_state.pop("active_resume_version", None)
                    st.rerun()

# ── Analysis tab ──
with tab_analyze:
    overall = analysis["overall_score"]
    dims    = analysis.get("dimension_scores", {})
    col_score, col_breakdown = st.columns([1, 3])
    with col_score:
        st.markdown(
            f"<div style='text-align:center;padding:20px 0'>"
            f"{score_badge(overall, 80)}"
            f"<div style='font-size:32px;font-weight:800;margin-top:8px'>{analysis['grade']}</div>"
            f"<div style='color:#64748b;font-size:13px'>Overall Score</div>"
            f"</div>", unsafe_allow_html=True
        )
        if dims:
            def _dim_bar(label, val, color):
                filled = int(val / 10 * 80)
                return (
                    f"<div style='margin-bottom:10px'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:11.5px;"
                    f"font-weight:600;color:#475569;margin-bottom:3px'>"
                    f"<span>{label}</span><span style='color:{color}'>{val}/10</span></div>"
                    f"<div style='background:#e2e8f0;border-radius:4px;height:6px'>"
                    f"<div style='background:{color};width:{filled}%;height:6px;border-radius:4px'></div>"
                    f"</div></div>"
                )
            imp_c = "#059669" if dims["impact"] >= 7 else "#d97706" if dims["impact"] >= 5 else "#dc2626"
            cla_c = "#059669" if dims["clarity"] >= 7 else "#d97706" if dims["clarity"] >= 5 else "#dc2626"
            str_c = "#059669" if dims["structure"] >= 7 else "#d97706" if dims["structure"] >= 5 else "#dc2626"
            st.markdown(
                f"<div style='margin-top:16px;padding:12px 14px;background:#f8fafc;"
                f"border-radius:10px;border:1px solid #e2e8f0'>"
                f"<div style='font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;"
                f"letter-spacing:.06em;margin-bottom:10px'>Score Breakdown</div>"
                + _dim_bar("Impact", dims["impact"], imp_c)
                + _dim_bar("Clarity", dims["clarity"], cla_c)
                + _dim_bar("Structure", dims["structure"], str_c)
                + "</div>",
                unsafe_allow_html=True
            )
    with col_breakdown:
        for sec_name, sec_data in analysis["section_analyses"].items():
            s = sec_data["score"]
            bar_color = score_color(s)
            sec_grade = "A" if s >= 85 else "B" if s >= 70 else "C" if s >= 55 else "D"
            grade_color = "#059669" if s >= 70 else "#d97706" if s >= 55 else "#dc2626"
            st.markdown(
                f"<div style='margin-bottom:14px'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<span style='font-weight:600;font-size:13.5px'>{sec_name}</span>"
                f"<span style='display:flex;align-items:center;gap:8px'>"
                f"<span style='font-size:11px;font-weight:700;color:{grade_color};"
                f"background:{grade_color}18;border-radius:4px;padding:1px 7px'>{sec_grade}</span>"
                f"<span style='font-size:12px;font-weight:700;color:{bar_color}'>{s}/100</span>"
                f"</span></div>"
                f"{progress_bar(s, bar_color)}"
                + "".join(f"<div style='font-size:12px;color:#dc2626;margin-top:3px;padding-left:2px'>⚠ {i}</div>" for i in sec_data["issues"])
                + "".join(f"<div style='font-size:12px;color:#2563eb;margin-top:3px;padding-left:2px'>💡 {sg}</div>" for sg in sec_data["suggestions"])
                + "</div>", unsafe_allow_html=True
            )

    if analysis["missing_sections"]:
        st.markdown("---")
        st.markdown("**Missing Sections**")
        for sec in analysis["missing_sections"]:
            st.markdown(alert(f"<b>{sec}</b> — {analysis['missing_tips'].get(sec,'')}", "red"), unsafe_allow_html=True)

    st.markdown("---")
    from pdf_export import analysis_report_pdf
    rpt_bytes = analysis_report_pdf(profile, analysis)
    st.download_button(
        "⬇ Download Analysis Report PDF",
        data=rpt_bytes,
        file_name=f"CareerIQ_ResumeReport_{profile.get('name','').replace(' ','_')}.pdf",
        mime="application/pdf",
    )

# ── Bullet coach tab ──
with tab_bullets:
    bullets = analysis["bullet_analyses"]
    if not bullets:
        st.info("No bullet points detected. Make sure your Experience section is in the resume text.")
    else:
        strong  = [b for b in bullets if b["score"] >= 75]
        weak    = [b for b in bullets if b["score"] <  75]
        avg_sc  = int(sum(b["score"] for b in bullets) / len(bullets))

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Bullets Analyzed", len(bullets))
        c2.metric("Avg Score", f"{avg_sc}%")
        c3.metric("Strong (75+)", len(strong))
        c4.metric("Need Work", len(weak))

        if weak:
            st.markdown(
                f"<div style='font-size:13px;color:#64748b;margin:14px 0 8px'>"
                f"Showing <b>{len(weak)}</b> bullets to improve — sorted from weakest to strongest.</div>",
                unsafe_allow_html=True
            )
            for idx, b in enumerate(sorted(weak, key=lambda x: x["score"])):
                bg          = score_color(b["score"])
                grade_l     = "D" if b["score"] < 40 else "C" if b["score"] < 60 else "B-"
                left_border = "#dc2626" if b["score"] < 50 else "#d97706"
                issues_html = "".join(
                    f"<div style='display:flex;align-items:flex-start;gap:6px;margin-bottom:5px'>"
                    f"<span style='color:#dc2626;font-size:12px;line-height:1.6;flex-shrink:0'>⚠</span>"
                    f"<span style='font-size:12.5px;color:#7f1d1d;line-height:1.6'>{i}</span>"
                    f"</div>"
                    for i in b["issues"]
                )
                st.markdown(
                    f"<div style='border:1px solid #e2e8f0;border-left:4px solid {left_border};"
                    f"border-radius:10px;padding:14px 16px;margin-bottom:12px;background:#fff'>"
                    f"<div style='display:flex;align-items:flex-start;gap:10px;margin-bottom:10px'>"
                    f"<div style='background:{bg};color:#fff;border-radius:6px;padding:3px 9px;"
                    f"font-size:12px;font-weight:800;white-space:nowrap;flex-shrink:0'>{b['score']}% {grade_l}</div>"
                    f"<div style='font-size:13px;color:#374151;font-style:italic;line-height:1.5'>\"{b['text'][:150]}{'…' if len(b['text'])>150 else ''}\"</div>"
                    f"</div>"
                    f"<div style='background:#fff7f7;border-radius:6px;padding:8px 10px;margin-bottom:8px'>"
                    f"{issues_html}"
                    f"</div>"
                    f"<div style='padding:8px 12px;background:#f0f9ff;border-radius:6px;"
                    f"font-size:13px;border-left:3px solid #2563eb;color:#1e3a5f;line-height:1.6'>"
                    f"<span style='font-weight:700;font-size:11px;text-transform:uppercase;"
                    f"letter-spacing:.06em;color:#2563eb;display:block;margin-bottom:3px'>Suggested rewrite</span>"
                    f"{b['suggestion']}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                from claude_ai import rewrite_bullet_claude

                _WEAK_VERB_MAP = {
                    "helped": "Supported", "worked on": "Executed", "was responsible for": "Owned",
                    "did": "Delivered", "made": "Built", "assisted": "Partnered on", "handled": "Managed",
                    "worked with": "Collaborated with", "involved in": "Contributed to",
                    "participated in": "Drove", "used": "Leveraged", "did work on": "Executed",
                }
                _STRONG_VERBS = [
                    "Accelerated","Achieved","Analyzed","Built","Championed","Collaborated",
                    "Delivered","Designed","Developed","Drove","Engineered","Executed","Generated",
                    "Launched","Led","Managed","Optimized","Orchestrated","Owned","Partnered",
                    "Reduced","Scaled","Spearheaded","Streamlined","Transformed",
                ]

                def _local_bullet_rewrites(bullet_text):
                    text = bullet_text.strip().rstrip(".")
                    rewrite1 = text
                    for weak, strong in _WEAK_VERB_MAP.items():
                        if text.lower().startswith(weak):
                            rewrite1 = strong + text[len(weak):]
                            break
                    else:
                        verb = random.choice(_STRONG_VERBS)
                        parts = text.split(" ", 1)
                        if len(parts) > 1:
                            rewrite1 = f"{verb} {parts[1]}"
                    rewrite2 = f"{rewrite1.rstrip('.')} — resulting in [add specific metric: X%, $Y, Z hours saved]."
                    rewrite3 = f"{rewrite1.rstrip('.')} to achieve [outcome], saving [time/money] across [scope]."
                    return [
                        ("Stronger verb", rewrite1),
                        ("+ Result metric", rewrite2),
                        ("+ Scope & impact", rewrite3),
                    ]

                ai_key    = f"ai_bullet_{idx}"
                local_key = f"local_bullet_{idx}"
                col_local, col_ai, _ = st.columns([1.2, 1, 4])
                with col_local:
                    if st.button("⚡ Quick Rewrites", key=f"local_b_btn_{idx}", use_container_width=True):
                        st.session_state[local_key] = _local_bullet_rewrites(b["text"])
                with col_ai:
                    if st.button("✨ AI Rewrite", key=f"ai_b_btn_{idx}", use_container_width=True):
                        with st.spinner("Claude rewriting…"):
                            st.session_state[ai_key] = rewrite_bullet_claude(
                                b["text"], profile["raw_text"]
                            )
                if st.session_state.get(local_key):
                    for _rw_label, _rw_text in st.session_state[local_key]:
                        st.markdown(
                            f"<div style='background:#f8fafc;border:1px solid #e2e8f0;border-left:3px solid #7c3aed;"
                            f"border-radius:6px;padding:8px 12px;margin-bottom:6px'>"
                            f"<div style='font-size:10px;font-weight:700;color:#7c3aed;text-transform:uppercase;"
                            f"letter-spacing:.06em;margin-bottom:3px'>{_rw_label}</div>"
                            f"<div style='font-size:13px;color:#0f172a'>{_rw_text}</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                if st.session_state.get(ai_key):
                    st.text_area(
                        "Claude's rewrite — copy & paste into your resume:",
                        value=st.session_state[ai_key],
                        key=f"ai_b_edit_{idx}",
                        height=80,
                    )

        if strong:
            with st.expander(f"✅ {len(strong)} strong bullets — click to review"):
                for b in strong:
                    st.markdown(
                        f"<div style='padding:6px 0;font-size:13px;color:#065f46;border-bottom:1px solid #dcfce7'>"
                        f"<span style='font-weight:700;color:#059669'>{b['score']}%</span>"
                        f"&nbsp;&nbsp;{b['text']}</div>",
                        unsafe_allow_html=True
                    )

# ── Suggestions tab ──
with tab_suggestions:
    action_plan = analysis.get("action_plan", {})
    quick_wins  = action_plan.get("quick_wins", [])
    high_impact = action_plan.get("high_impact", [])

    dims = analysis.get("dimension_scores", {})
    if dims:
        d_impact    = dims.get("impact", 5)
        d_clarity   = dims.get("clarity", 5)
        d_structure = dims.get("structure", 5)
        def _score_card(label, val, desc):
            c = "#059669" if val >= 7 else "#d97706" if val >= 5 else "#dc2626"
            bg = "#f0fdf4" if val >= 7 else "#fffbeb" if val >= 5 else "#fef2f2"
            return (
                f"<div style='background:{bg};border-radius:10px;padding:14px 16px;"
                f"text-align:center;border:1px solid {c}30'>"
                f"<div style='font-size:26px;font-weight:900;color:{c}'>{val}/10</div>"
                f"<div style='font-size:12px;font-weight:700;color:#374151;margin:2px 0'>{label}</div>"
                f"<div style='font-size:11px;color:#6b7280'>{desc}</div>"
                f"</div>"
            )
        sc1, sc2, sc3 = st.columns(3)
        sc1.markdown(_score_card("Impact", d_impact, "Measurable results & outcomes"), unsafe_allow_html=True)
        sc2.markdown(_score_card("Clarity", d_clarity, "Specific, active language"), unsafe_allow_html=True)
        sc3.markdown(_score_card("Structure", d_structure, "Sections & completeness"), unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if quick_wins:
        st.markdown(
            "<div style='font-size:14px;font-weight:800;color:#0f172a;margin:12px 0 6px'>"
            "Quick Wins — fix these in under 5 minutes each</div>",
            unsafe_allow_html=True
        )
        for i, item in enumerate(quick_wins, 1):
            example_html = (
                f"<div style='margin-top:8px;padding:7px 10px;background:#f0f9ff;"
                f"border-left:3px solid #2563eb;border-radius:4px;"
                f"font-size:12.5px;color:#1e3a5f;font-style:italic'>"
                f"{item['example']}</div>"
            ) if item.get("example") else ""
            st.markdown(
                f"<div style='border:1px solid #e2e8f0;border-left:4px solid #059669;"
                f"border-radius:10px;padding:14px 16px;margin-bottom:8px;background:#fff'>"
                f"<div style='display:flex;align-items:flex-start;gap:10px'>"
                f"<div style='background:#059669;color:#fff;border-radius:50%;width:22px;height:22px;"
                f"display:flex;align-items:center;justify-content:center;"
                f"font-size:11px;font-weight:800;flex-shrink:0'>{i}</div>"
                f"<div style='flex:1'>"
                f"<div style='font-size:13.5px;font-weight:700;color:#0f172a;margin-bottom:4px'>{item['title']}</div>"
                f"<div style='font-size:12.5px;color:#6b7280;margin-bottom:4px'><b>Why it matters:</b> {item['why']}</div>"
                f"<div style='font-size:12.5px;color:#374151'><b>Fix:</b> {item['how']}</div>"
                f"{example_html}"
                f"</div></div></div>",
                unsafe_allow_html=True
            )

    if high_impact:
        st.markdown(
            "<div style='font-size:14px;font-weight:800;color:#0f172a;margin:16px 0 6px'>"
            "High Impact — bigger improvements worth the time</div>",
            unsafe_allow_html=True
        )
        for item in high_impact:
            example_html = (
                f"<div style='margin-top:8px;padding:7px 10px;background:#f0fdf4;"
                f"border-left:3px solid #059669;border-radius:4px;"
                f"font-size:12.5px;color:#064e3b'>"
                f"<b>Example:</b> {item['example']}</div>"
            ) if item.get("example") else ""
            st.markdown(
                f"<div style='border:1px solid #e2e8f0;border-left:4px solid #2563eb;"
                f"border-radius:10px;padding:14px 16px;margin-bottom:8px;background:#fff'>"
                f"<div style='font-size:13.5px;font-weight:700;color:#0f172a;margin-bottom:5px'>{item['title']}</div>"
                f"<div style='font-size:12.5px;color:#6b7280;margin-bottom:4px'><b>Why:</b> {item['why']}</div>"
                f"<div style='font-size:12.5px;color:#374151'><b>How:</b> {item['how']}</div>"
                f"{example_html}"
                f"</div>",
                unsafe_allow_html=True
            )

    if not quick_wins and not high_impact:
        st.markdown(alert("Your resume looks solid! Use the Tailor tab to optimize it for a specific job description.", "green"), unsafe_allow_html=True)

# ── Tailor for Job tab ──
with tab_tailor:
    st.markdown("<div class='page-sub'>Paste a job description — get side-by-side rewrites of your weakest bullets, targeted to <i>this specific role</i>.</div>", unsafe_allow_html=True)
    tailor_jd = st.text_area("Paste job description", height=160, placeholder="Paste the full job posting here…", key="tailor_jd_input")

    if st.button("Tailor My Resume", type="primary", key="tailor_btn") and tailor_jd.strip():
        from ai_tools import ats_scan as _ats
        from scorer import get_model
        from sentence_transformers import util
        from claude_ai import decode_jd_claude, tailor_resume_claude, explain_skill_gaps_claude

        with st.spinner("Analyzing fit, decoding JD, and generating tailored rewrites…"):
            ats_r = _ats(profile["raw_text"], tailor_jd)
            jd_decoded       = decode_jd_claude(profile["raw_text"], tailor_jd)
            claude_rewrites  = tailor_resume_claude(profile["raw_text"], tailor_jd)
            gap_explanations = explain_skill_gaps_claude(
                ats_r.get("missing_hard", ats_r.get("missing_keywords", []))[:5],
                profile["raw_text"], tailor_jd
            )
            bullets_a = analysis.get("bullet_analyses", [])
            model   = get_model()
            results = []
            for kw in ats_r.get("missing_keywords", [])[:6]:
                kw_emb = model.encode(kw, convert_to_tensor=True)
                best_b, best_s = None, -1
                for b in bullets_a:
                    b_emb = model.encode(b["text"], convert_to_tensor=True)
                    s = util.cos_sim(kw_emb, b_emb).item()
                    if s > best_s:
                        best_s, best_b = s, b
                if best_b:
                    results.append({"kw": kw, "original": best_b["text"], "score": best_b["score"]})

        st.session_state.tailor_results          = (ats_r, results, tailor_jd)
        st.session_state.tailor_decoded          = jd_decoded
        st.session_state.tailor_claude_rewrites  = claude_rewrites
        st.session_state.tailor_gap_explanations = gap_explanations

    if st.session_state.get("tailor_results"):
        ats_r, results, _ = st.session_state.tailor_results
        vc_color = {"strong":"#059669","medium":"#d97706","weak":"#dc2626"}[ats_r["verdict"][0]]

        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div style='text-align:center'>{score_badge(ats_r['score'],56)}<div style='font-size:11px;color:#94a3b8;margin-top:4px'>ATS Score</div></div>", unsafe_allow_html=True)
        c2.metric("Keyword Match",  f"{ats_r['keyword_score']}%")
        c3.metric("Semantic Match", f"{ats_r['semantic_score']}%")
        st.markdown(alert(ats_r["verdict"][1], "green" if ats_r["verdict"][0]=="strong" else "amber" if ats_r["verdict"][0]=="medium" else "red"), unsafe_allow_html=True)

        if ats_r.get("found_keywords"):
            st.markdown("<span style='font-size:12px;font-weight:600;color:#059669'>Keywords you already have: </span>" + " ".join(chip(k,"green") for k in ats_r["found_keywords"][:10]), unsafe_allow_html=True)
        missing_hard = ats_r.get("missing_hard") or ats_r.get("missing_keywords", [])
        missing_soft = ats_r.get("missing_soft", [])
        if missing_hard:
            st.markdown("<span style='font-size:12px;font-weight:600;color:#dc2626'>Hard skills to add: </span>" + " ".join(chip(k,"red") for k in missing_hard[:8]), unsafe_allow_html=True)
        if missing_soft:
            st.markdown("<span style='font-size:12px;font-weight:600;color:#d97706'>Soft skills to highlight: </span>" + " ".join(chip(k,"amber") for k in missing_soft[:6]), unsafe_allow_html=True)

        gap_exps = st.session_state.get("tailor_gap_explanations")
        if gap_exps:
            with st.expander("💡 Why these gaps matter — and how to fix them", expanded=True):
                for g in gap_exps:
                    st.markdown(
                        f"<div style='border:1px solid #e2e8f0;border-left:4px solid #d97706;"
                        f"border-radius:8px;padding:10px 14px;margin-bottom:8px;background:#fff'>"
                        f"<div style='font-weight:700;font-size:13px;color:#0f172a;margin-bottom:4px'>{g.get('skill','')}</div>"
                        f"<div style='font-size:12.5px;color:#475569;margin-bottom:3px'><b>Why it matters:</b> {g.get('why','')}</div>"
                        f"<div style='font-size:12.5px;color:#059669'><b>How to fix:</b> {g.get('how','')}</div>"
                        f"</div>", unsafe_allow_html=True
                    )

        decoded = st.session_state.get("tailor_decoded")
        if decoded:
            st.markdown("---")
            st.markdown("<div class='section-tag'>JD Decoder — What This Role Really Wants</div>", unsafe_allow_html=True)
            dc1, dc2 = st.columns(2)
            with dc1:
                if decoded.get("what_they_want"):
                    st.markdown("<div style='font-size:12.5px;font-weight:700;color:#0f172a;margin-bottom:6px'>What they actually need</div>", unsafe_allow_html=True)
                    for item in decoded["what_they_want"]:
                        st.markdown(f"<div class='card-slate' style='margin-bottom:6px;font-size:13px'>🎯 {item}</div>", unsafe_allow_html=True)
                if decoded.get("gaps"):
                    st.markdown("<div style='font-size:12.5px;font-weight:700;color:#dc2626;margin:12px 0 6px'>Honest gaps — with fixes</div>", unsafe_allow_html=True)
                    for item in decoded["gaps"]:
                        st.markdown(f"<div class='card-red' style='margin-bottom:6px;font-size:13px'>⚠ {item}</div>", unsafe_allow_html=True)
            with dc2:
                if decoded.get("stand_out"):
                    st.markdown("<div style='font-size:12.5px;font-weight:700;color:#059669;margin-bottom:6px'>How you stand out</div>", unsafe_allow_html=True)
                    for item in decoded["stand_out"]:
                        st.markdown(f"<div class='card-green' style='margin-bottom:6px;font-size:13px'>✓ {item}</div>", unsafe_allow_html=True)
                if decoded.get("questions"):
                    st.markdown("<div style='font-size:12.5px;font-weight:700;color:#2563eb;margin:12px 0 6px'>Smart questions to ask them</div>", unsafe_allow_html=True)
                    for item in decoded["questions"]:
                        st.markdown(f"<div class='card-blue' style='margin-bottom:6px;font-size:13px'>💬 {item}</div>", unsafe_allow_html=True)

        if ats_r.get("cliches"):
            st.markdown(
                "<div style='margin-top:8px'>"
                "<span style='font-size:12px;font-weight:600;color:#7c3aed'>Buzzwords to replace: </span>"
                + " ".join(f"<span style='display:inline-block;background:#ede9fe;color:#5b21b6;"
                           f"border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600;margin:2px'>"
                           f"🚫 {c}</span>" for c in ats_r["cliches"][:6])
                + "<span style='font-size:11px;color:#94a3b8;margin-left:6px'>"
                "— replace with specific achievements or quantified examples</span>"
                "</div>", unsafe_allow_html=True
            )

        claude_rewrites = st.session_state.get("tailor_claude_rewrites")
        if claude_rewrites:
            st.markdown("---")
            st.markdown("<div class='section-tag'>AI-Tailored Resume Rewrites</div>", unsafe_allow_html=True)
            st.caption("Your existing bullets rewritten by Claude to match this specific job description. Copy and replace in your resume.")
            for r in claude_rewrites:
                st.markdown(
                    f"<div class='card' style='margin-bottom:12px'>"
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
                    f"{chip(r.get('keyword',''), 'purple')}"
                    f"<span style='font-size:11px;color:#94a3b8'>keyword targeted</span></div>"
                    f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>"
                    f"<div style='background:#fef2f2;border-radius:8px;padding:12px'>"
                    f"<div style='font-size:10px;font-weight:700;color:#dc2626;margin-bottom:4px'>BEFORE</div>"
                    f"<div style='font-size:13px;color:#1e293b'>{r.get('original','')}</div></div>"
                    f"<div style='background:#f0fdf4;border-radius:8px;padding:12px'>"
                    f"<div style='font-size:10px;font-weight:700;color:#059669;margin-bottom:4px'>AFTER — Claude Rewrite</div>"
                    f"<div style='font-size:13px;color:#1e293b'>{r.get('rewritten','')}</div></div>"
                    f"</div></div>", unsafe_allow_html=True
                )
        elif results:
            st.markdown("---")
            st.markdown("<div class='section-tag'>Before → After: Targeted Rewrites</div>", unsafe_allow_html=True)
            st.caption("These are your existing bullets rewritten to include each missing keyword. Copy and replace in your resume.")
            for r in results:
                kw_lower = r["kw"].lower()
                orig = r["original"]
                TOOLS = {"python","sql","excel","tableau","powerbi","r","java","salesforce",
                          "quickbooks","sap","figma","sketch","jira","confluence","git","aws","azure"}
                METHODS = {"agile","scrum","kanban","lean","six sigma","waterfall","pmp"}
                if kw_lower in TOOLS:
                    rewrite = f"{orig.rstrip('.')} using {r['kw'].title()}."
                elif kw_lower in METHODS:
                    rewrite = f"{orig.rstrip('.')} following {r['kw'].title()} methodology."
                elif len(kw_lower.split()) == 1:
                    rewrite = f"{orig.rstrip('.')} — leveraging {r['kw']} to drive impact. Add: [specific metric]"
                else:
                    rewrite = f"{orig.rstrip('.')} with emphasis on {r['kw']}. Add: [specific outcome or metric]"
                st.markdown(
                    f"<div class='card' style='margin-bottom:12px'>"
                    f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px'>"
                    f"{chip(r['kw'], 'red')}"
                    f"<span style='font-size:11px;color:#94a3b8'>missing keyword → add to this bullet</span></div>"
                    f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>"
                    f"<div style='background:#fef2f2;border-radius:8px;padding:12px'>"
                    f"<div style='font-size:10px;font-weight:700;color:#dc2626;margin-bottom:4px'>BEFORE</div>"
                    f"<div style='font-size:13px;color:#1e293b'>{orig}</div></div>"
                    f"<div style='background:#f0fdf4;border-radius:8px;padding:12px'>"
                    f"<div style='font-size:10px;font-weight:700;color:#059669;margin-bottom:4px'>AFTER</div>"
                    f"<div style='font-size:13px;color:#1e293b'>{rewrite}</div></div>"
                    f"</div></div>", unsafe_allow_html=True
                )
        else:
            st.markdown(alert("No weak bullets found that need targeted rewrites — your resume already covers the key terms well.", "green"), unsafe_allow_html=True)

# ── Examples tab ──
with tab_examples:
    st.markdown("<div class='page-sub'>Browse real resume examples by role — see what strong summaries and bullets look like, then adapt them for your own experience.</div>", unsafe_allow_html=True)
    st.markdown("---")

    role_filter = st.selectbox("Browse examples for:", list(RESUME_EXAMPLES.keys()), key="ex_role_filter")
    ex = RESUME_EXAMPLES[role_filter]

    col_ex, col_tips = st.columns([2, 1])

    with col_ex:
        st.markdown("<div class='section-tag'>Summary / About</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='card' style='background:#f8fafc;border-left:4px solid #2563eb;padding:16px 18px;font-size:14px;line-height:1.65;color:#1e293b'>{ex['summary']}</div>",
            unsafe_allow_html=True
        )
        st.caption("Copy, adapt to your experience, swap in your actual numbers")
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='section-tag'>Strong Experience Bullets</div>", unsafe_allow_html=True)
        for b in ex["bullets"]:
            highlighted = re.sub(r"(\d+[\w%$KM]*|\$[\d,.]+)", r"<strong style='color:#2563eb'>\1</strong>", b)
            st.markdown(
                f"<div class='card' style='padding:10px 14px;margin-bottom:6px;font-size:13.5px;color:#1e293b;line-height:1.55'>"
                f"<span style='color:#2563eb;font-weight:700;margin-right:6px'>•</span>{highlighted}</div>",
                unsafe_allow_html=True
            )
        st.caption("Every bullet: strong verb + specific action + quantified result")

    with col_tips:
        st.markdown("<div class='section-tag'>Writing Tips</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12.5px;font-weight:700;color:#64748b;margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em'>Summary</div>", unsafe_allow_html=True)
        for tip in EXAMPLE_TIPS["summary"]:
            st.markdown(f"<div style='font-size:13px;color:#374151;margin-bottom:8px;padding:8px 10px;background:#f0f9ff;border-radius:6px;line-height:1.5'>✓ {tip}</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12.5px;font-weight:700;color:#64748b;margin:14px 0 8px;text-transform:uppercase;letter-spacing:.04em'>Bullets</div>", unsafe_allow_html=True)
        for tip in EXAMPLE_TIPS["bullets"]:
            st.markdown(f"<div style='font-size:13px;color:#374151;margin-bottom:8px;padding:8px 10px;background:#f0fdf4;border-radius:6px;line-height:1.5'>✓ {tip}</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:12.5px;font-weight:700;color:#64748b;margin:14px 0 8px;text-transform:uppercase;letter-spacing:.04em'>ATS Optimization</div>", unsafe_allow_html=True)
        for tip in EXAMPLE_TIPS["ats"]:
            st.markdown(f"<div style='font-size:13px;color:#374151;margin-bottom:8px;padding:8px 10px;background:#fff7ed;border-radius:6px;line-height:1.5'>⚡ {tip}</div>", unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("<div style='font-size:12px;color:#94a3b8;line-height:1.6'>These examples are based on patterns from strong resumes across industries. Adapt the structure and swap in your real numbers — never copy verbatim.</div>", unsafe_allow_html=True)

