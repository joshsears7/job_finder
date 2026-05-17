"""
Tests for salary_intel.py — pure BLS data lookups, no network calls.
"""
import pytest
from salary_intel import estimate, match_role, city_mult, SALARY_DATA


# ── match_role ────────────────────────────────────────────────────────────────

class TestMatchRole:
    def test_exact_key_match(self):
        assert match_role("data analyst") == "data analyst"

    def test_partial_match_in_query(self):
        result = match_role("senior data analyst")
        assert result is not None
        assert "analyst" in result

    def test_partial_match_prefix(self):
        # "data" is in the key "data analyst" — should match
        result = match_role("senior data analyst II")
        assert result is not None

    def test_no_match_returns_none(self):
        result = match_role("underwater basket weaver")
        assert result is None

    def test_software_engineer_match(self):
        result = match_role("software engineer")
        assert result == "software engineer"

    def test_case_insensitive(self):
        result = match_role("Data Scientist")
        assert result == "data scientist"

    def test_all_keys_match_themselves(self):
        for key in SALARY_DATA:
            assert match_role(key) == key, f"Key '{key}' should match itself"


# ── city_mult ─────────────────────────────────────────────────────────────────

class TestCityMult:
    def test_san_francisco_above_one(self):
        mult = city_mult("san francisco")
        assert mult > 1.0, f"SF should cost more than average, got {mult}"

    def test_charlotte_reasonable(self):
        mult = city_mult("charlotte")
        assert 0.7 <= mult <= 1.3, f"Charlotte mult out of range: {mult}"

    def test_unknown_city_returns_one(self):
        assert city_mult("tiny town nobody knows") == 1.0

    def test_case_insensitive(self):
        assert city_mult("New York") == city_mult("new york")

    def test_returns_float(self):
        assert isinstance(city_mult("charlotte"), float)

    def test_no_negative_mult(self):
        for city in ["charlotte", "new york", "san francisco", "chicago", "austin", "raleigh"]:
            assert city_mult(city) > 0


# ── estimate ─────────────────────────────────────────────────────────────────

class TestEstimate:
    def test_known_role_returns_dict(self):
        result = estimate("data analyst", "charlotte", 2)
        assert isinstance(result, dict)

    def test_result_has_required_keys(self):
        result = estimate("business analyst", "charlotte", 3)
        for key in ("p10", "p25", "p50", "p75", "p90", "growth", "notes"):
            assert key in result, f"Missing key: {key}"

    def test_salaries_ordered(self):
        result = estimate("software engineer", "charlotte", 3)
        assert result["p10"] <= result["p25"] <= result["p50"] <= result["p75"] <= result["p90"]

    def test_city_multiplier_applied(self):
        base   = estimate("data analyst", "wichita falls", 2)  # small city → mult ~1.0
        sf     = estimate("data analyst", "san francisco", 2)
        assert sf["p50"] > base["p50"], "SF salary should exceed average"

    def test_experience_senior_higher_than_entry(self):
        entry  = estimate("financial analyst", "new york", 0)
        senior = estimate("financial analyst", "new york", 8)
        assert senior["p50"] >= entry["p50"]

    def test_unknown_role_returns_none(self):
        # estimate returns None when no matching role is found
        result = estimate("underwater basket weaver", "charlotte", 2)
        assert result is None

    def test_salaries_are_positive(self):
        result = estimate("product manager", "seattle", 4)
        for pct in ("p10", "p25", "p50", "p75", "p90"):
            if pct in result and result[pct] is not None:
                assert result[pct] > 0, f"{pct} should be positive"

    def test_all_roles_no_crash(self):
        for role in SALARY_DATA:
            result = estimate(role, "charlotte", 3)
            assert isinstance(result, dict)
