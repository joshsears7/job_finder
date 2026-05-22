import streamlit as st
from dotenv import load_dotenv
load_dotenv()

from utils import inject_css, alert, chip, xe
from ai_tools import generate_interview_questions
import tracker

inject_css()

st.markdown("<div class='page-title'>Interview Prep</div><div class='page-sub'>Tailored question banks, STAR story builder, salary coaching, and smart questions to ask your interviewer.</div>", unsafe_allow_html=True)

profile = st.session_state.get("resume")
if not profile:
    st.markdown(alert("Upload your resume on the Dashboard first — questions are tailored to your background.", "blue"), unsafe_allow_html=True)
    st.stop()

tab_qs, tab_star, tab_salary, tab_ask, tab_debrief = st.tabs([
    "Question Bank", "STAR Story Builder", "Salary Coach", "Questions to Ask", "Post-Interview"
])

# ── Question Bank ─────────────────────────────────────────────────
with tab_qs:
    st.markdown("<div class='section-tag'>Job Context</div>", unsafe_allow_html=True)

    all_saved  = tracker.get_all(st.session_state.get("active_user_id", 1))
    job_list   = [(a["title"], a["company"], a.get("url",""), "") for a in all_saved if a["status"] in ("applied","interview","saved")]
    searched   = st.session_state.get("jobs", [])
    for j in searched:
        job_list.append((j["title"], j["company"], j.get("url",""), j.get("description","")))

    use_saved = st.checkbox("Use a saved/applied job for context", value=bool(job_list), key="iq_use_saved")
    job_ctx = None
    if use_saved and job_list:
        labels = [f"{t} @ {c}" for t, c, u, d in job_list]
        idx = st.selectbox("Select job", range(len(labels)), format_func=lambda i: labels[i], key="iq_job_sel", label_visibility="collapsed")
        t, c, u, d = job_list[idx]
        job_ctx = {"title": t, "company": c, "url": u, "description": d}

    c1, c2 = st.columns(2)
    manual_title   = c1.text_input("Job title",   value=job_ctx["title"]   if job_ctx else "", placeholder="e.g. Marketing Analyst Intern", key="iq_title")
    manual_company = c2.text_input("Company",     value=job_ctx["company"] if job_ctx else "", placeholder="e.g. Deloitte", key="iq_company")
    jd_paste = st.text_area("Paste job description (optional — improves question relevance)", value=job_ctx.get("description","") if job_ctx else "", height=100, key="iq_jd")

    job = {
        "title":       manual_title   or (job_ctx["title"]   if job_ctx else "this role"),
        "company":     manual_company or (job_ctx["company"] if job_ctx else "the company"),
        "description": jd_paste       or (job_ctx.get("description","") if job_ctx else ""),
    }

    if st.button("Generate Question Bank", type="primary", key="gen_qs"):
        with st.spinner("Building tailored question bank — loading AI model on first run (30–60 s)…"):
            qs = generate_interview_questions(profile, job)
            st.session_state["interview_qs"] = qs

    qs = st.session_state.get("interview_qs", [])
    if qs:
        try:
            from pdf_export import interview_pdf as _ipdf
            _pdf_bytes = _ipdf(
                qs,
                job_title=manual_title or (job_ctx["title"] if job_ctx else ""),
                company=manual_company or (job_ctx["company"] if job_ctx else ""),
                name=profile.get("name", "") if profile else "",
            )
            safe_co = (manual_company or (job_ctx["company"] if job_ctx else "questions")).replace(" ", "_")[:20]
            st.download_button(
                "⬇ Download Question Bank PDF",
                data=_pdf_bytes,
                file_name=f"interview_questions_{safe_co}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception:
            pass
        type_order = ["Technical", "Role-Specific", "Behavioral", "Situational", "Closing"]
        grouped = {}
        for q in qs:
            t = q.get("type", "General")
            grouped.setdefault(t, []).append(q)

        type_colors = {
            "Technical":     "#3b82f6",
            "Role-Specific": "#8b5cf6",
            "Behavioral":    "#10b981",
            "Situational":   "#f59e0b",
            "Closing":       "#64748b",
        }

        for qtype in type_order:
            if qtype not in grouped:
                continue
            color = type_colors.get(qtype, "#64748b")
            st.markdown(
                f"<div style='font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.08em;"
                f"color:{color};margin:20px 0 8px'>── {qtype} ──</div>",
                unsafe_allow_html=True
            )
            for item in grouped[qtype]:
                with st.expander(item["question"]):
                    st.markdown(
                        f"<div style='background:#0d1424;border-left:3px solid {color};padding:12px 16px;"
                        f"border-radius:0 8px 8px 0;font-size:13px;color:#93c5fd;line-height:1.65'>"
                        f"💡 {xe(item['hint'])}</div>",
                        unsafe_allow_html=True
                    )

        # Also show remaining types not in type_order
        for qtype, items in grouped.items():
            if qtype in type_order:
                continue
            st.markdown(f"<div style='font-size:11px;font-weight:800;text-transform:uppercase;color:#64748b;margin:16px 0 8px'>── {xe(qtype)} ──</div>", unsafe_allow_html=True)
            for item in items:
                with st.expander(item["question"]):
                    st.markdown(f"<div style='font-size:13px;color:#93c5fd;line-height:1.65'>💡 {xe(item['hint'])}</div>", unsafe_allow_html=True)

        # ── STAR story connector ──────────────────────────────────
        stories = st.session_state.get("star_stories", [])
        behavioral_qs = grouped.get("Behavioral", [])
        if stories and behavioral_qs:
            st.markdown("---")
            st.markdown(
                "<div style='font-size:11px;font-weight:800;text-transform:uppercase;"
                "color:#10b981;margin:4px 0 10px;letter-spacing:.07em'>── Your STAR Stories — matched to these questions ──</div>",
                unsafe_allow_html=True
            )
            for bq in behavioral_qs:
                q_text = bq["question"].lower()
                # Simple keyword theme matching — no model needed
                _THEMES = {
                    "analyz": ["data", "analyz", "report", "dashboard", "metrics", "insights"],
                    "lead":   ["led", "lead", "team", "manag", "coordinat", "captain"],
                    "adapt":  ["adapt", "change", "new", "challenge", "pivot", "unexpected"],
                    "initiat":["initiat", "propos", "built", "created", "started", "without being asked"],
                    "communic":["present", "communic", "explain", "stakeholder", "non-technical"],
                }
                best_match, best_score = None, 0
                for story in stories:
                    s_text = f"{story.get('title','')} {story.get('action','')} {story.get('result','')}".lower()
                    sc = 0
                    for theme_kws in _THEMES.values():
                        q_hits = sum(1 for kw in theme_kws if kw in q_text)
                        s_hits = sum(1 for kw in theme_kws if kw in s_text)
                        if q_hits > 0 and s_hits > 0:
                            sc += q_hits + s_hits
                    if sc > best_score:
                        best_score, best_match = sc, story
                if best_match and best_score > 0:
                    st.markdown(
                        f"<div style='border:1px solid #166534;border-radius:8px;padding:10px 14px;"
                        f"margin-bottom:8px;background:#0f2a1a'>"
                        f"<div style='font-size:11px;font-weight:700;color:#10b981;text-transform:uppercase;"
                        f"letter-spacing:.05em;margin-bottom:4px'>Relevant STAR story for:</div>"
                        f"<div style='font-size:12.5px;color:#94a3b8;font-style:italic;margin-bottom:8px'>"
                        f"\"{xe(bq['question'][:100])}{'…' if len(bq['question'])>100 else ''}\"</div>"
                        f"<div style='font-size:13px;font-weight:700;color:#6ee7b7'>📖 {xe(best_match['title'])}</div>"
                        f"<div style='font-size:12px;color:#4ade80;margin-top:4px'>"
                        f"Action: {xe(best_match['action'][:100])}{'…' if len(best_match.get('action',''))>100 else ''}</div>"
                        f"<div style='font-size:12px;color:#4ade80'>"
                        f"Result: {xe(best_match['result'][:100])}{'…' if len(best_match.get('result',''))>100 else ''}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

# ── STAR Story Builder ────────────────────────────────────────────
with tab_star:
    st.markdown("<div class='section-tag'>Build Your STAR Stories</div>", unsafe_allow_html=True)
    st.caption("STAR = Situation · Task · Action · Result. Prepare 5–7 of these before any interview. They cover 80% of behavioral questions.")

    if "star_stories" not in st.session_state:
        try:
            import profile_store as _ps_star
            _uid_star = st.session_state.get("active_user_id", 1)
            st.session_state["star_stories"] = _ps_star.get_star_stories(_uid_star)
        except Exception:
            st.session_state["star_stories"] = []

    with st.expander("➕ Add a new STAR story", expanded=not bool(st.session_state["star_stories"])):
        story_title = st.text_input("Story title / theme", placeholder="e.g. Led a team project under deadline pressure", key="star_title")
        col_s, col_t = st.columns(2)
        situation = col_s.text_area("Situation", height=120, placeholder="Set the scene. What was the context? What was at stake?", key="star_situation")
        task      = col_t.text_area("Task", height=120, placeholder="What was your specific responsibility? What needed to happen?", key="star_task")
        col_a, col_r = st.columns(2)
        action = col_a.text_area("Action", height=120, placeholder="What did YOU specifically do? Use 'I', not 'we'. Be specific.", key="star_action")
        result = col_r.text_area("Result", height=120, placeholder="What was the outcome? Quantify if possible. What did you learn?", key="star_result")

        if st.button("Save Story", type="primary", key="star_save"):
            if story_title and situation and action and result:
                st.session_state["star_stories"].append({
                    "title": story_title,
                    "situation": situation,
                    "task": task,
                    "action": action,
                    "result": result,
                })
                try:
                    import profile_store as _ps_star
                    _ps_star.set_star_stories(
                        st.session_state["star_stories"],
                        st.session_state.get("active_user_id", 1),
                    )
                except Exception:
                    pass
                st.success(f"Story saved: '{story_title}'")
                st.rerun()
            else:
                st.error("Fill in at least Title, Situation, Action, and Result.")

    stories = st.session_state.get("star_stories", [])
    if stories:
        try:
            from pdf_export import star_stories_pdf as _spdf
            _star_pdf = _spdf(stories, name=profile.get("name", "") if profile else "")
            st.download_button(
                "⬇ Download All STAR Stories PDF",
                data=_star_pdf,
                file_name="star_stories.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception:
            pass
        st.markdown(f"<div class='section-tag' style='margin-top:16px'>Your Stories ({len(stories)})</div>", unsafe_allow_html=True)
        for i, s in enumerate(stories):
            with st.expander(f"📖 {s['title']}", expanded=False):
                st.markdown(
                    f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:8px'>"
                    f"<div><div style='font-size:10px;font-weight:800;color:#3b82f6;text-transform:uppercase;margin-bottom:4px'>Situation</div>"
                    f"<div style='font-size:13px;color:#cbd5e1;line-height:1.6'>{xe(s['situation'])}</div></div>"
                    f"<div><div style='font-size:10px;font-weight:800;color:#8b5cf6;text-transform:uppercase;margin-bottom:4px'>Task</div>"
                    f"<div style='font-size:13px;color:#cbd5e1;line-height:1.6'>{xe(s.get('task','—'))}</div></div>"
                    f"<div><div style='font-size:10px;font-weight:800;color:#10b981;text-transform:uppercase;margin-bottom:4px'>Action</div>"
                    f"<div style='font-size:13px;color:#cbd5e1;line-height:1.6'>{xe(s['action'])}</div></div>"
                    f"<div><div style='font-size:10px;font-weight:800;color:#f59e0b;text-transform:uppercase;margin-bottom:4px'>Result</div>"
                    f"<div style='font-size:13px;color:#cbd5e1;line-height:1.6'>{xe(s['result'])}</div></div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                if st.button("Delete", key=f"del_story_{i}"):
                    st.session_state["star_stories"].pop(i)
                    try:
                        import profile_store as _ps_star
                        _ps_star.set_star_stories(
                            st.session_state["star_stories"],
                            st.session_state.get("active_user_id", 1),
                        )
                    except Exception:
                        pass
                    st.rerun()
    else:
        st.markdown(alert("No stories yet. Add your first STAR story above.", "blue"), unsafe_allow_html=True)

# ── Salary Coach ──────────────────────────────────────────────────
with tab_salary:
    st.markdown("<div class='section-tag'>How to Handle 'What Are Your Salary Expectations?'</div>", unsafe_allow_html=True)

    st.markdown(
        "<div class='card-amber' style='margin-bottom:16px'>"
        "<b>Golden rule: Never give a number first.</b> The first person to name a number is at a disadvantage. "
        "Always ask them to share the range, or deflect until you have an offer."
        "</div>",
        unsafe_allow_html=True
    )

    scripts = [
        ("Early in the process (before you have any range)",
         "\"I'd love to learn more about the role before discussing compensation. Could you share the budgeted range for this position?\"",
         "This is almost always appropriate and puts the ball back in their court."),
        ("If they push for a number",
         "\"Based on my research for this role in this market, I'm targeting [range]. But I'm more focused on finding the right fit — is that in line with your budget?\"",
         "Give a range, not a specific number. The bottom of your range should be your actual minimum."),
        ("When you have an offer and want to negotiate",
         "\"Thank you so much for the offer — I'm genuinely excited about this role. After reviewing it carefully, I was hoping we could discuss the base salary. Based on market data and my background, I was targeting [higher number]. Is there flexibility there?\"",
         "Always express enthusiasm first. Never apologize for negotiating."),
        ("If they say 'the budget is fixed'",
         "\"I understand completely. If the base is set, would there be room to discuss a signing bonus, additional PTO, or an earlier performance review?\"",
         "Always have 3 asks ready: base, signing bonus, and one other (equity, remote days, PTO)."),
        ("The silence technique",
         "Make your ask, then stop talking. Don't fill the silence. The next person to speak loses leverage.",
         "This is the single most powerful thing you can do in a negotiation. Practice it."),
    ]

    for title, script, note in scripts:
        with st.expander(title):
            st.markdown(
                f"<div style='background:#0f1f4a;border:1px solid #1e3a8a;border-radius:10px;padding:14px 18px;margin-bottom:10px'>"
                f"<div style='font-size:14px;color:#bfdbfe;font-style:italic;line-height:1.7'>{xe(script)}</div>"
                f"</div>"
                f"<div style='font-size:12.5px;color:#64748b;line-height:1.6'>💡 {xe(note)}</div>",
                unsafe_allow_html=True
            )

    st.markdown("---")
    st.markdown("<div class='section-tag'>Answering 'What's Your Weakness?'</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='card' style='padding:18px 22px'>"
        "<div style='font-size:13px;color:#e2e8f0;line-height:1.7'>"
        "<b style='color:#f1f5f9'>Formula:</b> Real weakness → what you're doing about it → evidence of improvement.<br><br>"
        "<b style='color:#93c5fd'>Example:</b> \"Earlier in my career, I tended to take on too much without asking for help — I'd rather figure things out independently than seem uncertain. "
        "What I've learned is that asking the right questions early actually saves more time and produces better outcomes than working in isolation. "
        "In my last project, I proactively scheduled weekly check-ins with my manager to catch gaps early, and it made a real difference in how smoothly things ran.\""
        "<br><br>"
        "<b style='color:#fca5a5'>Never say:</b> 'I'm a perfectionist' or 'I work too hard' — every interviewer has heard it 500 times and it signals you didn't prepare."
        "</div></div>",
        unsafe_allow_html=True
    )

# ── Questions to Ask ──────────────────────────────────────────────
with tab_ask:
    st.markdown("<div class='section-tag'>Smart Questions to Ask Your Interviewer</div>", unsafe_allow_html=True)
    st.caption("Always ask 2–3 questions. It signals engagement, helps you evaluate the role, and keeps you memorable.")

    QUESTIONS_TO_ASK = [
        ("Role Clarity",
         "What does success look like in the first 90 days?",
         "This question signals you're already thinking about delivering results, not just passing the interview."),
        ("Team Dynamics",
         "What's the team's biggest challenge right now, and how would this role help address it?",
         "Shows you want to contribute, not just collect a paycheck. Also reveals real organizational context."),
        ("Culture",
         "How would you describe the team culture — and what kind of person tends to thrive here?",
         "Helps you evaluate fit. Also gives you language to use in your thank-you note."),
        ("Growth",
         "What does the career path look like for someone in this role?",
         "Especially important for internships and entry-level. Shows you're thinking long term."),
        ("Decision Process",
         "What's the timeline for next steps, and when should I expect to hear back?",
         "Close every interview with this. Sets expectations and gives you a follow-up anchor."),
        ("Interviewer-Specific",
         "What's your favorite thing about working here — and what's something you'd like to see change?",
         "The second part is what makes this question different. The honest answer tells you a lot about the company."),
        ("Role Context",
         "Is this a newly created role, or would I be replacing someone? What's the origin story of this position?",
         "Tells you whether the role has established expectations or whether you'll be defining it from scratch."),
        ("Strategy",
         "Where do you see the team or company in 2–3 years? What's the big bet?",
         "Good for senior roles. Shows strategic thinking and genuine interest in the company's direction."),
    ]

    for category, question, note in QUESTIONS_TO_ASK:
        col_q, col_note = st.columns([2, 3])
        with col_q:
            st.markdown(
                f"<div class='card-slate' style='padding:14px 16px;height:100%'>"
                f"<div style='font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;margin-bottom:6px'>{xe(category)}</div>"
                f"<div style='font-size:14px;color:#e2e8f0;font-weight:600;line-height:1.5'>&ldquo;{xe(question)}&rdquo;</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with col_note:
            st.markdown(
                f"<div style='padding:14px 0;font-size:13px;color:#64748b;line-height:1.6'>{xe(note)}</div>",
                unsafe_allow_html=True
            )

# ── Post-Interview Debrief ────────────────────────────────────────
with tab_debrief:
    st.markdown("<div class='page-sub'>Turn your interview notes into a specific, ready-to-send thank-you note — not a generic template.</div>", unsafe_allow_html=True)

    _db_c1, _db_c2 = st.columns(2)
    _db_interviewer = _db_c1.text_input("Interviewer name", placeholder="Sarah Johnson", key="db_interviewer")
    _db_role        = _db_c2.text_input("Role you interviewed for", placeholder="Data Analyst", key="db_role")
    _db_company     = st.text_input("Company", placeholder="Acme Corp", key="db_company")
    _db_topics      = st.text_area(
        "What did you discuss? (be specific — the more detail, the better the note)",
        height=140,
        placeholder=(
            "Examples:\n"
            "- They mentioned the team is expanding into ML-powered forecasting\n"
            "- We discussed how I'd approach cleaning their messy CRM data\n"
            "- Interviewer Sarah shared that the biggest pain point is slow reporting\n"
            "- I asked about the 90-day success metric and they said shipping the dashboard MVP"
        ),
        key="db_topics",
    )

    if st.button("Generate Thank-You Note", type="primary", key="db_gen_btn", use_container_width=True):
        if not _db_topics.strip():
            st.error("Add at least a few notes about what you discussed — that's what makes the note specific.")
        else:
            from claude_ai import stream_thankyou_claude
            st.session_state.pop("db_ty_result", None)
            _role_ctx = _db_role or (job.get("title","") if "job" in dir() else "the role")
            _co_ctx   = _db_company or (job.get("company","") if "job" in dir() else "the company")
            streamed_ty = st.write_stream(stream_thankyou_claude(
                interviewer_name=_db_interviewer,
                role=_role_ctx,
                company=_co_ctx,
                topics_discussed=_db_topics,
                candidate_name=profile.get("name","") if profile else "",
                resume_text=profile.get("raw_text","")[:1000] if profile else "",
            ))
            st.session_state["db_ty_result"] = streamed_ty
            st.rerun()

    _ty_out = st.session_state.get("db_ty_result", "")
    if _ty_out:
        st.text_area(
            "Your thank-you note — review, edit, then copy:",
            value=_ty_out,
            height=220,
            key="db_ty_edit",
        )
        st.markdown(
            "<div style='font-size:12px;color:#64748b;margin-top:8px'>"
            "💡 Send within 24 hours. Email is better than LinkedIn for this. Subject line: "
            "\"Thank you — [Role] interview\" — direct and easy to find."
            "</div>",
            unsafe_allow_html=True
        )

        st.markdown("---")
        st.markdown("<div class='section-tag'>Post-Interview Debrief Checklist</div>", unsafe_allow_html=True)
        _checklist = [
            ("Send thank-you note within 24 hours", True if _ty_out else False),
            ("Note down every question you were asked — review them before next rounds", False),
            ("Record any red flags or concerns that came up", False),
            ("Check LinkedIn profiles of everyone you spoke with", False),
            ("Research any topics they mentioned that you weren't fully prepared for", False),
            ("If you blanked on a question, draft a better answer now while it's fresh", False),
        ]
        for _ci, (_ct, _cd) in enumerate(_checklist):
            _done = st.checkbox(_ct, value=_cd, key=f"debrief_chk_{_ci}")
    else:
        st.markdown(
            alert("Fill in the fields above and click Generate — the more specific your notes, the better the thank-you note.", "blue"),
            unsafe_allow_html=True
        )
