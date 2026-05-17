"""
Tests for scorer.py — pure-function and integration layers.

Model-dependent tests (score_job, batch_score_jobs) are marked with
pytest.mark.slow and skipped by default unless -m slow is passed.
"""
import pytest
from scorer import (
    _skill_in_text,
    _extract_jd_phrases,
    get_skill_gaps,
    ghost_score,
    salary_adjusted_score,
)
from tests.conftest import SAMPLE_RESUME, SAMPLE_JD_ANALYST, SAMPLE_JD_UNRELATED, SAMPLE_JOB


# ── _skill_in_text ────────────────────────────────────────────────────────────

class TestSkillInText:
    def test_long_skill_substring_match(self):
        assert _skill_in_text("python", "experience with python scripting")

    def test_long_skill_not_present(self):
        assert not _skill_in_text("python", "experience with ruby on rails")

    def test_short_skill_word_boundary_match(self):
        # "sql" is short → must match as whole word
        assert _skill_in_text("sql", "strong sql skills required")

    def test_short_skill_no_false_positive(self):
        # "sql" is in _SHORT_SKILLS (3 chars, alpha, in COMMON_SKILLS)
        # "sql" appears inside "mysql" — word boundary must prevent false positive
        assert not _skill_in_text("sql", "must know mysql and postgresql")

    def test_short_skill_word_boundary_present(self):
        # "sql" as standalone word must match
        assert _skill_in_text("sql", "strong sql skills required")

    def test_case_insensitive_via_lowercase_input(self):
        # _skill_in_text expects already-lowercased text
        text = "PYTHON DEVELOPER WITH EXPERIENCE".lower()
        assert _skill_in_text("python", text)

    def test_exact_match_multi_word(self):
        assert _skill_in_text("power bi", "must know power bi dashboards")

    def test_no_partial_word_bleed(self):
        # "git" is in _SHORT_SKILLS (3 chars, alpha, in COMMON_SKILLS)
        # must not match inside "digital"
        assert not _skill_in_text("git", "experience with digital marketing tools")
        assert _skill_in_text("git", "strong git and version control skills")


# ── _extract_jd_phrases ───────────────────────────────────────────────────────

class TestExtractJdPhrases:
    def test_returns_list(self):
        phrases = _extract_jd_phrases(SAMPLE_JD_ANALYST)
        assert isinstance(phrases, list)

    def test_extracts_known_bigrams(self):
        phrases = _extract_jd_phrases(SAMPLE_JD_ANALYST)
        phrase_set = set(phrases)
        # "financial modeling" should be extracted from SAMPLE_JD_ANALYST
        assert any("financial" in p for p in phrase_set), f"Got: {phrase_set}"

    def test_max_20_phrases(self):
        long_jd = (SAMPLE_JD_ANALYST + "\n") * 5
        assert len(_extract_jd_phrases(long_jd)) <= 20

    def test_empty_input(self):
        assert _extract_jd_phrases("") == []

    def test_no_stop_word_phrases(self):
        phrases = _extract_jd_phrases("and the for with this that have will")
        # All stop words — should produce nothing meaningful
        assert all(len(p.split()) <= 4 for p in phrases)

    def test_pattern_extraction(self):
        jd = "We require experience with financial modeling and proficiency in data analysis."
        phrases = _extract_jd_phrases(jd)
        text = " ".join(phrases)
        assert "financial" in text or "data" in text


# ── get_skill_gaps ────────────────────────────────────────────────────────────

class TestGetSkillGaps:
    def test_returns_two_lists(self):
        matched, missing = get_skill_gaps(SAMPLE_RESUME, SAMPLE_JD_ANALYST)
        assert isinstance(matched, list)
        assert isinstance(missing, list)

    def test_known_matched_skills(self):
        matched, _ = get_skill_gaps(SAMPLE_RESUME, SAMPLE_JD_ANALYST)
        matched_lower = [s.lower() for s in matched]
        assert "python" in matched_lower
        assert "sql" in matched_lower

    def test_unrelated_jd_many_missing(self):
        matched, missing = get_skill_gaps(SAMPLE_RESUME, SAMPLE_JD_UNRELATED)
        # Nursing skills should all be missing
        assert len(missing) >= len(matched) or len(matched) == 0

    def test_empty_resume(self):
        matched, missing = get_skill_gaps("", SAMPLE_JD_ANALYST)
        assert len(matched) == 0
        assert len(missing) > 0

    def test_empty_jd(self):
        matched, missing = get_skill_gaps(SAMPLE_RESUME, "")
        assert matched == []
        assert missing == []

    def test_no_overlap_exact(self):
        matched, missing = get_skill_gaps("no skills here", "python sql excel required")
        assert "python" in missing or len(missing) > 0
        assert len(matched) == 0


# ── ghost_score ───────────────────────────────────────────────────────────────

class TestGhostScore:
    def test_fresh_job_low_score(self):
        score, signals = ghost_score({"date": "2026-04-28", "description": "Great role."})
        assert score < 30, f"Expected <30 for day-old job, got {score}"

    def test_stale_job_moderate_score(self):
        score, signals = ghost_score({"date": "2026-03-01", "description": "Great role."})
        # 59 days old (relative to 2026-04-29)
        assert score >= 30, f"Expected ≥30 for stale job, got {score}"

    def test_very_stale_job_high_score(self):
        score, signals = ghost_score({"date": "2025-12-01", "description": "Great role."})
        assert score >= 60, f"Expected ≥60 for very old job, got {score}"

    def test_pipeline_phrase_raises_score(self):
        job = {
            "date":        "2026-04-25",
            "description": "We are always looking for talented engineers to join our talent pool.",
        }
        score, signals = ghost_score(job)
        assert score >= 20
        assert any("pool" in s.lower() or "pipeline" in s.lower() or "always" in s.lower()
                   for s in signals)

    def test_no_description_adds_signal(self):
        score, signals = ghost_score({"date": "2026-04-25", "description": ""})
        assert score >= 15
        assert any("description" in s.lower() for s in signals)

    def test_returns_tuple_of_int_and_list(self):
        result = ghost_score(SAMPLE_JOB)
        assert isinstance(result, tuple) and len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], list)

    def test_score_capped_at_100(self):
        job = {
            "date":        "2024-01-01",   # very old
            "description": "talent pool pipeline future opportunities always looking",
        }
        score, _ = ghost_score(job)
        assert score <= 100

    def test_missing_date_no_crash(self):
        score, signals = ghost_score({"description": "Exciting role!"})
        assert isinstance(score, int)

    def test_invalid_date_no_crash(self):
        score, signals = ghost_score({"date": "not-a-date", "description": "Cool job"})
        assert isinstance(score, int)


# ── salary_adjusted_score ─────────────────────────────────────────────────────

class TestSalaryAdjustedScore:
    def test_no_profile_returns_base(self):
        score, note = salary_adjusted_score(75, SAMPLE_JOB, None)
        assert score == 75
        assert note == ""

    def test_empty_profile_returns_base(self):
        score, note = salary_adjusted_score(75, SAMPLE_JOB, {})
        assert score == 75
        assert note == ""

    def test_salary_below_target_reduces_score(self):
        # Job pays $30K, user targets $80K — should reduce score and add note
        low_pay_job = {**SAMPLE_JOB, "salary_min": 25_000, "salary_max": 35_000}
        profile = {"min_salary": 70_000, "max_salary": 90_000}
        score, note = salary_adjusted_score(80, low_pay_job, profile)
        assert score < 80
        assert note != ""

    def test_salary_in_range_no_penalty(self):
        profile = {"min_salary": 70_000, "max_salary": 100_000}
        score, note = salary_adjusted_score(80, SAMPLE_JOB, profile)
        assert score == 80

    def test_no_job_salary_no_penalty(self):
        no_sal_job = {**SAMPLE_JOB, "salary_min": None, "salary_max": None}
        profile = {"min_salary": 70_000, "max_salary": 90_000}
        score, note = salary_adjusted_score(80, no_sal_job, profile)
        assert score == 80

    def test_score_never_below_zero(self):
        low_pay_job = {**SAMPLE_JOB, "salary_min": 10_000, "salary_max": 15_000}
        profile = {"min_salary": 200_000, "max_salary": 300_000}
        score, note = salary_adjusted_score(5, low_pay_job, profile)
        assert score >= 0

    def test_note_is_string(self):
        profile = {"min_salary": 70_000, "max_salary": 90_000}
        _, note = salary_adjusted_score(80, SAMPLE_JOB, profile)
        assert isinstance(note, str)


# ── score_job (model-dependent, slow) ────────────────────────────────────────

@pytest.mark.slow
class TestScoreJob:
    def test_high_score_for_matching_resume(self):
        from scorer import score_job
        score = score_job(SAMPLE_RESUME, SAMPLE_JD_ANALYST, "Business Analyst")
        assert score >= 50, f"Expected ≥50 for matching resume/JD, got {score}"

    def test_low_score_for_unrelated_jd(self):
        from scorer import score_job
        score = score_job(SAMPLE_RESUME, SAMPLE_JD_UNRELATED, "Registered Nurse")
        assert score <= 40, f"Expected ≤40 for unrelated JD, got {score}"

    def test_score_bounds(self):
        from scorer import score_job
        score = score_job(SAMPLE_RESUME, SAMPLE_JD_ANALYST, "Analyst")
        assert 0 <= score <= 100

    def test_no_jd_returns_zero(self):
        from scorer import score_job
        assert score_job(SAMPLE_RESUME, "", "Analyst") == 0


# ── batch_score_jobs (model-dependent, slow) ──────────────────────────────────

@pytest.mark.slow
class TestBatchScoreJobs:
    def test_mutates_jobs_in_place(self):
        from scorer import batch_score_jobs
        jobs = [dict(SAMPLE_JOB), dict(SAMPLE_JOB, id="job-002", description="")]
        batch_score_jobs(SAMPLE_RESUME, jobs)
        for j in jobs:
            assert "score" in j
            assert "matched" in j
            assert "missing" in j
            assert "ghost_score" in j
            assert "ghost_signals" in j
            assert "salary_note" in j

    def test_empty_list_no_crash(self):
        from scorer import batch_score_jobs
        batch_score_jobs(SAMPLE_RESUME, [])

    def test_score_types_correct(self):
        from scorer import batch_score_jobs
        jobs = [dict(SAMPLE_JOB)]
        batch_score_jobs(SAMPLE_RESUME, jobs)
        j = jobs[0]
        assert isinstance(j["score"], int)
        assert isinstance(j["matched"], list)
        assert isinstance(j["missing"], list)
        assert isinstance(j["ghost_score"], int)
        assert isinstance(j["ghost_signals"], list)
        assert isinstance(j["salary_note"], str)
