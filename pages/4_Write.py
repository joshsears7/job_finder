import re
import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, score_badge
import tracker

inject_css()

# ── Writing Suite ─────────────────────────────────────────────────
from writing_suite import PROMPT_CATALOG, CATEGORIES, generate
from ai_tools import ats_scan

st.markdown("<div class='page-title'>Writing Suite</div><div class='page-sub'>AI-assisted writing for every stage of your job search — tailored to your profile.</div>", unsafe_allow_html=True)

profile = st.session_state.get("resume")
if not profile:
    st.markdown(alert("Load your resume on the Dashboard first to personalize all outputs.", "blue"), unsafe_allow_html=True)
    st.stop()

# ── Job context (shared across all tools) ──
all_saved   = tracker.get_all(st.session_state.get("active_user_id", 1))
search_jobs = st.session_state.get("jobs", [])
prefill_job = st.session_state.pop("ai_prefill_job", None)

all_jobs = search_jobs + [{
    "id": f"saved_{a['id']}", "title": a["title"], "company": a["company"],
    "location": a["location"], "url": a.get("url", ""), "description": "", "source": a["source"],
} for a in all_saved]

with st.expander("⚙️ Job Context (optional — improves every tool)", expanded=False):
    job_ctx = prefill_job
    if all_jobs:
        use_list = st.checkbox("Use a job from my list", value=bool(prefill_job))
        if use_list:
            labels = [f"{j['title']} @ {j['company']}" for j in all_jobs]
            idx = st.selectbox("Job", range(len(labels)), format_func=lambda i: labels[i], label_visibility="collapsed")
            job_ctx = dict(all_jobs[idx])
    c1, c2 = st.columns(2)
    manual_company = c1.text_input("Company name", value=job_ctx.get("company", "") if job_ctx else "", placeholder="e.g. Goldman Sachs")
    manual_role    = c2.text_input("Job title",    value=job_ctx.get("title", "")   if job_ctx else "", placeholder="e.g. Business Analyst")
    pasted_jd = st.text_area("Paste job description", value=job_ctx.get("description", "") if job_ctx else "", height=120, placeholder="Paste the full posting for best results…")

job = {
    "id":      "writing_ctx",
    "title":   manual_role    or (job_ctx.get("title", "")   if job_ctx else "this role"),
    "company": manual_company or (job_ctx.get("company", "") if job_ctx else "your company"),
    "location": "",
    "description": pasted_jd or (job_ctx.get("description", "") if job_ctx else ""),
    "source": "manual",
}

st.markdown("---")

# ── Quick Access row ─────────────────────────────────────────────
st.markdown("<div class='section-tag'>Quick Access</div>", unsafe_allow_html=True)
_qa_cols = st.columns(5)
_QA_TOOLS = [
    ("_ats",            "🔍 ATS Scanner",       None),
    ("cover_letter",    "✉️ Cover Letter",       None),
    ("_offer_compare",  "📊 Offer Comparison",  None),
    ("_search_strategy","🧭 Job Strategy",       None),
    ("thank_you",       "🙏 Thank-You Note",     None),
]
for _col, (_key, _label, _) in zip(_qa_cols, _QA_TOOLS):
    _active = st.session_state.get("ws_selected") == _key
    if _col.button(_label, key=f"qa_{_key}", use_container_width=True,
                   type="primary" if _active else "secondary"):
        st.session_state.ws_selected = _key
        st.session_state.pop("ws_output", None)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
st.markdown("---")

col_menu, col_output = st.columns([1, 2], gap="large")

with col_menu:
    st.markdown("<div class='section-tag'>All Tools</div>", unsafe_allow_html=True)
    if st.button("ATS Resume Scanner", use_container_width=True, key="menu_ats"):
        st.session_state.ws_selected = "_ats"

    st.markdown("<div class='section-tag'>Strategic</div>", unsafe_allow_html=True)
    if st.button("📊 Offer Comparison", use_container_width=True, key="menu_oc"):
        st.session_state.ws_selected = "_offer_compare"
        st.session_state.pop("ws_output", None)
    if st.button("🧭 Job Search Strategy", use_container_width=True, key="menu_ss"):
        st.session_state.ws_selected = "_search_strategy"
        st.session_state.pop("ws_output", None)

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    st.markdown("<div class='section-tag'>Application Essays</div>", unsafe_allow_html=True)
    essay_prompts = {k: v for k, v in PROMPT_CATALOG.items() if v["category"] == "Application Essays"}
    essay_keys    = list(essay_prompts.keys())
    essay_labels  = [essay_prompts[k]["label"] for k in essay_keys]
    if essay_keys:
        sel_essay_idx = st.selectbox(
            "Pick a question",
            range(len(essay_keys)),
            format_func=lambda i: essay_labels[i],
            key="ws_essay_dd",
            label_visibility="collapsed",
        )
        if st.button("Load Essay Tool", use_container_width=True, key="ws_essay_load"):
            st.session_state.ws_selected = essay_keys[sel_essay_idx]
            st.session_state.pop("ws_output", None)

    for cat in ["Emails", "Profile"]:
        st.markdown(f"<div class='section-tag'>{cat}</div>", unsafe_allow_html=True)
        cat_prompts = {k: v for k, v in PROMPT_CATALOG.items() if v["category"] == cat}
        for key, meta in cat_prompts.items():
            active = st.session_state.get("ws_selected") == key
            if st.button(meta["label"], key=f"ws_btn_{key}", use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.ws_selected = key
                st.session_state.pop("ws_output", None)

with col_output:
    selected = st.session_state.get("ws_selected")

    if not selected:
        st.markdown(
            "<div class='card' style='text-align:center;padding:48px 24px'>"
            "<div style='font-size:2.5rem;margin-bottom:12px'>✍️</div>"
            "<div style='font-weight:700;font-size:1.1rem;margin-bottom:8px'>Select a writing tool</div>"
            "<div style='color:#64748b;font-size:13px'>Choose from the menu on the left.<br>"
            "Add job context above for more tailored output.</div>"
            "</div>", unsafe_allow_html=True
        )

    elif selected == "_offer_compare":
        from claude_ai import compare_offers_claude
        st.markdown("### 📊 Offer Comparison")
        st.caption("Enter 2-4 offers — Claude gives a direct recommendation and negotiation tips.")
        n_offers = st.number_input("How many offers?", min_value=2, max_value=4, value=2, step=1, key="oc_n")
        offers_input = []
        for oi in range(int(n_offers)):
            st.markdown(f"**Offer {oi+1}**")
            oc1, oc2 = st.columns(2)
            co_nm = oc1.text_input("Company",      key=f"oc_co_{oi}",  placeholder="e.g. Google")
            ro_nm = oc2.text_input("Role",          key=f"oc_ro_{oi}",  placeholder="e.g. Senior Engineer")
            oc3, oc4 = st.columns(2)
            sal   = oc3.text_input("Base salary",   key=f"oc_sal_{oi}", placeholder="e.g. $145,000")
            eq    = oc4.text_input("Equity/bonus",  key=f"oc_eq_{oi}",  placeholder="e.g. $40K RSU/yr")
            bens  = st.text_input("Benefits",       key=f"oc_ben_{oi}", placeholder="e.g. 4% 401k match, unlimited PTO, remote")
            notes = st.text_input("Notes",          key=f"oc_nt_{oi}",  placeholder="e.g. 6-month cliff, on-site 3 days/week")
            offers_input.append({"company": co_nm, "role": ro_nm, "salary": sal, "equity": eq, "benefits": bens, "notes": notes})
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        if st.button("Compare Offers", type="primary", key="oc_btn"):
            filled = [o for o in offers_input if o["company"] and o["salary"]]
            if len(filled) < 2:
                st.error("Enter at least 2 offers with company and salary.")
            else:
                with st.spinner("Claude is analyzing your offers…"):
                    oc_result = compare_offers_claude(filled, profile)
                st.session_state.ws_output = ("_offer_compare", oc_result)

        if st.session_state.get("ws_output") and st.session_state.ws_output[0] == "_offer_compare":
            oc_res = st.session_state.ws_output[1]
            if oc_res and isinstance(oc_res, dict):
                st.markdown("---")
                st.markdown(
                    f"<div class='card' style='border-left:4px solid #059669;margin-bottom:12px'>"
                    f"<div style='font-size:11px;font-weight:700;color:#059669;margin-bottom:6px'>🏆 RECOMMENDATION</div>"
                    f"<div style='font-size:14px;color:#0f172a;line-height:1.6'>{oc_res.get('recommendation', '')}</div>"
                    f"</div>", unsafe_allow_html=True
                )
                breakdown = oc_res.get("breakdown", [])
                if breakdown:
                    cols = st.columns(len(breakdown))
                    for bi, bd in enumerate(breakdown):
                        with cols[bi]:
                            st.markdown(f"**{bd.get('company', f'Offer {bi+1}')}**")
                            for p in bd.get("pros", []):
                                st.markdown(f"<div style='font-size:12px;color:#059669;padding:2px 0'>✅ {p}</div>", unsafe_allow_html=True)
                            for c in bd.get("cons", []):
                                st.markdown(f"<div style='font-size:12px;color:#dc2626;padding:2px 0'>❌ {c}</div>", unsafe_allow_html=True)
                            if bd.get("total_comp_note"):
                                st.caption(bd["total_comp_note"])
                if oc_res.get("negotiation_tips"):
                    st.markdown("**💰 Negotiation tips (regardless of which you choose):**")
                    for tip in oc_res["negotiation_tips"]:
                        st.markdown(f"• {tip}")
            else:
                st.error("Could not generate comparison. Check that Claude API is configured.")

    elif selected == "_search_strategy":
        from claude_ai import job_search_strategy_claude
        st.markdown("### 🧭 Job Search Strategy")
        st.caption("Claude reviews your resume and application history and gives specific strategic advice — not generic tips.")
        if st.button("Get My Strategy", type="primary", key="ss_btn"):
            all_apps = tracker.get_all(st.session_state.get("active_user_id", 1))
            with st.spinner("Claude is analyzing your search…"):
                ss_result = job_search_strategy_claude(profile, all_apps)
            st.session_state.ws_output = ("_search_strategy", ss_result)

        if st.session_state.get("ws_output") and st.session_state.ws_output[0] == "_search_strategy":
            ss_res = st.session_state.ws_output[1]
            if ss_res:
                st.markdown("---")
                st.markdown("<div class='section-tag'>Your Personalized Strategy</div>", unsafe_allow_html=True)
                for para in ss_res.strip().split("\n\n"):
                    if para.strip():
                        st.markdown(f"<div style='font-size:14px;color:#0f172a;line-height:1.7;margin-bottom:16px'>{para.strip()}</div>", unsafe_allow_html=True)
                st.markdown(alert("🔁 <b>Tip:</b> Re-run this after every 10 applications — strategy should evolve as you get more data.", "blue"), unsafe_allow_html=True)
                from pdf_export import writing_output_pdf
                ss_pdf = writing_output_pdf("Job Search Strategy", ss_res, name=profile.get("name", ""))
                st.download_button("⬇ Download Strategy PDF", data=ss_pdf, file_name="CareerIQ_Strategy.pdf", mime="application/pdf")
            else:
                st.error("Could not generate strategy. Check that Claude API is configured.")

    elif selected == "_ats":
        st.markdown("### ATS Resume Scanner")
        st.caption("See exactly how your resume scores against a job description")
        if st.button("Run Scan", type="primary"):
            if not job["description"]:
                st.error("Paste a job description in the context box above.")
            else:
                with st.spinner("Scanning…"):
                    r = ats_scan(profile["raw_text"], job["description"])
                st.session_state.ws_output = ("_ats", r)

        if st.session_state.get("ws_output") and st.session_state.ws_output[0] == "_ats":
            r  = st.session_state.ws_output[1]
            vc = {"strong": "#059669", "medium": "#d97706", "weak": "#dc2626"}[r["verdict"][0]]
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"<div style='text-align:center'>{score_badge(r['score'], 60)}<div style='font-size:11px;color:#64748b;margin-top:4px'>ATS Score</div></div>", unsafe_allow_html=True)
            c2.metric("Keyword Match",  f"{r['keyword_score']}%")
            c3.metric("Semantic Match", f"{r['semantic_score']}%")
            st.markdown(alert(r["verdict"][1], "green" if r["verdict"][0] == "strong" else "amber" if r["verdict"][0] == "medium" else "red"), unsafe_allow_html=True)
            cf, cm = st.columns(2)
            with cf:
                st.markdown("**✅ Keywords found**")
                st.markdown(" ".join(chip(s, "green") for s in r["found_keywords"]) or "*None*", unsafe_allow_html=True)
            with cm:
                st.markdown("**🔴 Keywords missing**")
                st.markdown(" ".join(chip(s, "red") for s in r["missing_keywords"]) or "✅ None!", unsafe_allow_html=True)
            if r.get("extra_missing"):
                st.markdown("**🟡 Other JD terms not in resume**")
                st.markdown(" ".join(chip(w, "gray") for w in r["extra_missing"]), unsafe_allow_html=True)
            if r["suggested_bullets"]:
                st.markdown("---")
                st.markdown("**✏️ Suggested Bullets**")
                for item in r["suggested_bullets"]:
                    st.markdown(f"<div class='card-amber'><span style='font-size:11px;font-weight:700;color:#92400e'>ADD: {item['keyword'].upper()}</span><br>• {item['suggested_bullet']}</div>", unsafe_allow_html=True)
            with st.expander("Formatting tips"):
                for tip in r["formatting_tips"]:
                    st.markdown(f"• {tip}")

    else:
        meta = PROMPT_CATALOG.get(selected, {})
        st.markdown(f"### {meta.get('label', 'Generate')}")
        placeholder = meta.get("placeholder", "")
        extra_ctx = st.text_area(
            "Additional context (optional)",
            height=80,
            placeholder=placeholder or "Any specific details to include…",
            key=f"extra_{selected}",
            label_visibility="visible" if placeholder else "collapsed",
        )
        col_gen, col_clear = st.columns([1, 1])
        with col_gen:
            if st.button("Generate", type="primary", use_container_width=True):
                with st.spinner("Writing…"):
                    title, body = generate(selected, profile, job, extra_ctx)
                st.session_state.ws_output = (selected, title, body)
        with col_clear:
            if st.button("Clear", use_container_width=True):
                st.session_state.pop("ws_output", None)
                st.rerun()

        if st.session_state.get("ws_output") and st.session_state.ws_output[0] == selected:
            _, out_title, out_body = st.session_state.ws_output
            wc = len(out_body.split())
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-top:12px'>"
                f"<span style='font-size:12px;color:#64748b'>{wc} words</span>"
                f"<span style='font-size:12px;color:{'#059669' if 150 <= wc <= 500 else '#d97706'}'>"
                f"{'✓ Good length' if 150 <= wc <= 500 else 'Consider trimming' if wc > 500 else 'Could be longer'}</span>"
                f"</div>", unsafe_allow_html=True
            )
            edited = st.text_area("Edit before using", value=out_body, height=420, label_visibility="collapsed", key=f"edit_{selected}")
            dl_col, tip_col = st.columns([1, 3])
            with dl_col:
                from pdf_export import writing_output_pdf
                safe_title = re.sub(r"[^\w\s-]", "", out_title)[:40].strip().replace(" ", "_")
                pdf_bytes  = writing_output_pdf(
                    out_title, edited,
                    name=profile.get("name", ""),
                    job_title=job.get("title", ""),
                    company=job.get("company", ""),
                )
                st.download_button(
                    "⬇ Download PDF", data=pdf_bytes,
                    file_name=f"CareerIQ_{safe_title}.pdf",
                    mime="application/pdf", use_container_width=True,
                )
            with tip_col:
                st.markdown(alert("Select all → Copy → Paste into your application, or download as PDF.", "blue"), unsafe_allow_html=True)

