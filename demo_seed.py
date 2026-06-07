"""
demo_seed.py
Idempotent demo data seeder for the Alex Rivera demo account.
Called from auth.ensure_demo_user() on first account creation.
"""

from datetime import date, datetime, timedelta
from pathlib import Path

import db

_APP_DB = Path(__file__).parent / "applications.db"
_ANA_DB = Path(__file__).parent / "analytics.db"


def _app_conn():
    return db.connect(_APP_DB)


def _ana_conn():
    return db.connect(_ANA_DB)


def seed(user_id: int) -> bool:
    """Seed realistic demo data for user_id. Returns True if seeding ran, False if already seeded."""
    conn = _app_conn()
    existing = conn.execute(
        f"SELECT COUNT(*) as cnt FROM applications WHERE user_id={db.P}", (user_id,)
    ).fetchone()
    conn.close()
    if dict(existing)["cnt"] > 0:
        return False

    _seed_profile(user_id)
    _seed_applications(user_id)
    _seed_analytics(user_id)
    _seed_scanner_runs(user_id)
    return True


def _seed_profile(user_id: int):
    import profile_store as _ps
    # Ensure the profile row exists — save_profile() is UPDATE-only
    _ps_conn = db.connect(Path(__file__).parent / "applications.db")
    _ps_conn.execute(
        f"INSERT OR IGNORE INTO user_profiles (user_id) VALUES ({db.P})", (user_id,)
    )
    _ps_conn.commit()
    _ps_conn.close()

    _ps.save_profile(
        {
            "name": "Alex Rivera",
            "email": "alex.rivera@example.com",
            "phone": "(704) 555-0142",
            "linkedin_url": "https://linkedin.com/in/alexrivera-dev",
            "github_url": "https://github.com/alexrivera",
            "portfolio_url": "",
            "current_location": "Charlotte, NC",
            "target_roles": ["Software Engineer", "Full Stack Engineer", "ML Engineer"],
            "target_cities": ["Remote", "Charlotte", "San Francisco", "New York"],
            "target_countries": ["US"],
            "min_salary": 150000,
            "max_salary": 220000,
            "salary_type": "annual",
            "open_to_remote": True,
            "open_to_relocate": True,
            "job_type": "full-time",
            "target_companies": ["Stripe", "Anthropic", "Linear", "Vercel", "Notion"],
            "blacklist_companies": [],
            "work_auth": "US Citizen",
            "graduation_date": "2022-05",
            "school": "NC State University",
            "degree": "B.S.",
            "majors": "Computer Science",
            "years_experience": 3,
            "auto_save_threshold": 70,
            "scan_interval_hours": 4,
            "notify_on_fresh": True,
            "fresh_threshold": 80,
            "resume_text": "",
        },
        user_id=user_id,
    )


def _ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _seed_applications(user_id: int):
    today = date.today()

    apps = [
        {
            "job_id": f"demo_stripe_swe_{user_id}",
            "title": "Senior Software Engineer",
            "company": "Stripe",
            "location": "Remote",
            "url": "https://stripe.com/jobs",
            "score": 91,
            "source": "Adzuna",
            "status": "interview",
            "date_saved": _ago(21),
            "date_applied": _ago(18),
            "salary_min": 175000,
            "salary_max": 225000,
            "notes": "Recruiter screen went well — final round scheduled",
        },
        {
            "job_id": f"demo_anthropic_ml_{user_id}",
            "title": "ML Engineer",
            "company": "Anthropic",
            "location": "San Francisco, CA",
            "url": "https://anthropic.com/jobs",
            "score": 88,
            "source": "LinkedIn",
            "status": "interview",
            "date_saved": _ago(15),
            "date_applied": _ago(12),
            "salary_min": 180000,
            "salary_max": 240000,
            "notes": "Take-home assignment submitted",
        },
        {
            "job_id": f"demo_notion_pm_{user_id}",
            "title": "Product Manager, Platform",
            "company": "Notion",
            "location": "Remote",
            "url": "https://notion.so/jobs",
            "score": 87,
            "source": "Jobicy",
            "status": "applied",
            "date_saved": _ago(17),
            "date_applied": _ago(14),
            "salary_min": 150000,
            "salary_max": 190000,
            "notes": "",
        },
        {
            "job_id": f"demo_linear_fe_{user_id}",
            "title": "Full Stack Engineer",
            "company": "Linear",
            "location": "Remote",
            "url": "https://linear.app/jobs",
            "score": 84,
            "source": "Remotive",
            "status": "offer",
            "date_saved": _ago(28),
            "date_applied": _ago(25),
            "salary_min": 160000,
            "salary_max": 210000,
            "notes": "Offer received — evaluating",
        },
        {
            "job_id": f"demo_vercel_swe_{user_id}",
            "title": "Software Engineer",
            "company": "Vercel",
            "location": "Remote",
            "url": "https://vercel.com/careers",
            "score": 82,
            "source": "Adzuna",
            "status": "applied",
            "date_saved": _ago(11),
            "date_applied": _ago(8),
            "salary_min": 155000,
            "salary_max": 195000,
            "notes": "",
        },
        {
            "job_id": f"demo_plaid_be_{user_id}",
            "title": "Backend Engineer",
            "company": "Plaid",
            "location": "Remote",
            "url": "https://plaid.com/careers",
            "score": 79,
            "source": "Jobicy",
            "status": "saved",
            "date_saved": _ago(4),
            "date_applied": None,
            "salary_min": 160000,
            "salary_max": 200000,
            "notes": "",
        },
        {
            "job_id": f"demo_figma_fe_{user_id}",
            "title": "Senior Frontend Engineer",
            "company": "Figma",
            "location": "San Francisco, CA",
            "url": "https://figma.com/jobs",
            "score": 76,
            "source": "Adzuna",
            "status": "rejected",
            "date_saved": _ago(30),
            "date_applied": _ago(25),
            "salary_min": 170000,
            "salary_max": 220000,
            "notes": "No feedback provided",
        },
        {
            "job_id": f"demo_shopify_em_{user_id}",
            "title": "Engineering Manager",
            "company": "Shopify",
            "location": "Remote",
            "url": "https://shopify.com/careers",
            "score": 74,
            "source": "LinkedIn",
            "status": "applied",
            "date_saved": _ago(9),
            "date_applied": _ago(7),
            "salary_min": 185000,
            "salary_max": 230000,
            "notes": "",
        },
        {
            "job_id": f"demo_github_swe_{user_id}",
            "title": "Software Engineer, Actions",
            "company": "GitHub",
            "location": "Remote",
            "url": "https://github.com/about/careers",
            "score": 73,
            "source": "Remotive",
            "status": "saved",
            "date_saved": _ago(3),
            "date_applied": None,
            "salary_min": 150000,
            "salary_max": 190000,
            "notes": "",
        },
        {
            "job_id": f"demo_hashicorp_devops_{user_id}",
            "title": "Staff DevOps Engineer",
            "company": "HashiCorp",
            "location": "Remote",
            "url": "https://hashicorp.com/jobs",
            "score": 71,
            "source": "Arbeitnow",
            "status": "applied",
            "date_saved": _ago(8),
            "date_applied": _ago(5),
            "salary_min": 165000,
            "salary_max": 205000,
            "notes": "",
        },
    ]

    conn = _app_conn()
    app_ids = {}
    for a in apps:
        cur = conn.execute(
            f"""
            INSERT OR IGNORE INTO applications
                (job_id, title, company, location, url, score, source, status,
                 date_saved, date_applied, notes, salary_min, salary_max, user_id)
            VALUES ({db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},
                    {db.P},{db.P},{db.P},{db.P},{db.P},{db.P})
            """,
            (
                a["job_id"], a["title"], a["company"], a["location"], a["url"],
                a["score"], a["source"], a["status"], a["date_saved"],
                a["date_applied"], a["notes"], a["salary_min"], a["salary_max"],
                user_id,
            ),
        )
        if cur.lastrowid:
            app_ids[a["job_id"]] = cur.lastrowid

    # Seed follow-up schedule for applied/interview rows that are 7+ days old
    for a in apps:
        if a["status"] in ("applied", "interview") and a["date_applied"]:
            applied_date = date.fromisoformat(a["date_applied"])
            if (today - applied_date).days >= 7:
                due = (applied_date + timedelta(days=7)).isoformat()
                row_id = app_ids.get(a["job_id"])
                if row_id:
                    conn.execute(
                        f"""
                        INSERT OR IGNORE INTO followup_schedule
                            (app_id, user_id, due_date, status, created_at)
                        VALUES ({db.P},{db.P},{db.P},{db.P},{db.P})
                        """,
                        (row_id, user_id, due, "pending", datetime.now().isoformat()),
                    )

    conn.commit()
    conn.close()


def _seed_analytics(user_id: int):
    base = date.today() - timedelta(days=14)
    event_schedule = [
        (0, "session_start"), (0, "resume_analyzed"), (0, "resume_uploaded"),
        (1, "session_start"), (1, "jobs_searched"), (1, "application_added"),
        (2, "session_start"), (2, "jobs_searched"), (2, "cover_letter_gen"),
        (3, "jobs_searched"), (3, "application_added"),
        (5, "session_start"), (5, "resume_analyzed"), (5, "jobs_searched"),
        (6, "cover_letter_gen"), (6, "application_added"),
        (8, "session_start"), (8, "jobs_searched"),
        (10, "session_start"), (10, "resume_analyzed"), (10, "cover_letter_gen"),
        (12, "session_start"), (12, "jobs_searched"), (12, "application_added"),
        (14, "session_start"), (14, "resume_analyzed"),
    ]
    conn = _ana_conn()
    for day_offset, event in event_schedule:
        ts = datetime.combine(base + timedelta(days=day_offset), datetime.min.time()).isoformat()
        conn.execute(
            f"INSERT INTO events (event, user_id, meta, ts) VALUES ({db.P},{db.P},{db.P},{db.P})",
            (event, user_id, "", ts),
        )
    conn.commit()
    conn.close()


def _seed_scanner_runs(user_id: int):
    conn = _app_conn()
    runs = [
        (_ago(14), 42, 8, 3, "Charlotte,Remote", "Software Engineer,ML Engineer"),
        (_ago(7), 38, 5, 2, "Remote", "Software Engineer,Backend Engineer"),
        (_ago(1), 51, 11, 6, "Charlotte,Remote", "Software Engineer,DevOps Engineer"),
    ]
    for run in runs:
        conn.execute(
            f"""
            INSERT INTO scanner_runs
                (user_id, run_at, jobs_found, jobs_saved, jobs_notified, cities_scanned, roles_scanned, duration_secs)
            VALUES ({db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P})
            """,
            (user_id, *run, 12.4),
        )
    conn.commit()
    conn.close()
