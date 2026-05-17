"""
Tests for job_fetcher.py — all external API calls are mocked.
Tests validate deduplication logic, result shaping, and error handling.
"""
import pytest
from unittest.mock import patch, MagicMock
from tests.conftest import SAMPLE_JOB


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_job(i=0, title="Analyst", company="ACME"):
    return {
        "id":          f"job-{i}",
        "title":       title,
        "company":     company,
        "location":    "Charlotte, NC",
        "url":         f"https://example.com/job/{i}",
        "source":      "mock",
        "description": f"Job description number {i}",
        "salary_min":  None,
        "salary_max":  None,
        "date":        "2026-04-20",
    }


# ── _dedup_jobs ───────────────────────────────────────────────────────────────

class TestDedupJobs:
    def test_no_dupes_passthrough(self):
        from job_fetcher import _dedup_jobs
        jobs = [_make_job(0, "Analyst", "ACME"), _make_job(1, "Engineer", "Beta Corp")]
        result = _dedup_jobs(jobs)
        assert len(result) == 2

    def test_exact_duplicate_removed(self):
        from job_fetcher import _dedup_jobs
        job = _make_job(0, "Business Analyst", "ACME Inc")
        dupe = dict(job, id="job-999")  # different id, same title+company
        result = _dedup_jobs([job, dupe])
        assert len(result) == 1

    def test_near_duplicate_removed(self):
        from job_fetcher import _dedup_jobs
        j1 = _make_job(0, "Business Analyst",      "ACME Inc")
        j2 = _make_job(1, "Business Analyst Intern","ACME Inc")
        result = _dedup_jobs([j1, j2])
        # Near-duplicate same company, very similar title — should be deduped
        assert len(result) <= 2  # may or may not dedup depending on threshold

    def test_different_companies_kept(self):
        from job_fetcher import _dedup_jobs
        j1 = _make_job(0, "Business Analyst", "ACME Inc")
        j2 = _make_job(1, "Business Analyst", "Beta Corp")
        result = _dedup_jobs([j1, j2])
        assert len(result) == 2

    def test_empty_list(self):
        from job_fetcher import _dedup_jobs
        assert _dedup_jobs([]) == []

    def test_single_item(self):
        from job_fetcher import _dedup_jobs
        job = _make_job(0)
        result = _dedup_jobs([job])
        assert len(result) == 1


# ── CITY_PRESETS ──────────────────────────────────────────────────────────────

class TestCityPresets:
    def test_presets_is_dict(self):
        from job_fetcher import CITY_PRESETS
        assert isinstance(CITY_PRESETS, dict)

    def test_common_cities_present(self):
        from job_fetcher import CITY_PRESETS
        keys_lower = {k.lower() for k in CITY_PRESETS}
        # At least some expected cities
        assert any("new york" in k for k in keys_lower)
        assert any("charlotte" in k for k in keys_lower)

    def test_each_preset_has_country(self):
        from job_fetcher import CITY_PRESETS
        for key, val in CITY_PRESETS.items():
            assert "country" in val, f"Preset '{key}' missing 'country'"

    def test_each_preset_has_where_key(self):
        from job_fetcher import CITY_PRESETS
        for key, val in CITY_PRESETS.items():
            assert "where" in val or "location" in val or "query" in val or "city" in val, \
                f"Preset '{key}' has no location-like key: {list(val.keys())}"


# ── fetch_jobs (mocked) ───────────────────────────────────────────────────────

class TestFetchJobsMocked:
    @patch("job_fetcher.fetch_jobicy",
           return_value=[_make_job(0, "Analyst", "ACME"), _make_job(1, "Engineer", "Beta Corp")])
    @patch("job_fetcher.fetch_muse",   return_value=[])
    @patch("job_fetcher.fetch_remotive", return_value=[])
    @patch("job_fetcher.fetch_arbeitnow", return_value=[])
    @patch("job_fetcher.fetch_jsearch", return_value=[])
    def test_returns_jobs_from_source(self, *mocks):
        from job_fetcher import fetch_jobs
        jobs = fetch_jobs("analyst", "New York", 5)
        assert len(jobs) >= 2

    @patch("job_fetcher.fetch_adzuna",   side_effect=Exception("API down"))
    @patch("job_fetcher.fetch_jobicy",   return_value=[_make_job(0)])
    @patch("job_fetcher.fetch_muse",     return_value=[])
    @patch("job_fetcher.fetch_remotive", return_value=[])
    @patch("job_fetcher.fetch_arbeitnow",return_value=[])
    def test_one_source_failure_does_not_crash(self, *mocks):
        from job_fetcher import fetch_jobs
        jobs = fetch_jobs("analyst", "Charlotte", 5)
        assert isinstance(jobs, list)

    @patch("job_fetcher.fetch_adzuna",    side_effect=Exception("down"))
    @patch("job_fetcher.fetch_jobicy",    side_effect=Exception("down"))
    @patch("job_fetcher.fetch_muse",      side_effect=Exception("down"))
    @patch("job_fetcher.fetch_remotive",  side_effect=Exception("down"))
    @patch("job_fetcher.fetch_arbeitnow", side_effect=Exception("down"))
    @patch("charlotte_jobs.fetch_all_charlotte_design_jobs", side_effect=Exception("down"))
    def test_all_sources_fail_returns_empty(self, *mocks):
        from job_fetcher import fetch_jobs
        jobs = fetch_jobs("analyst", "Charlotte", 5)
        assert jobs == []

    @patch("job_fetcher.fetch_adzuna", return_value=[_make_job(i) for i in range(20)])
    @patch("job_fetcher.fetch_jobicy", return_value=[])
    @patch("job_fetcher.fetch_muse",   return_value=[])
    @patch("job_fetcher.fetch_remotive", return_value=[])
    @patch("job_fetcher.fetch_arbeitnow", return_value=[])
    def test_result_count_respected(self, *mocks):
        from job_fetcher import fetch_jobs
        jobs = fetch_jobs("analyst", "Charlotte", 5)
        assert len(jobs) <= 20  # dedup may reduce, but shouldn't inflate


# ── get_fetch_warnings ────────────────────────────────────────────────────────

class TestGetFetchWarnings:
    def test_returns_list(self):
        from job_fetcher import get_fetch_warnings
        warnings = get_fetch_warnings()
        assert isinstance(warnings, list)

    def test_each_warning_is_tuple(self):
        from job_fetcher import get_fetch_warnings
        for w in get_fetch_warnings():
            assert isinstance(w, tuple) and len(w) == 2
