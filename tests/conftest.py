"""
Shared fixtures for CareerIQ test suite.
"""
import os
import sys
import sqlite3
import pytest

# Make project root importable without installation
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Sample data ───────────────────────────────────────────────────────────────

SAMPLE_RESUME = """
Joshua Sears
Finance & Analytics Professional | Python · SQL · Excel · Power BI
joshuasears03@att.net · Charlotte, NC

SKILLS
Python, SQL, Excel, Power BI, Tableau, Financial Modeling, Data Analysis,
Project Management, Communication, Stakeholder Management, Agile

EXPERIENCE
Business Analyst — Acme Corp (2023–2025)
- Analyzed financial data using Python and SQL to surface $1.2M in cost savings
- Built Power BI dashboards tracking 12 KPIs for executive leadership
- Led cross-functional project coordinating 5 teams to deliver on-time migration

Data Analyst Intern — StartupCo (2022)
- Queried PostgreSQL databases to support product analytics
- Created Excel models for financial forecasting

EDUCATION
University of North Carolina — B.S. Finance / Data Science (2023)
"""

SAMPLE_JD_ANALYST = """
Business Data Analyst — FinanceCo

We are looking for a Business Analyst with strong Python and SQL skills.
Responsibilities:
- Analyze financial data and build dashboards in Power BI or Tableau
- Collaborate with stakeholders to define KPIs
- Write clean SQL queries for data extraction
- Project management experience a plus

Requirements:
- Experience with Python, SQL, Excel
- Strong communication and stakeholder management skills
- Financial modeling background preferred
- Agile / Scrum familiarity
"""

SAMPLE_JD_UNRELATED = """
Registered Nurse — City Hospital

We seek an experienced RN for our ICU ward.
Must have NCLEX license, 3+ years clinical experience,
IV administration, patient care documentation, HIPAA compliance.
Emergency triage and team collaboration required.
"""

SAMPLE_JOB = {
    "id":          "test-job-001",
    "title":       "Business Analyst",
    "company":     "FinanceCo",
    "location":    "Charlotte, NC",
    "url":         "https://example.com/job/001",
    "source":      "test",
    "description": SAMPLE_JD_ANALYST,
    "salary_min":  70_000,
    "salary_max":  95_000,
    "date":        "2026-04-20",
}


# ── Tracker DB fixture ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """
    Redirect tracker to a fresh temp SQLite DB for each test.
    Returns the db path (rarely needed directly).
    """
    import tracker as tr
    from pathlib import Path

    db_path = tmp_path / "test_applications.db"
    monkeypatch.setattr(tr, "_SQLITE_PATH", db_path)

    # Reinitialize all tables in the temp db
    tr.init_db()
    tr._init_contacts()
    tr._init_resume_vault()
    yield str(db_path)
