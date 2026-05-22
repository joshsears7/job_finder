"""
claude_ai.py
------------
Claude-powered generation for cover letters, LinkedIn sections, and cold DMs.
Falls back gracefully if ANTHROPIC_API_KEY is not set or anthropic is not installed.
"""

import os
import re
import time

_client = None

# Last error from _call_claude — readable by callers for user-facing messages
_last_error: str = ""

# Model constants — override via env vars to avoid touching code on model upgrades
_HAIKU  = os.getenv("CLAUDE_MODEL_HAIKU",  "claude-haiku-4-5")
_SONNET = os.getenv("CLAUDE_MODEL_SONNET", "claude-sonnet-4-6")


def _sanitize(text: str, max_len: int = 4000) -> str:
    """Sanitize user-controlled text before inserting into a prompt.
    Strips common prompt-injection patterns and limits length."""
    if not text:
        return ""
    # Remove markdown code fences and injection-style role overrides
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"(?i)(ignore (all |previous |above )?(instructions?|rules?|prompts?)|"
                  r"you are now|new instruction|system:|</?s>|</?human>)", "", text)
    return text[:max_len]


def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        try:
            import anthropic
            _client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            return None
    return _client


def claude_available() -> bool:
    return _get_client() is not None


def get_last_error() -> str:
    """Return a human-readable description of the last Claude API failure."""
    return _last_error


def _call_claude(system: str, user: str, max_tokens: int = 2048, retries: int = 2) -> str | None:
    """
    Claude API call with retry logic and error capture.
    Retries up to `retries` times on transient errors (rate-limit, server error).
    Returns text content or None; sets _last_error on failure.
    """
    global _last_error
    _last_error = ""
    client = _get_client()
    if client is None:
        _last_error = "ANTHROPIC_API_KEY not set — Claude features are unavailable."
        return None

    last_exc = None
    for attempt in range(retries + 1):
        try:
            with client.messages.stream(
                model=_HAIKU,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            ) as stream:
                msg = stream.get_final_message()
                _last_error = ""
                return next((b.text for b in msg.content if b.type == "text"), None)
        except Exception as e:
            last_exc = e
            err_str = str(e).lower()
            # Retry on rate-limit or server errors, abort immediately on auth/bad-request
            if attempt < retries and any(
                kw in err_str for kw in ("rate", "overloaded", "529", "500", "503", "timeout")
            ):
                time.sleep(2 ** attempt)  # 1s, then 2s
                continue
            break

    if last_exc is not None:
        err_str = str(last_exc)
        if "401" in err_str or "auth" in err_str.lower():
            _last_error = "Invalid API key — check ANTHROPIC_API_KEY in .env."
        elif "rate" in err_str.lower():
            _last_error = "Rate limit reached — wait a moment and try again."
        elif "overloaded" in err_str.lower() or "529" in err_str:
            _last_error = "Claude is overloaded — try again in a few seconds."
        else:
            _last_error = f"Claude API error: {err_str[:120]}"
    return None


def _stream_claude(system: str, user: str, max_tokens: int = 2048, model: str = None):
    """Generator that yields text chunks from Claude's streaming API. Use with st.write_stream()."""
    global _last_error
    _last_error = ""
    if model is None:
        model = _HAIKU
    client = _get_client()
    if client is None:
        _last_error = "ANTHROPIC_API_KEY not set — Claude features are unavailable."
        yield "⚠ Claude API not available — add ANTHROPIC_API_KEY to .env"
        return
    try:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "auth" in err_str.lower():
            _last_error = "Invalid API key — check ANTHROPIC_API_KEY in .env."
        elif "rate" in err_str.lower():
            _last_error = "Rate limit reached — wait a moment and try again."
        else:
            _last_error = f"Claude API error: {err_str[:120]}"
        yield f"\n\n[Generation stopped: {_last_error}]"


def stream_cover_letter_claude(profile: dict, job: dict):
    """Stream a Sonnet-quality cover letter. Pass to st.write_stream()."""
    resume_text = _sanitize(profile.get("raw_text", ""), 3000)
    company     = _sanitize(job.get("company", "the company"), 100)
    role        = _sanitize(job.get("title", "this position"), 100)
    jd          = _sanitize(job.get("description", ""), 1500)
    name        = _sanitize(profile.get("name", ""), 80)

    system = (
        "You are an expert career coach and professional writer. "
        "Write concise, specific, genuinely personalized cover letters. "
        "Reference actual details from the resume — never use generic filler or placeholders. "
        "Sound like a real person: confident, not stiff, not sycophantic. "
        "Format: 3 tight paragraphs, no headers, ready to copy-paste. "
        "Never use brackets or placeholders like [insert X]."
    )
    user = f"""Write a cover letter for {name or 'the candidate'} applying for the {role} role at {company}.

RESUME:
{resume_text}

JOB DESCRIPTION:
{jd}

Requirements:
- Opening: one specific observation about this company or role — not generic praise
- Body: connect 2-3 accomplishments from the resume directly to the JD requirements with specifics
- Close: direct ask (not "I look forward to hearing from you") — e.g. "I'd welcome a conversation about..."
- Under 280 words total"""

    return _stream_claude(system, user, max_tokens=600, model=_SONNET)


def stream_about_claude(profile: dict, target_role: str = ""):
    """Stream a LinkedIn About section. Pass to st.write_stream()."""
    resume_text = _sanitize(profile.get("raw_text", ""), 3000)
    name        = _sanitize(profile.get("name", ""), 80)
    target_role = _sanitize(target_role, 100)

    system = (
        "You are a LinkedIn profile expert. Write About sections that sound like real people, "
        "not corporate bios. Pull specific details from the resume. "
        "Structure: Hook → What I bring (3 bullets) → Proof (specific accomplishment) → CTA. "
        "180-220 words. First person. No buzzwords."
    )
    user = f"""Write a LinkedIn About section for {name or 'this person'}{f' targeting {target_role} roles' if target_role else ''}.

RESUME:
{resume_text}

Instructions:
- Hook: a specific, honest statement about what drives them — pulled from their actual background
- Bring section: exactly 3 bullet points starting with action verbs, using real skills/experiences from this resume
- Proof: 1-2 sentences with a specific accomplishment from the resume (name real numbers or outcomes if present)
- CTA: one simple line — open to opportunities or connecting
- Sound like a person wrote it, not a template
- 180-220 words"""

    return _stream_claude(system, user, max_tokens=400, model=_SONNET)


def stream_coach_interview_claude(question: str, rough_answer: str, resume_text: str, job_title: str = ""):
    """Stream a polished STAR interview answer. Pass to st.write_stream()."""
    question     = _sanitize(question, 500)
    rough_answer = _sanitize(rough_answer, 1000)
    resume_text  = _sanitize(resume_text, 2000)
    job_title    = _sanitize(job_title, 100)
    system = (
        "You are an interview coach. Rewrite rough answers into polished STAR-format responses "
        "that are specific, confident, and draw on the candidate's actual experience. "
        "Conversational tone — not robotic. 150-200 words."
    )
    user = f"""Rewrite this interview answer using STAR format (Situation → Task → Action → Result).

QUESTION: {question}

ROUGH ANSWER: {rough_answer}

CANDIDATE RESUME (pull real details from here):
{resume_text}
{f'TARGET ROLE: {job_title}' if job_title else ''}

Instructions:
- Pull specific details, numbers, and achievements from the resume
- Write as flowing speech — not labeled S/T/A/R sections
- Natural, confident tone — sounds like a real person
- 150-200 words
- End with the concrete result or impact"""
    return _stream_claude(system, user, max_tokens=400)


def stream_writing_tool_claude(system: str, user: str, max_tokens: int = 800):
    """Generic streaming writer for Writing Suite tools. Pass to st.write_stream()."""
    return _stream_claude(system, user, max_tokens=max_tokens)


def stream_thankyou_claude(
    interviewer_name: str,
    role: str,
    company: str,
    topics_discussed: str,
    candidate_name: str = "",
    resume_text: str = "",
):
    """Stream a personalized post-interview thank-you note. Pass to st.write_stream()."""
    interviewer = _sanitize(interviewer_name, 80)
    role        = _sanitize(role, 100)
    company     = _sanitize(company, 100)
    topics      = _sanitize(topics_discussed, 800)
    name        = _sanitize(candidate_name, 80)
    resume_ctx  = _sanitize(resume_text, 1000)

    system = (
        "You are an expert career coach. Write a concise, genuine post-interview thank-you note. "
        "Reference the specific topics discussed — never use brackets or placeholders. "
        "Tone: warm, professional, confident. Under 180 words. Ready to send as-is."
    )
    first = interviewer.split()[0] if interviewer and interviewer.strip() else "there"
    user = f"""Write a thank-you note for {name or 'the candidate'} to send after interviewing for the {role} role at {company} with {first}.

Topics they discussed:
{topics}

Candidate background (for reference):
{resume_ctx}

Requirements:
- Address {first} by first name
- Reference 1-2 specific things from the topics discussed above — not generic filler
- Reinforce the candidate's strongest relevant qualification in one natural sentence
- End with a clear, confident close (not "I look forward to hearing from you" — be more specific)
- Under 180 words total
- No brackets, no placeholders — every word should be ready to send"""

    return _stream_claude(system, user, max_tokens=300)


def generate_cover_letter_claude(profile: dict, job: dict) -> str | None:
    """Generate a personalized cover letter using Claude."""
    resume_text = _sanitize(profile.get("raw_text", ""), 3000)
    company     = _sanitize(job.get("company", "the company"), 100)
    role        = _sanitize(job.get("title", "this position"), 100)
    jd          = _sanitize(job.get("description", ""), 1500)
    name        = _sanitize(profile.get("name", ""), 80)

    system = (
        "You are an expert career coach and professional writer. "
        "Write concise, specific, genuinely personalized cover letters. "
        "Reference actual details from the resume — never use generic filler or placeholders. "
        "Sound like a real person: confident, not stiff, not sycophantic. "
        "Format: 3 tight paragraphs, no headers, ready to copy-paste. "
        "Never use brackets or placeholders like [insert X]."
    )
    user = f"""Write a cover letter for {name or 'the candidate'} applying for the {role} role at {company}.

RESUME:
{resume_text}

JOB DESCRIPTION:
{jd}

Requirements:
- Opening: one specific observation about this company or role — not generic praise
- Body: connect 2-3 accomplishments from the resume directly to the JD requirements with specifics
- Close: direct ask (not "I look forward to hearing from you") — e.g. "I'd welcome a conversation about..."
- Under 280 words total"""

    result = _call_claude_sonnet(system, user, max_tokens=600)
    return result if result else _call_claude(system, user, max_tokens=600)


def generate_about_claude(profile: dict, target_role: str = "") -> str | None:
    """Generate a LinkedIn About section using Claude."""
    resume_text = _sanitize(profile.get("raw_text", ""), 3000)
    name        = _sanitize(profile.get("name", ""), 80)
    target_role = _sanitize(target_role, 100)

    system = (
        "You are a LinkedIn profile expert. Write About sections that sound like real people, "
        "not corporate bios. Pull specific details from the resume. "
        "Structure: Hook → What I bring (3 bullets) → Proof (specific accomplishment) → CTA. "
        "180-220 words. First person. No buzzwords."
    )
    user = f"""Write a LinkedIn About section for {name or 'this person'}{f' targeting {target_role} roles' if target_role else ''}.

RESUME:
{resume_text}

Instructions:
- Hook: a specific, honest statement about what drives them — pulled from their actual background
- Bring section: exactly 3 bullet points starting with action verbs, using real skills/experiences from this resume
- Proof: 1-2 sentences with a specific accomplishment from the resume (name real numbers or outcomes if present)
- CTA: one simple line — open to opportunities or connecting
- Sound like a person wrote it, not a template
- 180-220 words"""

    return _call_claude(system, user)


def generate_headlines_claude(profile: dict, target_role: str = "") -> list[str] | None:
    """Generate 3 LinkedIn headline variants using Claude."""
    resume_text = _sanitize(profile.get("raw_text", ""), 2000)
    target_role = _sanitize(target_role, 100)

    system = (
        "You are a LinkedIn optimization expert. Headlines must be specific, keyword-rich, "
        "and under 220 characters. Return exactly 3 options numbered 1. 2. 3. — no other text."
    )
    user = f"""Write 3 LinkedIn headline variants for this person{f' targeting {target_role} roles' if target_role else ''}.

RESUME:
{resume_text}

Requirements:
- Each under 220 characters
- Use actual skills and titles from this resume — not generic placeholders
- Variant 1: ATS/keyword-dense (Role | Skill · Skill · Skill | Status)
- Variant 2: Value-prop driven (outcome or impact focused, reads like a pitch)
- Variant 3: Personal brand / bold statement (distinctive, memorable)
- Return only the 3 headlines, numbered 1. 2. 3. — nothing else before or after"""

    result = _call_claude(system, user, max_tokens=512)
    if result is None:
        return None

    lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
    headlines = []
    for line in lines:
        cleaned = re.sub(r"^\d+[.)]\s*", "", line).strip()
        if cleaned:
            headlines.append(cleaned[:220])
    return headlines[:3] if headlines else None


def rewrite_bullet_claude(bullet: str, resume_text: str, job_description: str = "") -> str | None:
    """Rewrite a single resume bullet — stronger verb, better metric, more specific."""
    bullet        = _sanitize(bullet, 500)
    resume_text   = _sanitize(resume_text, 2000)
    job_description = _sanitize(job_description, 600)
    jd_ctx = f"\n\nJob context:\n{job_description}" if job_description else ""
    system = (
        "You are a resume expert. Rewrite the bullet to be stronger: powerful action verb, "
        "specific quantified result. Return ONLY the rewritten bullet — no explanation, no quotes, no prefix."
    )
    user = f"""Rewrite this resume bullet to be stronger and more impactful.

ORIGINAL BULLET: {bullet}

RESUME (for accurate context):
{resume_text}{jd_ctx}

Rules:
- Start with a strong, specific action verb (not generic ones like "managed" or "helped")
- If the original has numbers, keep or sharpen them; if not, do NOT invent placeholders — instead make the outcome more specific and vivid
- Replace vague language with concrete details from the resume context
- Under 35 words
- Return only the rewritten bullet, nothing else"""
    return _call_claude(system, user, max_tokens=150)


def generate_thankyou_claude(
    interviewer_name: str,
    role: str,
    company: str,
    topics_discussed: str,
    candidate_name: str = "",
    resume_text: str = "",
) -> str | None:
    """Generate a specific, personalized thank-you note after an interview."""
    interviewer = _sanitize(interviewer_name, 80)
    role        = _sanitize(role, 100)
    company     = _sanitize(company, 100)
    topics      = _sanitize(topics_discussed, 800)
    name        = _sanitize(candidate_name, 80)
    resume_ctx  = _sanitize(resume_text, 1000)

    system = (
        "You are an expert career coach. Write a concise, genuine post-interview thank-you note. "
        "Reference the specific topics discussed — never use brackets or placeholders. "
        "Tone: warm, professional, confident. Under 180 words. Ready to send as-is."
    )
    first = interviewer.split()[0] if interviewer and interviewer.strip() else "there"
    user = f"""Write a thank-you note for {name or 'the candidate'} to send after interviewing for the {role} role at {company} with {first}.

Topics they discussed:
{topics}

Candidate background (for reference):
{resume_ctx}

Requirements:
- Address {first} by first name
- Reference 1-2 specific things from the topics discussed above — not generic filler
- Reinforce the candidate's strongest relevant qualification in one natural sentence
- End with a clear, confident close (not "I look forward to hearing from you" — be more specific)
- Under 180 words total
- No brackets, no placeholders — every word should be ready to send"""

    return _call_claude(system, user, max_tokens=300)


def tailor_resume_claude(resume_text: str, job_description: str) -> list[dict] | None:
    """
    Rewrite the 4-5 most relevant resume bullets to align with a specific job description.
    Returns list of {original, rewritten, keyword} dicts.
    """
    import json
    resume_text     = _sanitize(resume_text, 3000)
    job_description = _sanitize(job_description, 1500)
    system = (
        "You are a resume coach. Identify the most relevant bullets and rewrite them "
        "to mirror the job description's language and keywords. Be specific and quantified. "
        "Return valid JSON array only — no markdown, no explanation."
    )
    user = f"""Rewrite the 4-5 most relevant resume bullets to match this job description.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Return a JSON array. Each object must have exactly these keys:
- "original": the original bullet verbatim from resume
- "rewritten": improved version using JD language and keywords
- "keyword": the main JD keyword this bullet now targets

Return ONLY the JSON array, nothing else. Example:
[{{"original": "...", "rewritten": "...", "keyword": "..."}}]"""

    result = _call_claude(system, user, max_tokens=1200)
    if not result:
        return None
    try:
        cleaned = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception:
        return None


def decode_jd_claude(resume_text: str, job_description: str) -> dict | None:
    """
    Decode a JD: what they really want, how to stand out, honest gaps, smart questions.
    Returns dict with keys: what_they_want, stand_out, gaps, questions.
    """
    import json
    resume_text     = _sanitize(resume_text, 2500)
    job_description = _sanitize(job_description, 1500)
    system = (
        "You are a senior recruiter and career strategist. Analyze job descriptions with brutal honesty. "
        "Return valid JSON only — no markdown fences, no explanation."
    )
    user = f"""Analyze this job description against the candidate's resume.

RESUME:
{resume_text}

JOB DESCRIPTION:
{job_description}

Return JSON with exactly these keys:
- "what_they_want": list of 3-4 strings — what this role REALLY needs (read between the lines)
- "stand_out": list of 3 strings — specific things from THIS resume that will impress for THIS role
- "gaps": list of up to 3 strings — honest gaps, each with a one-line fix suggestion
- "questions": list of 3 strings — smart questions to ask in the interview based on this JD

Return ONLY valid JSON, nothing else."""

    result = _call_claude(system, user, max_tokens=800)
    if not result:
        return None
    try:
        cleaned = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception:
        return None


def coach_interview_answer_claude(question: str, rough_answer: str, resume_text: str, job_title: str = "") -> str | None:
    """Rewrite a rough interview answer into a polished STAR-format response using real resume details."""
    question     = _sanitize(question, 500)
    rough_answer = _sanitize(rough_answer, 1000)
    resume_text  = _sanitize(resume_text, 2000)
    job_title    = _sanitize(job_title, 100)
    system = (
        "You are an interview coach. Rewrite rough answers into polished STAR-format responses "
        "that are specific, confident, and draw on the candidate's actual experience. "
        "Conversational tone — not robotic. 150-200 words."
    )
    user = f"""Rewrite this interview answer using STAR format (Situation → Task → Action → Result).

QUESTION: {question}

ROUGH ANSWER: {rough_answer}

CANDIDATE RESUME (pull real details from here):
{resume_text}
{f'TARGET ROLE: {job_title}' if job_title else ''}

Instructions:
- Pull specific details, numbers, and achievements from the resume
- Write as flowing speech — not labeled S/T/A/R sections
- Natural, confident tone — sounds like a real person
- 150-200 words
- End with the concrete result or impact"""
    return _call_claude(system, user, max_tokens=400)


def explain_skill_gaps_claude(missing_skills: list[str], resume_text: str, job_description: str) -> list[dict] | None:
    """
    For each missing skill, explain why it matters and how to address it fast.
    Returns list of {skill, why, how} dicts.
    """
    import json
    if not missing_skills:
        return None
    skills_str      = _sanitize(", ".join(missing_skills[:6]), 300)
    resume_text     = _sanitize(resume_text, 1500)
    job_description = _sanitize(job_description, 1000)
    system = (
        "You are a career advisor. For each missing skill give a brief, specific explanation "
        "of why it matters and the fastest realistic way to address it. "
        "Return valid JSON only — no markdown, no explanation."
    )
    user = f"""For these skills missing from the resume, explain why each matters and how to address the gap.

MISSING SKILLS: {skills_str}

JOB DESCRIPTION:
{job_description}

RESUME (for context):
{resume_text}

Return a JSON array — one object per skill with exactly these keys:
- "skill": the skill name
- "why": 1 sentence — why this skill matters specifically for this role
- "how": 1 sentence — fastest realistic way to address this gap

Return ONLY valid JSON array, nothing else."""

    result = _call_claude(system, user, max_tokens=600)
    if not result:
        return None
    try:
        cleaned = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception:
        return None


def generate_cold_dm_claude(
    profile: dict,
    target_name: str,
    target_company: str,
    target_role_at_co: str = "",
    job_title: str = "",
) -> str | None:
    """Generate a personalized cold LinkedIn DM using Claude."""
    name              = _sanitize(profile.get("name", ""), 80)
    resume_text       = _sanitize(profile.get("raw_text", ""), 1500)
    target_name       = _sanitize(target_name, 80)
    target_company    = _sanitize(target_company, 100)
    target_role_at_co = _sanitize(target_role_at_co, 100)
    job_title         = _sanitize(job_title, 100)
    titles  = profile.get("titles", [])
    my_role = titles[0].title() if titles else "professional"
    first   = target_name.split()[0] if target_name and target_name.strip() else "there"

    system = (
        "You are a networking expert. Write cold LinkedIn DMs that feel genuine and specific, "
        "not templated or spammy. Under 150 words. Mobile-readable. No buzzwords."
    )
    user = f"""Write a cold LinkedIn DM from {name or 'the candidate'} ({my_role}) to {first} at {target_company}{f' regarding the {job_title} role' if job_title else ''}.

SENDER'S BACKGROUND (resume excerpt):
{resume_text}

Instructions:
- 3 short paragraphs, 120-150 words total
- Mention one specific, real thing from the sender's background that is relevant to {target_company}
- Keep the ask low-pressure (15-min call, happy to connect)
- Do NOT use: "I came across your profile", "I'm blown away", "I'd love to pick your brain"
- Sound like a real person reaching out, not a form letter
- No placeholders or brackets"""

    return _call_claude(system, user, max_tokens=400)


def mock_interview_feedback_claude(question: str, answer: str, resume_text: str, job_title: str = "") -> dict | None:
    """
    Give detailed AI feedback on an interview answer.
    Returns dict: {score, verdict, strengths, improvements, example_line}.
    """
    import json
    question    = _sanitize(question, 500)
    answer      = _sanitize(answer, 1500)
    resume_text = _sanitize(resume_text, 2000)
    job_title   = _sanitize(job_title, 100)
    system = (
        "You are a senior hiring manager and interview coach. Give honest, specific, actionable feedback on interview answers. "
        "Return valid JSON only — no markdown, no explanation."
    )
    user = f"""Evaluate this interview answer and give detailed coaching feedback.

QUESTION: {question}

CANDIDATE'S ANSWER: {answer}

CANDIDATE BACKGROUND (resume):
{resume_text}
{f'TARGET ROLE: {job_title}' if job_title else ''}

Return JSON with exactly these keys:
- "score": integer 0-100
- "verdict": one of "Strong", "Good", "Needs Work", "Weak"
- "strengths": list of 2-3 strings — what they did well (be specific, reference their actual words)
- "improvements": list of 2-3 strings — concrete things to add or change
- "example_line": string — one example sentence showing how to open the answer more powerfully

Return ONLY valid JSON."""

    result = _call_claude(system, user, max_tokens=600)
    if not result:
        return None
    try:
        cleaned = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception:
        return None


def assess_fit_claude(profile: dict, job: dict) -> str | None:
    """
    Honest narrative assessment of how well the candidate fits a specific job.
    Returns 2-3 paragraphs of direct, useful analysis.
    """
    resume_text = _sanitize(profile.get("raw_text", ""), 2500)
    company     = _sanitize(job.get("company", "the company"), 100)
    role        = _sanitize(job.get("title", "this role"), 100)
    jd          = _sanitize(job.get("description", ""), 1500)

    system = (
        "You are a brutally honest career advisor. Assess fit between a candidate and a job. "
        "Be direct — not encouraging for its own sake. Give a realistic picture with a rough fit percentage. "
        "3 short paragraphs max. No fluff."
    )
    user = f"""Honestly assess how well this candidate fits the {role} role at {company}.

CANDIDATE RESUME:
{resume_text}

JOB DESCRIPTION:
{jd}

Structure your response:
Paragraph 1: Open with a fit percentage (e.g. "Honest fit: ~70%") and 1-2 sentence summary of the match.
Paragraph 2: The 2-3 strongest reasons they ARE a fit — specific skills or experiences that directly match.
Paragraph 3: The 1-2 real gaps or risks that could hurt their chances — be honest, include a brief fix suggestion.

Keep it under 200 words. No platitudes. Write like you're talking to a friend who asked for your real opinion."""

    return _call_claude(system, user, max_tokens=500)


def company_intel_claude(company: str, job_description: str, role: str = "") -> dict | None:
    """
    Read the JD to infer company culture, day-in-life, red flags, and likely interview Qs.
    Returns dict: {culture_signals, day_in_life, red_flags, likely_questions}.
    """
    import json
    if not job_description.strip():
        return None
    company         = _sanitize(company, 100)
    role            = _sanitize(role, 100)
    job_description = _sanitize(job_description, 2000)
    system = (
        "You are an experienced recruiter and career strategist who reads between the lines of job descriptions. "
        "Decode what the company is really like from how they write. Return valid JSON only."
    )
    user = f"""Analyze this job description for {role or 'the role'} at {company} and decode what it really tells us.

JOB DESCRIPTION:
{job_description}

Return JSON with exactly these keys:
- "culture_signals": list of 3-4 strings — what the language/requirements signal about culture (e.g. "Fast-paced startup energy — 'wear many hats' suggests limited support")
- "day_in_life": list of 3 strings — what a typical week actually looks like based on the responsibilities
- "red_flags": list of up to 3 strings — anything in the JD that's a potential warning sign (or empty list if none)
- "likely_questions": list of 4 strings — specific interview questions THIS company will likely ask based on this JD

Return ONLY valid JSON."""

    result = _call_claude(system, user, max_tokens=700)
    if not result:
        return None
    try:
        cleaned = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception:
        return None


def compare_offers_claude(offers: list[dict], profile: dict) -> dict | None:
    """
    Side-by-side offer analysis with a recommendation.
    offers: list of dicts with keys: company, role, salary, equity, benefits, notes
    Returns dict: {recommendation, breakdown, negotiation_tips}.
    """
    import json
    if not offers:
        return None
    resume_text = _sanitize(profile.get("raw_text", ""), 1500)
    offers_text = "\n\n".join(
        f"OFFER {i+1} — {_sanitize(o.get('company','?'),80)} ({_sanitize(o.get('role','?'),80)}):\n"
        f"  Salary: {_sanitize(o.get('salary','?'),50)}\n"
        f"  Equity/Bonus: {_sanitize(o.get('equity','not specified'),100)}\n"
        f"  Benefits: {_sanitize(o.get('benefits','not specified'),200)}\n"
        f"  Notes: {_sanitize(o.get('notes',''),200)}"
        for i, o in enumerate(offers)
    )
    system = (
        "You are a compensation expert and career advisor. Analyze job offers objectively. "
        "Look beyond salary to total comp, growth, and career trajectory. Return valid JSON only."
    )
    user = f"""Compare these job offers and give a clear recommendation for this candidate.

{offers_text}

CANDIDATE BACKGROUND:
{resume_text}

Return JSON with exactly these keys:
- "recommendation": string — which offer to take and the single most important reason why (2-3 sentences, direct)
- "breakdown": list of objects, one per offer, each with keys:
    "company": company name
    "pros": list of 2-3 strings
    "cons": list of 2-3 strings
    "total_comp_note": string — any calculation or context on total compensation
- "negotiation_tips": list of 2-3 strings — specific things to negotiate regardless of which offer they choose

Return ONLY valid JSON."""

    result = _call_claude(system, user, max_tokens=900)
    if not result:
        return None
    try:
        cleaned = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(cleaned)
    except Exception:
        return None


def job_search_strategy_claude(profile: dict, applications: list[dict]) -> str | None:
    """
    Give strategic advice on the job search based on resume + application history.
    applications: list of {title, company, status, source}
    Returns narrative strategy advice (3-4 paragraphs).
    """
    resume_text = _sanitize(profile.get("raw_text", ""), 2500)
    name        = _sanitize(profile.get("name", ""), 80)

    app_summary = ""
    if applications:
        statuses: dict = {}
        for a in applications:
            statuses[a.get("status", "unknown")] = statuses.get(a.get("status", "unknown"), 0) + 1
        total = len(applications)
        status_str = ", ".join(f"{v} {k}" for k, v in statuses.items())
        titles = list({a.get("title", "") for a in applications if a.get("title")})[:6]
        companies = list({a.get("company", "") for a in applications if a.get("company")})[:6]
        app_summary = (
            f"\n\nAPPLICATION HISTORY ({total} total):\n"
            f"Status breakdown: {status_str}\n"
            f"Roles applied to: {', '.join(titles)}\n"
            f"Companies applied to: {', '.join(companies)}"
        )

    system = (
        "You are a senior career strategist. Give direct, specific, actionable job search advice. "
        "No generic tips — everything must be specific to this person's resume and situation. "
        "Be honest about what's working and what isn't."
    )
    user = f"""Give {name or 'this candidate'} a specific job search strategy based on their resume and application history.

RESUME:
{resume_text}
{app_summary}

Write 3-4 focused paragraphs covering:
1. Your honest read of their positioning — what role/level are they realistically targeting and is the strategy working?
2. The 2-3 highest-leverage things they should do THIS WEEK to improve results
3. What to do differently with applications (targeting, messaging, channels) — be specific
4. One thing most people overlook at their career level that could be a real differentiator

Under 300 words. Be direct. No motivational fluff."""

    return _call_claude(system, user, max_tokens=700)

# ── Career Intelligence (Sonnet-powered) ──────────────────────────────

def _call_claude_sonnet(system: str, user: str, max_tokens: int = 1500):
    """Higher-quality Sonnet pathway for career intelligence features."""
    _client = _get_client()
    if _client is None:
        return None
    try:
        full = ""
        with _client.messages.stream(
            model=_SONNET,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        ) as s:
            for chunk in s.text_stream:
                full += chunk
        return full
    except Exception as e:
        return None


def _parse_json_response(text) -> dict:
    """Strip markdown fences and parse JSON from Claude response."""
    import json, re
    if not text:
        return {}
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text.strip(), flags=re.MULTILINE)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return {}


def executive_narrative_claude(profile: dict, career_level_data: dict) -> dict:
    """Analyse career narrative arc and executive positioning."""
    level  = _sanitize(str(career_level_data.get("level", "mid")), 20)
    resume = _sanitize(profile.get("raw_text", ""), 3000)
    name   = _sanitize(profile.get("name", "this candidate"), 80)

    system = (
        "You are a senior executive career coach. "
        "Analyse career narrative, positioning, and brand differentiation. "
        "Return valid JSON only."
    )
    user = f"""Analyse {name}'s career narrative and executive positioning.

Career Level: {level}
Resume:
{resume}

Return ONLY a JSON object:
{{
  "narrative_grade": "<A/B/C/D/F>",
  "arc_score": <int 0-100>,
  "six_second_impression": "<what a recruiter sees in 6 seconds>",
  "positioning_statement": "<1 sentence: what this person is and does>",
  "arc_strengths": ["<strength 1>", "<strength 2>"],
  "arc_gaps": ["<gap 1>", "<gap 2>"],
  "differentiation": "<what makes them stand out vs peers at {level} level>",
  "headline_rewrite": "<stronger resume headline>",
  "career_level_advice": "<2-3 sentences specific to {level} level>"
}}"""

    return _parse_json_response(_call_claude_sonnet(system, user, max_tokens=900))


def compensation_intel_claude(profile: dict, career_level_data: dict) -> dict:
    """Generate compensation intelligence and negotiation strategy."""
    level  = _sanitize(str(career_level_data.get("level", "mid")), 20)
    years  = int(career_level_data.get("years", 0))
    skills = profile.get("skills", [])[:10]
    resume = _sanitize(profile.get("raw_text", ""), 2000)

    system = (
        "You are a compensation analyst with current US market data. "
        "Provide specific, realistic comp ranges — not generic. "
        "Return valid JSON only."
    )
    user = f"""Estimate compensation for this candidate.

Career Level: {level}
Years Experience: {years}
Key Skills: {', '.join(skills)}
Resume excerpt:
{resume}

Return ONLY a JSON object:
{{
  "base_range": {{"low": <int>, "mid": <int>, "high": <int>}},
  "total_comp_range": {{"low": <int>, "mid": <int>, "high": <int>}},
  "market_percentile": "<e.g. 60th-75th percentile>",
  "negotiation_leverage": ["<leverage point 1>", "<leverage point 2>", "<leverage point 3>"],
  "comp_gaps": ["<gap 1>", "<gap 2>"],
  "ask_strategy": "<tactical comp negotiation advice, 2-3 sentences>",
  "equity_note": "<equity/RSU context for this level>",
  "benchmark_context": "<1 sentence: how this profile compares to market>"
}}

Use 2024-2025 US market data. Be specific with numbers."""

    return _parse_json_response(_call_claude_sonnet(system, user, max_tokens=800))


def brand_differentiation_claude(profile: dict, career_level_data: dict) -> dict:
    """Identify brand differentiation and unique value proposition."""
    level  = _sanitize(str(career_level_data.get("level", "mid")), 20)
    resume = _sanitize(profile.get("raw_text", ""), 3000)
    name   = _sanitize(profile.get("name", "this candidate"), 80)

    system = (
        "You are a personal branding expert for professionals at all career levels. "
        "Identify what makes someone genuinely distinctive — not platitudes. "
        "Return valid JSON only."
    )
    user = f"""Analyse {name}'s professional brand and positioning.

Career Level: {level}
Resume:
{resume}

Return ONLY a JSON object:
{{
  "brand_archetype": "<e.g. The Operator, The Builder, The Strategist>",
  "unique_value_proposition": "<1 crisp sentence — what makes them uniquely valuable>",
  "strongest_proof_points": ["<achievement 1>", "<achievement 2>", "<achievement 3>"],
  "brand_gaps": ["<missing element 1>", "<missing element 2>"],
  "linkedin_headline": "<optimised LinkedIn headline under 200 chars>",
  "elevator_pitch": "<3-sentence elevator pitch for networking events>",
  "blind_spots": ["<undersold element 1>", "<undersold element 2>"],
  "competitor_differentiation": "<how they stand out vs typical {level}-level candidates>",
  "target_audience": "<who should they market themselves to — specific company types, roles>"
}}

Be specific. Reference what is actually in their resume."""

    return _parse_json_response(_call_claude_sonnet(system, user, max_tokens=1000))
