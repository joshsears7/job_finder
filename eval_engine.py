"""
eval_engine.py
--------------
LLM output evaluation for CareerIQ.
Scores generated cover letters, LinkedIn sections, and interview answers
across dimensions: relevance, grounding, specificity, tone, keyword coverage.
No external eval framework required — pure Python + Claude.
"""

import re
import sqlite3
import threading
import logging
from datetime import datetime

_DB   = "eval_results.db"
_lock = threading.Lock()
_log  = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init():
    with _lock:
        conn = _connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS eval_results (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                output_type  TEXT NOT NULL,
                model        TEXT DEFAULT 'haiku',
                relevance    INTEGER,
                grounding    INTEGER,
                specificity  INTEGER,
                tone         INTEGER,
                keyword_cov  INTEGER,
                overall      INTEGER,
                flags        TEXT DEFAULT '[]',
                input_hash   TEXT,
                created_at   TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()


_init()


# ── Heuristic evaluators (no API cost) ───────────────────────────

def _keyword_coverage(generated: str, job_description: str) -> int:
    """
    0-100: what fraction of non-trivial JD words appear in the generated text?
    Simple but meaningful signal for ATS alignment.
    """
    if not job_description.strip():
        return 100  # can't evaluate without JD
    _stop = frozenset([
        "and","or","the","a","an","of","in","at","for","to","with","is","are",
        "will","you","your","we","our","this","that","have","be","as","by",
        "from","their","they","can","all","but","not","do","may","must","also",
        "would","should","through","including","within","across","provide","ensure",
    ])
    jd_words = {
        w.lower() for w in re.findall(r"[a-zA-Z]{4,}", job_description)
        if w.lower() not in _stop
    }
    if not jd_words:
        return 100
    gen_lower = generated.lower()
    covered   = sum(1 for w in jd_words if w in gen_lower)
    return min(100, int(covered / len(jd_words) * 100))


def _grounding_score(generated: str, resume_text: str) -> int:
    """
    0-100: are specific resume facts present in the generated text?
    Checks for numbers, proper nouns, and skill names from the resume.
    """
    if not resume_text.strip():
        return 50  # neutral when no resume provided

    # Extract specific signals from resume: numbers, capitalized phrases ≥3 chars
    numbers    = re.findall(r"\d+", resume_text)
    cap_phrases = re.findall(r"[A-Z][a-zA-Z]{2,}(?:\s+[A-Z][a-zA-Z]{2,})*", resume_text)

    gen_lower = generated.lower()
    hits = 0
    total_checks = 0

    for n in numbers[:10]:
        total_checks += 1
        if n in generated:
            hits += 1

    for phrase in cap_phrases[:15]:
        if len(phrase) < 4:
            continue
        total_checks += 1
        if phrase.lower() in gen_lower:
            hits += 1

    if total_checks == 0:
        return 50
    return min(100, int(hits / total_checks * 100) + 30)  # +30 floor (some generalization is fine)


def _specificity_score(generated: str) -> int:
    """
    0-100: penalize vague filler phrases.
    Specific text = real names, numbers, outcomes. Vague text = buzzwords and platitudes.
    """
    _VAGUE = [
        "results-driven", "team player", "passionate", "hardworking", "dynamic",
        "synergy", "leverage", "utilize", "impactful", "innovative", "proactive",
        "go-getter", "self-starter", "detail-oriented", "fast-paced", "excited about",
        "looking to grow", "seeking an opportunity", "i am a", "i believe that",
        "I am passionate", "deeply passionate", "extensive experience",
        "proven track record", "seasoned professional",
    ]
    _SPECIFIC = [
        r"\d+%", r"\$[\d,]+", r"\d+ (years?|months?|people|team|users?|customers?)",
        r"(built|shipped|launched|led|reduced|increased|drove|generated|grew)\s+\w+",
    ]

    text_lower = generated.lower()
    vague_hits   = sum(1 for v in _VAGUE if v.lower() in text_lower)
    specific_hits = sum(1 for p in _SPECIFIC if re.search(p, generated, re.IGNORECASE))

    # Start at 70, subtract for vague, add for specific
    score = 70 - (vague_hits * 8) + (specific_hits * 6)
    return max(10, min(100, score))


def _tone_score(generated: str, output_type: str) -> int:
    """
    0-100: basic tone check — appropriate length and no obvious issues.
    """
    words = len(generated.split())
    score = 75  # baseline

    if output_type == "cover_letter":
        if 150 <= words <= 350:
            score += 15
        elif words < 100 or words > 500:
            score -= 20
        # Penalize "[" brackets — means placeholders weren't filled
        if "[" in generated or "]" in generated:
            score -= 30
        # Penalize "I am writing to express" type openers
        if re.search(r"i am writing to (express|apply|inquire)", generated.lower()):
            score -= 10

    elif output_type == "linkedin_about":
        if 120 <= words <= 280:
            score += 15
        elif words < 80 or words > 400:
            score -= 15

    elif output_type == "interview_answer":
        if 100 <= words <= 250:
            score += 15
        elif words < 60 or words > 400:
            score -= 15

    return max(10, min(100, score))


def _relevance_score(generated: str, job_description: str, output_type: str) -> int:
    """
    0-100: does the generated text address the job description?
    Simple overlap check between JD key phrases and generated text.
    """
    if not job_description.strip():
        return 75  # can't evaluate without JD

    # Extract 2-3 word phrases from JD
    jd_phrases = re.findall(r"[a-z][a-z\s]{4,20}[a-z]", job_description.lower())
    if not jd_phrases:
        return 75

    gen_lower = generated.lower()
    hits = sum(1 for p in jd_phrases[:20] if p.strip() in gen_lower)
    return min(100, int(hits / min(len(jd_phrases), 20) * 100) + 20)


# ── Main eval function ────────────────────────────────────────────

def evaluate(
    generated: str,
    output_type: str,
    resume_text: str = "",
    job_description: str = "",
    model: str = "haiku",
    persist: bool = True,
) -> dict:
    """
    Evaluate a generated output across 5 dimensions.

    output_type: "cover_letter" | "linkedin_about" | "interview_answer" | "cold_dm" | "other"
    Returns dict with scores 0-100 per dimension, overall, flags, and grade.
    """
    if not generated or not generated.strip():
        return {"error": "No output to evaluate."}

    relevance   = _relevance_score(generated, job_description, output_type)
    grounding   = _grounding_score(generated, resume_text)
    specificity = _specificity_score(generated)
    tone        = _tone_score(generated, output_type)
    keyword_cov = _keyword_coverage(generated, job_description)

    # Weighted overall — relevance and grounding matter most
    weights = {"relevance": 0.25, "grounding": 0.25, "specificity": 0.25, "tone": 0.15, "keyword_cov": 0.10}
    overall = int(
        relevance   * weights["relevance"]  +
        grounding   * weights["grounding"]  +
        specificity * weights["specificity"] +
        tone        * weights["tone"]       +
        keyword_cov * weights["keyword_cov"]
    )

    # Flags — things to improve
    flags = []
    if "[" in generated or "]" in generated:
        flags.append("Contains unfilled placeholder brackets")
    if grounding < 40:
        flags.append("Low grounding — few resume-specific facts in the output")
    if specificity < 40:
        flags.append("Too vague — reduce filler phrases, add specific outcomes")
    if tone < 50:
        flags.append("Tone or length issue — review output structure")
    if keyword_cov < 30 and job_description:
        flags.append("Low JD keyword coverage — consider tailoring further")

    grade = "A" if overall >= 85 else "B" if overall >= 70 else "C" if overall >= 55 else "D" if overall >= 40 else "F"

    result = {
        "relevance":   relevance,
        "grounding":   grounding,
        "specificity": specificity,
        "tone":        tone,
        "keyword_cov": keyword_cov,
        "overall":     overall,
        "grade":       grade,
        "flags":       flags,
        "output_type": output_type,
        "model":       model,
    }

    if persist:
        _persist(result)

    return result


def _persist(result: dict):
    import json
    with _lock:
        try:
            conn = _connect()
            conn.execute(
                """INSERT INTO eval_results
                   (output_type, model, relevance, grounding, specificity, tone,
                    keyword_cov, overall, flags, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    result["output_type"], result["model"],
                    result["relevance"], result["grounding"], result["specificity"],
                    result["tone"], result["keyword_cov"], result["overall"],
                    json.dumps(result["flags"]),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            _log.warning("eval persist failed: %s", e)


# ── Aggregate stats ────────────────────────────────────────────────

def get_eval_history(limit: int = 50) -> list[dict]:
    """Return recent eval results."""
    import json
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM eval_results ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["flags"] = json.loads(d.get("flags") or "[]")
        except Exception:
            d["flags"] = []
        results.append(d)
    return results


def get_eval_summary() -> dict:
    """Aggregate stats across all eval results."""
    with _lock:
        conn = _connect()
        rows = conn.execute("SELECT * FROM eval_results").fetchall()
        conn.close()

    if not rows:
        return {"total": 0}

    rows = [dict(r) for r in rows]
    total = len(rows)
    avg_overall    = round(sum(r["overall"] or 0 for r in rows) / total, 1)
    avg_grounding  = round(sum(r["grounding"] or 0 for r in rows) / total, 1)
    avg_specificity = round(sum(r["specificity"] or 0 for r in rows) / total, 1)

    by_type: dict = {}
    for r in rows:
        t = r.get("output_type", "other")
        by_type.setdefault(t, []).append(r["overall"] or 0)
    type_avgs = {t: round(sum(v) / len(v), 1) for t, v in by_type.items()}

    return {
        "total":          total,
        "avg_overall":    avg_overall,
        "avg_grounding":  avg_grounding,
        "avg_specificity": avg_specificity,
        "by_type":        type_avgs,
    }
