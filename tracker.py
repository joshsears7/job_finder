import os
import threading
from datetime import datetime
from pathlib import Path

import db

_SQLITE_PATH = Path(__file__).parent / "applications.db"
_db_lock = threading.Lock()

STATUSES = ["saved", "applied", "interview", "offer", "rejected"]


def _connect():
    return db.connect(_SQLITE_PATH)


def init_db():
    conn = _connect()
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS applications (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id         TEXT UNIQUE,
            title          TEXT,
            company        TEXT,
            location       TEXT,
            url            TEXT,
            score          INTEGER DEFAULT 0,
            source         TEXT,
            status         TEXT DEFAULT 'saved',
            date_saved     TEXT,
            date_applied   TEXT,
            notes          TEXT,
            salary_min     REAL,
            salary_max     REAL,
            resume_version TEXT
        )
    """)
    db.add_column_if_missing(conn, "applications", "resume_version", "TEXT")
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS followup_schedule (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            app_id       INTEGER NOT NULL,
            user_id      INTEGER DEFAULT 1,
            due_date     TEXT NOT NULL,
            status       TEXT DEFAULT 'pending',
            draft_text   TEXT DEFAULT '',
            created_at   TEXT,
            completed_at TEXT
        )
    """)
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS scanner_runs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER DEFAULT 1,
            run_at         TEXT,
            jobs_found     INTEGER DEFAULT 0,
            jobs_saved     INTEGER DEFAULT 0,
            jobs_notified  INTEGER DEFAULT 0,
            cities_scanned TEXT DEFAULT '',
            roles_scanned  TEXT DEFAULT '',
            duration_secs  REAL DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


def save_job(job, score=0, resume_version=None):
    with _db_lock:
        conn = _connect()
        cur = conn.execute(f"""
            INSERT OR IGNORE INTO applications
                (job_id, title, company, location, url, score, source, status, date_saved, salary_min, salary_max, resume_version)
            VALUES ({db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},'saved',{db.P},{db.P},{db.P},{db.P})
        """, (
            job["id"], job["title"], job["company"], job["location"],
            job["url"], score, job["source"],
            datetime.now().isoformat()[:10],
            job.get("salary_min"), job.get("salary_max"),
            resume_version,
        ))
        inserted = cur.rowcount > 0
        conn.commit()
        conn.close()
    if inserted:
        try:
            import analytics as _a
            _a.track("application_added", meta=job.get("title", ""))
        except Exception:
            pass
    return inserted


def get_version_stats():
    """Return {version_name: {saved, applied, interview, offer, response_rate}} for A/B tracking."""
    conn = _connect()
    rows = conn.execute(
        "SELECT resume_version, status FROM applications WHERE resume_version IS NOT NULL"
    ).fetchall()
    conn.close()
    from collections import defaultdict
    stats = defaultdict(lambda: {"saved": 0, "applied": 0, "interview": 0, "offer": 0, "rejected": 0})
    for row in rows:
        v, s = row["resume_version"], row["status"]
        if s in stats[v]:
            stats[v][s] += 1
    result = {}
    for v, counts in stats.items():
        total_applied = counts["applied"] + counts["interview"] + counts["offer"] + counts["rejected"]
        responded = counts["interview"] + counts["offer"] + counts["rejected"]
        result[v] = {
            **counts,
            "total": sum(counts.values()),
            "response_rate": round(responded / max(total_applied, 1) * 100),
        }
    return result


def get_all():
    conn = _connect()
    rows = conn.execute("SELECT * FROM applications ORDER BY date_saved DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_status(app_id, status, notes=None):
    with _db_lock:
        conn = _connect()
        if notes is not None:
            conn.execute(f"UPDATE applications SET status={db.P}, notes={db.P} WHERE id={db.P}", (status, notes, app_id))
        else:
            conn.execute(f"UPDATE applications SET status={db.P} WHERE id={db.P}", (status, app_id))
        if status == "applied":
            existing_date = conn.execute(
                f"SELECT date_applied FROM applications WHERE id={db.P}", (app_id,)
            ).fetchone()
            date_applied = dict(existing_date).get("date_applied") if existing_date else None
            if not date_applied:
                today = datetime.now().isoformat()[:10]
                conn.execute(f"UPDATE applications SET date_applied={db.P} WHERE id={db.P}", (today, app_id))
                from datetime import date, timedelta
                due = (date.today() + timedelta(days=7)).isoformat()
                existing_fu = conn.execute(
                    f"SELECT id FROM followup_schedule WHERE app_id={db.P} AND status='pending'", (app_id,)
                ).fetchone()
                if not existing_fu:
                    conn.execute(
                        f"INSERT INTO followup_schedule (app_id, due_date, status, created_at) VALUES ({db.P},{db.P},{db.P},{db.P})",
                        (app_id, due, "pending", datetime.now().isoformat()),
                    )
        conn.commit()
        conn.close()


def delete_app(app_id):
    conn = _connect()
    conn.execute(f"DELETE FROM applications WHERE id={db.P}", (app_id,))
    conn.commit()
    conn.close()


def is_saved(job_id):
    conn = _connect()
    result = conn.execute(f"SELECT id FROM applications WHERE job_id={db.P}", (job_id,)).fetchone()
    conn.close()
    return result is not None


init_db()


# ── Resume Vault ──────────────────────────────────────────────────

def _init_resume_vault():
    conn = _connect()
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS resume_versions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE NOT NULL,
            text       TEXT,
            score      INTEGER DEFAULT 0,
            date_saved TEXT
        )
    """)
    conn.commit()
    conn.close()
    _migrate_vault_from_json()


def _migrate_vault_from_json():
    """One-time migration: import resume_vault.json → SQLite, rename to .migrated."""
    import json
    json_path = os.path.join(os.path.dirname(__file__), "resume_vault.json")
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path) as f:
            data = json.load(f)
        if not data:
            return
        conn = _connect()
        row = conn.execute("SELECT COUNT(*) as cnt FROM resume_versions").fetchone()
        count = dict(row).get("cnt", 0) if row else 0
        if count == 0:
            for name, v in data.items():
                conn.execute(
                    f"INSERT OR IGNORE INTO resume_versions (name, text, score, date_saved) VALUES ({db.P},{db.P},{db.P},{db.P})",
                    (name, v.get("text", ""), v.get("score", 0), v.get("saved", "")),
                )
            conn.commit()
        conn.close()
        os.rename(json_path, json_path + ".migrated")
    except Exception:
        pass


def save_vault_version(name: str, text: str, score: int, date_saved: str = None):
    """Upsert a resume version by name."""
    conn = _connect()
    conn.execute(
        f"""
        INSERT INTO resume_versions (name, text, score, date_saved)
        VALUES ({db.P},{db.P},{db.P},{db.P})
        ON CONFLICT(name) DO UPDATE SET
            text       = excluded.text,
            score      = excluded.score,
            date_saved = excluded.date_saved
        """,
        (name, text, score, date_saved or datetime.now().isoformat()[:10]),
    )
    conn.commit()
    conn.close()


def get_vault() -> dict:
    """Return {name: {text, score, saved}} — drop-in replacement for JSON load."""
    conn = _connect()
    rows = conn.execute(
        "SELECT name, text, score, date_saved FROM resume_versions ORDER BY id"
    ).fetchall()
    conn.close()
    return {r["name"]: {"text": r["text"], "score": r["score"], "saved": r["date_saved"]} for r in rows}


def delete_vault_version(name: str):
    conn = _connect()
    conn.execute(f"DELETE FROM resume_versions WHERE name={db.P}", (name,))
    conn.commit()
    conn.close()


_init_resume_vault()


# ── Network CRM ───────────────────────────────────────────────────

CONTACT_STATUSES = ["warm", "hot", "cold", "reached out", "replied", "met", "referred"]


def _init_contacts():
    conn = _connect()
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS contacts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            company      TEXT,
            role         TEXT,
            how_met      TEXT,
            email        TEXT,
            linkedin     TEXT,
            status       TEXT DEFAULT 'warm',
            next_action  TEXT,
            notes        TEXT,
            date_added   TEXT,
            last_contact TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_contacts()


def save_contact(name, company="", role="", how_met="", email="",
                 linkedin="", status="warm", next_action="", notes=""):
    conn = _connect()
    conn.execute(f"""
        INSERT INTO contacts
            (name, company, role, how_met, email, linkedin, status, next_action, notes, date_added)
        VALUES ({db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P})
    """, (name, company, role, how_met, email, linkedin, status,
          next_action, notes, datetime.now().isoformat()[:10]))
    conn.commit()
    conn.close()


def get_contacts():
    conn = _connect()
    rows = conn.execute("SELECT * FROM contacts ORDER BY date_added DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


_CONTACT_COLS = frozenset({"name","company","role","how_met","email","linkedin",
                            "status","next_action","notes","last_contact"})

def update_contact(contact_id, **kwargs):
    if not kwargs:
        return
    safe = {k: v for k, v in kwargs.items() if k in _CONTACT_COLS}
    if not safe:
        return
    # Hard assertion: every column name must be in the compile-time whitelist.
    # Column names are interpolated into SQL (sqlite3 can't parameterize them),
    # so we verify each one is a known-safe identifier before use.
    for col in safe:
        assert col in _CONTACT_COLS, f"Blocked unsafe column: {col!r}"
    fields = ", ".join(f"{col}={db.P}" for col in safe)
    conn = _connect()
    conn.execute(f"UPDATE contacts SET {fields} WHERE id={db.P}",
                 list(safe.values()) + [contact_id])
    conn.commit()
    conn.close()


def delete_contact(contact_id):
    conn = _connect()
    conn.execute(f"DELETE FROM contacts WHERE id={db.P}", (contact_id,))
    conn.commit()
    conn.close()


# ── Follow-up Schedule ─────────────────────────────────────────────

def get_due_followups(user_id: int = 1) -> list:
    """Return pending follow-ups due today or earlier, joined with application data."""
    from datetime import date
    conn = _connect()
    rows = conn.execute(f"""
        SELECT f.id as followup_id, f.app_id, f.due_date, f.draft_text,
               a.title, a.company, a.url, a.date_applied, a.notes
        FROM followup_schedule f
        JOIN applications a ON a.id = f.app_id
        WHERE f.user_id={db.P} AND f.status='pending' AND f.due_date <= {db.P}
        ORDER BY f.due_date
    """, (user_id, date.today().isoformat())).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_followups(user_id: int = 1) -> list:
    conn = _connect()
    rows = conn.execute(f"""
        SELECT f.*, a.title, a.company, a.date_applied
        FROM followup_schedule f
        JOIN applications a ON a.id = f.app_id
        WHERE f.user_id={db.P}
        ORDER BY f.due_date
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_followup(followup_id: int):
    conn = _connect()
    conn.execute(
        f"UPDATE followup_schedule SET status='sent', completed_at={db.P} WHERE id={db.P}",
        (datetime.now().isoformat(), followup_id),
    )
    conn.commit()
    conn.close()


def skip_followup(followup_id: int):
    conn = _connect()
    conn.execute(
        f"UPDATE followup_schedule SET status='skipped', completed_at={db.P} WHERE id={db.P}",
        (datetime.now().isoformat(), followup_id),
    )
    conn.commit()
    conn.close()


def save_followup_draft(followup_id: int, draft: str):
    conn = _connect()
    conn.execute(
        f"UPDATE followup_schedule SET draft_text={db.P} WHERE id={db.P}", (draft, followup_id)
    )
    conn.commit()
    conn.close()


# ── Job Search Health Score ────────────────────────────────────────

def get_health_score(user_id: int = 1) -> dict:
    """Return pipeline health metrics used by the dashboard Today's Actions tab."""
    from datetime import date, timedelta
    conn = _connect()
    apps = [dict(r) for r in conn.execute(
        "SELECT status, date_applied FROM applications"
    ).fetchall()]
    try:
        row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM followup_schedule WHERE user_id={db.P} AND status='pending' AND due_date <= {db.P}",
            (user_id, date.today().isoformat()),
        ).fetchone()
        due_followups = dict(row).get("cnt", 0) if row else 0
    except Exception:
        due_followups = 0
    conn.close()

    week_ago = (date.today() - timedelta(days=7)).isoformat()
    total_applied    = sum(1 for a in apps if a["status"] in ("applied", "interview", "offer", "rejected"))
    week_applied     = sum(1 for a in apps if a["status"] in ("applied", "interview", "offer", "rejected")
                           and (a.get("date_applied") or "") >= week_ago)
    total_interviews = sum(1 for a in apps if a["status"] in ("interview", "offer"))
    responses        = sum(1 for a in apps if a["status"] in ("interview", "offer", "rejected"))

    response_rate  = round(responses / total_applied * 100) if total_applied else 0
    interview_rate = round(total_interviews / total_applied * 100) if total_applied else 0

    return {
        "total_applied":    total_applied,
        "week_applied":     week_applied,
        "response_rate":    response_rate,
        "total_interviews": total_interviews,
        "interview_rate":   interview_rate,
        "due_followups":    due_followups,
    }


# ── Scanner Log ────────────────────────────────────────────────────

def log_scanner_run(jobs_found=0, jobs_saved=0, jobs_notified=0,
                    cities="", roles="", duration=0.0, user_id=1):
    conn = _connect()
    conn.execute(f"""
        INSERT INTO scanner_runs
            (user_id, run_at, jobs_found, jobs_saved, jobs_notified,
             cities_scanned, roles_scanned, duration_secs)
        VALUES ({db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P},{db.P})
    """, (user_id, datetime.now().isoformat(), jobs_found, jobs_saved,
          jobs_notified, cities, roles, duration))
    conn.commit()
    conn.close()


def get_scanner_runs(limit=10, user_id=1) -> list:
    conn = _connect()
    rows = conn.execute(
        f"SELECT * FROM scanner_runs WHERE user_id={db.P} ORDER BY run_at DESC LIMIT {db.P}",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

