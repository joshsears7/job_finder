import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, score_color, progress_bar, score_badge, xe
from linkedin_editor import (
    generate_headlines, generate_about, rewrite_bullets_for_linkedin,
    skills_to_add, generate_connection_request, generate_cold_dm,
    analyze_profile, generate_salary_negotiation,
)
from claude_ai import stream_about_claude

inject_css()

st.markdown("<div class='page-title'>LinkedIn Optimizer</div><div class='page-sub'>Generate headlines, About sections, cold DMs, and salary scripts — all tailored to your resume. Profile Score is optional.</div>", unsafe_allow_html=True)

profile = st.session_state.get("resume")
if not profile:
    st.markdown(alert("Upload your resume on the Dashboard first — all outputs are tailored to your background.", "blue"), unsafe_allow_html=True)
    st.stop()

tab_headlines, tab_about, tab_msgs, tab_negotiate, tab_skills, tab_score = st.tabs([
    "Headlines", "About Section", "Messages", "Salary Negotiation", "Skills to Add", "Profile Score ↗"
])

# ── Profile Score (moved to last — requires pasting profile text) ──
with tab_score:
    st.markdown("<div class='section-tag'>Paste your LinkedIn profile text</div>", unsafe_allow_html=True)
    st.caption("On LinkedIn → go to your profile → select all text (Cmd+A) → copy (Cmd+C) → paste below. The other tabs don't require this.")

    pasted = st.text_area("LinkedIn profile text", height=260, placeholder="Paste your full LinkedIn profile text here…", label_visibility="collapsed")
    c1, c2, c3 = st.columns([1.5, 1.5, 1])
    target_role_score = c1.text_input("Target role (optional)", placeholder="e.g. Business Analyst", key="li_score_role")
    has_photo         = c2.checkbox("I have a profile photo", value=True)
    conn_count        = c3.number_input("Connections", min_value=0, max_value=30000, value=0, step=50, key="li_conn")

    if st.button("Analyze Profile", type="primary", key="li_analyze") and pasted.strip():
        with st.spinner("Scoring your LinkedIn profile…"):
            result = analyze_profile(pasted, target_role_score, has_photo, conn_count)
            st.session_state["li_score_result"] = result

    result = st.session_state.get("li_score_result")
    if result:
        sc = result["overall_score"]
        grade = result["grade"]
        asd = result["all_star_done"]
        is_all_star = result["is_all_star"]

        m1, m2, m3 = st.columns(3)
        sc_color = score_color(sc)
        m1.markdown(
            f"<div class='card' style='text-align:center'>"
            f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Profile Score</div>"
            f"<div style='margin-top:8px'>{score_badge(sc, 56)}</div>"
            f"<div style='font-size:22px;font-weight:900;color:#f1f5f9;margin-top:6px'>Grade {grade}</div>"
            f"</div>", unsafe_allow_html=True
        )
        m2.markdown(
            f"<div class='card' style='text-align:center'>"
            f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>All-Star Status</div>"
            f"<div style='font-size:38px;font-weight:900;color:{'#10b981' if is_all_star else '#f59e0b'};margin-top:8px'>{'✅' if is_all_star else f'{asd}/10'}</div>"
            f"<div style='font-size:12px;color:#64748b'>{'All-Star achieved!' if is_all_star else 'items complete'}</div>"
            f"</div>", unsafe_allow_html=True
        )
        m3.markdown(
            f"<div class='card' style='text-align:center'>"
            f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase'>Word Count</div>"
            f"<div style='font-size:38px;font-weight:900;color:#3b82f6;margin-top:8px'>{result['word_count']}</div>"
            f"<div style='font-size:12px;color:#64748b'>{'good length' if result['word_count'] >= 200 else 'expand your profile'}</div>"
            f"</div>", unsafe_allow_html=True
        )

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("<div class='section-tag' style='margin-top:14px'>Section Scores</div>", unsafe_allow_html=True)
            for sec_name, sec_data in result["sections"].items():
                s = sec_data["score"]
                bar_col = score_color(s)
                issues_html = "".join(f"<div style='font-size:12px;color:#fca5a5;margin-top:2px'>⚠ {xe(i)}</div>" for i in sec_data["issues"][:1])
                tip_html    = "".join(f"<div style='font-size:12px;color:#93c5fd;margin-top:2px'>💡 {xe(t)}</div>" for t in sec_data["tips"][:1])
                st.markdown(
                    f"<div style='margin-bottom:10px'>"
                    f"<div style='display:flex;justify-content:space-between'>"
                    f"<span style='font-weight:600;color:#e2e8f0;font-size:13px'>{xe(sec_name)}</span>"
                    f"<span style='font-size:12px;font-weight:700;color:{bar_col}'>{s}%</span></div>"
                    f"{progress_bar(s, bar_col)}{issues_html}{tip_html}</div>",
                    unsafe_allow_html=True
                )

        with col_r:
            st.markdown("<div class='section-tag' style='margin-top:14px'>All-Star Checklist</div>", unsafe_allow_html=True)
            for item in result["all_star_checklist"]:
                icon = "✅" if item["done"] else "⬜"
                color = "#86efac" if item["done"] else "#94a3b8"
                st.markdown(f"<div style='font-size:13px;color:{color};margin-bottom:5px'>{icon} {xe(item['item'])}</div>", unsafe_allow_html=True)

            if result["top_recommendations"]:
                st.markdown("<div class='section-tag' style='margin-top:14px'>Top Recommendations</div>", unsafe_allow_html=True)
                for rec in result["top_recommendations"]:
                    st.markdown(alert(rec, "blue"), unsafe_allow_html=True)

# ── Headlines ────────────────────────────────────────────────────
with tab_headlines:
    st.markdown("<div class='section-tag'>Generate LinkedIn Headlines</div>", unsafe_allow_html=True)
    st.caption("LinkedIn shows your headline in recruiter search results. It's your #1 searchability lever.")

    if not profile:
        st.markdown(alert("Upload your resume on the Dashboard first — headlines are tailored to your skills and background.", "blue"), unsafe_allow_html=True)
    else:
        tr_hl = st.text_input("Target role", value=profile.get("titles", [""])[0] if profile.get("titles") else "", placeholder="e.g. Marketing Analyst", key="li_hl_role")
        if st.button("Generate Headlines", type="primary", key="li_gen_hl"):
            with st.spinner("Generating headlines…"):
                headlines = generate_headlines(profile, tr_hl)
                st.session_state["li_headlines"] = headlines

        headlines = st.session_state.get("li_headlines", [])
        for i, h in enumerate(headlines):
            st.markdown(
                f"<div class='card' style='padding:16px 20px'>"
                f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;margin-bottom:8px'>Option {i+1}</div>"
                f"<div style='font-size:15px;font-weight:600;color:#e2e8f0'>{xe(h)}</div>"
                f"<div style='font-size:11px;color:#475569;margin-top:6px'>{len(h)}/220 characters</div>"
                f"</div>", unsafe_allow_html=True
            )
            st.code(h, language=None)

# ── About Section ─────────────────────────────────────────────────
with tab_about:
    st.markdown("<div class='section-tag'>Generate LinkedIn About Section</div>", unsafe_allow_html=True)
    st.caption("A strong About section shows up in recruiter keyword searches and converts profile views into connection requests.")

    if not profile:
        st.markdown(alert("Upload your resume on the Dashboard first.", "blue"), unsafe_allow_html=True)
    else:
        c_ab1, c_ab2 = st.columns(2)
        tr_ab = c_ab1.text_input("Target role", value=profile.get("titles", [""])[0] if profile.get("titles") else "", placeholder="e.g. Data Analyst", key="li_ab_role")

        col_abt, col_bullets = st.tabs(["About Section", "Rewrite Bullets for LinkedIn"])

        with col_abt:
            ab_c1, ab_c2 = st.columns([3, 1])
            with ab_c2:
                if st.button("⚡ Stream with Sonnet", key="li_gen_about_stream"):
                    st.session_state.pop("li_about", None)
            with ab_c1:
                gen_about_btn = st.button("Generate About Section", type="primary", key="li_gen_about")

            if gen_about_btn:
                st.session_state.pop("li_about", None)

            about = st.session_state.get("li_about", "")

            if gen_about_btn or (not about and st.session_state.get("li_about") is None and
                                  st.session_state.get("li_gen_about_stream")):
                st.caption("Claude Sonnet is writing your About section…")
                streamed = st.write_stream(stream_about_claude(profile, tr_ab))
                st.session_state["li_about"] = streamed
                about = streamed
                st.rerun()

            if about:
                st.text_area("Generated About section (copy to LinkedIn)", value=about, height=380, key="li_about_display")
                st.caption(f"{len(about)} characters — LinkedIn About supports up to 2,600.")
                # Quality eval
                try:
                    from eval_engine import evaluate
                    ev = evaluate(about, "linkedin_about", resume_text=profile.get("raw_text",""), persist=True)
                    grade_color = {"A":"#10b981","B":"#3b82f6","C":"#f59e0b","D":"#f97316","F":"#ef4444"}.get(ev["grade"],"#64748b")
                    st.markdown(
                        f"<div style='display:flex;gap:16px;align-items:center;margin-top:8px'>"
                        f"<span style='font-size:11px;color:#64748b'>Quality:</span>"
                        f"<span style='font-size:13px;font-weight:900;color:{grade_color}'>Grade {ev['grade']} ({ev['overall']}%)</span>"
                        f"<span style='font-size:11px;color:#64748b'>Grounding: {ev['grounding']}% · Specificity: {ev['specificity']}%</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                    for flag in ev.get("flags", []):
                        st.caption(f"⚠ {flag}")
                except Exception:
                    pass

        with col_bullets:
            st.caption("LinkedIn bullets should be shorter and more achievement-focused than resume bullets.")
            raw_bullets = profile.get("raw_text", "")
            bullets = [b.strip().lstrip("•·-* ") for b in raw_bullets.split("\n") if len(b.strip()) > 30 and b.strip()[0] in "•·-*ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"][:12]

            if st.button("Rewrite My Bullets for LinkedIn", key="li_rewrite_bullets"):
                with st.spinner("Rewriting…"):
                    rewritten = rewrite_bullets_for_linkedin(bullets)
                    st.session_state["li_rewritten_bullets"] = rewritten

            rewritten = st.session_state.get("li_rewritten_bullets", [])
            if rewritten:
                for b in rewritten:
                    st.markdown(
                        f"<div class='card-slate' style='padding:12px 16px'>"
                        f"<span style='color:#93c5fd;font-size:13px'>→ {xe(b)}</span>"
                        f"</div>", unsafe_allow_html=True
                    )

# ── Skills to Add ─────────────────────────────────────────────────
with tab_skills:
    st.markdown("<div class='section-tag'>Skills to Add to Your LinkedIn</div>", unsafe_allow_html=True)
    st.caption("LinkedIn's algorithm ranks profiles with 5+ skills higher in recruiter searches. These are the skills recruiters filter on for your target role.")

    if not profile:
        st.markdown(alert("Upload your resume on the Dashboard first.", "blue"), unsafe_allow_html=True)
    else:
        tr_sk = st.text_input("Target role", placeholder="e.g. Product Manager", key="li_sk_role")
        if st.button("Get Skills to Add", type="primary", key="li_gen_skills"):
            missing = skills_to_add(profile, tr_sk)
            st.session_state["li_missing_skills"] = missing

        missing = st.session_state.get("li_missing_skills")
        if missing is not None:
            if missing:
                st.markdown("<div style='margin-top:12px'>Add these to your LinkedIn Skills section:</div>", unsafe_allow_html=True)
                st.markdown(" ".join(chip(s, "blue") for s in missing), unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                st.info("💡 Take the LinkedIn Skill Assessments for SQL, Excel, or Python — passing adds a verified badge and boosts your search ranking.")
            else:
                st.markdown(alert("Your profile already has the top skills for this role. Consider taking LinkedIn Skill Assessments to get verification badges.", "green"), unsafe_allow_html=True)

        if profile.get("skills"):
            st.markdown("<div class='section-tag' style='margin-top:16px'>Skills Already on Your Resume</div>", unsafe_allow_html=True)
            st.markdown(" ".join(chip(s, "green") for s in profile["skills"]), unsafe_allow_html=True)

# ── Messages ──────────────────────────────────────────────────────
with tab_msgs:
    msg_tab1, msg_tab2 = st.tabs(["Connection Request", "Cold DM / Cold Email"])

    with msg_tab1:
        st.markdown("<div class='section-tag'>Connection Request (< 300 characters)</div>", unsafe_allow_html=True)
        st.caption("Short, genuine, no pitch. Mention something specific — why them, why now.")
        c_cr1, c_cr2 = st.columns(2)
        cr_name    = c_cr1.text_input("Their name", placeholder="Sarah Johnson", key="cr_name")
        cr_company = c_cr2.text_input("Their company", placeholder="Goldman Sachs", key="cr_company")
        cr_context = st.text_input("Context (optional)", placeholder="Found you through X posting, alumni network, etc.", key="cr_context")
        cr_my_role = st.text_input("Your role/goal", placeholder="e.g. aspiring data analyst", key="cr_my_role")

        if st.button("Generate Connection Requests", type="primary", key="gen_cr"):
            variants = generate_connection_request(cr_name, cr_company, cr_context, cr_my_role)
            st.session_state["li_cr_variants"] = variants

        for i, v in enumerate(st.session_state.get("li_cr_variants", [])):
            st.markdown(
                f"<div class='card' style='padding:14px 18px'>"
                f"<div style='font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;margin-bottom:8px'>Option {i+1} · {len(v)}/300 chars</div>"
                f"<div style='font-size:13.5px;color:#e2e8f0;line-height:1.6'>{xe(v)}</div>"
                f"</div>", unsafe_allow_html=True
            )

    with msg_tab2:
        st.markdown("<div class='section-tag'>Cold DM / Cold Email to Recruiter or Hiring Manager</div>", unsafe_allow_html=True)
        if not profile:
            st.markdown(alert("Upload your resume first — the DM is tailored to your background.", "blue"), unsafe_allow_html=True)
        else:
            c_dm1, c_dm2 = st.columns(2)
            dm_name    = c_dm1.text_input("Their name", placeholder="Mike Chen", key="dm_name")
            dm_company = c_dm2.text_input("Their company", placeholder="Stripe", key="dm_company")
            dm_role_co = c_dm1.text_input("Their role at company", placeholder="Senior Recruiter", key="dm_role_co")
            dm_job     = c_dm2.text_input("Job you're targeting", placeholder="Business Analyst Intern", key="dm_job")

            if st.button("Generate Cold DM", type="primary", key="gen_dm"):
                with st.spinner("Drafting your message…"):
                    dm = generate_cold_dm(profile, dm_name, dm_company, dm_role_co, dm_job)
                    st.session_state["li_cold_dm"] = dm

            dm_text = st.session_state.get("li_cold_dm", "")
            if dm_text:
                st.text_area("Cold DM (edit before sending)", value=dm_text, height=320, key="li_dm_display")
                st.caption("Fill in the [bracketed] placeholders before sending. Keep it under 300 words.")

# ── Salary Negotiation ────────────────────────────────────────────
with tab_negotiate:
    st.markdown("<div class='section-tag'>Salary Negotiation Scripts</div>", unsafe_allow_html=True)
    st.caption("85% of employers have room to negotiate. Most people never ask.")

    if not profile:
        name_neg = st.text_input("Your name", placeholder="Josh Sears", key="neg_name_noprofile")
    else:
        name_neg = profile.get("name", "")

    c_n1, c_n2, c_n3 = st.columns(3)
    offer_amt  = c_n1.number_input("Current offer ($)", min_value=0, max_value=500000, value=65000, step=1000, key="neg_offer")
    target_amt = c_n2.number_input("Your target ($)", min_value=0, max_value=500000, value=75000, step=1000, key="neg_target")
    neg_co     = c_n3.text_input("Company", placeholder="Goldman Sachs", key="neg_company")
    neg_role   = st.text_input("Role title", placeholder="Business Analyst", key="neg_role")

    if st.button("Generate Negotiation Scripts", type="primary", key="gen_neg"):
        if offer_amt > 0 and target_amt > offer_amt:
            with st.spinner("Building your negotiation playbook…"):
                scripts = generate_salary_negotiation(offer_amt, target_amt, neg_co, neg_role, name_neg)
                st.session_state["li_neg_scripts"] = scripts
        else:
            st.error("Target must be greater than offer.")

    scripts = st.session_state.get("li_neg_scripts")
    if scripts:
        gap = scripts["gap_pct"]
        mid = scripts["mid"]
        st.markdown(
            f"<div class='card-blue' style='margin-bottom:16px'>"
            f"<b>Gap: {gap}% above offer</b> · Midpoint: ${mid:,} · "
            f"{'Well within normal range (under 20%)' if gap <= 20 else 'Significant ask — prepare strong justification'}"
            f"</div>", unsafe_allow_html=True
        )

        with st.expander("📞 Opening Script (in-person / phone)", expanded=True):
            st.text_area("Opening", value=scripts["opening"], height=180, key="neg_opening_display")

        with st.expander("✉️ Counter-Offer Email"):
            st.text_area("Counter email", value=scripts["counter_email"], height=260, key="neg_email_display")

        with st.expander("🎯 Verbal Script (exact words to say)"):
            st.text_area("Verbal script", value=scripts["verbal_script"], height=220, key="neg_verbal_display")

        with st.expander("💡 Negotiation Tips"):
            for tip in scripts["notes"]:
                st.markdown(f"<div style='color:#93c5fd;font-size:13px;margin-bottom:6px'>• {xe(tip)}</div>", unsafe_allow_html=True)
