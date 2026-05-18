"""
analytics.py
------------
Lightweight usage analytics. Works with SQLite locally and PostgreSQL on cloud.
"""
import datetime
import threading
from pathlib import Path

import db

_SQLITE_PATH = Path(__file__).parent / "analytics.db"
_lock = threading.Lock()


def _conn():
    return db.connect(_SQLITE_PATH)


def _init():
    conn = _conn()
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS events (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            event     TEXT    NOT NULL,
            user_id   INTEGER DEFAULT 1,
            meta      TEXT    DEFAULT '',
            ts        TEXT    DEFAULT (datetime('now'))
        )
    """)
    db.create_table(conn, """
        CREATE TABLE IF NOT EXISTS daily_stats (
            date          TEXT PRIMARY KEY,
            active_users  INTEGER DEFAULT 0,
            resumes       INTEGER DEFAULT 0,
            jobs_searched INTEGER DEFAULT 0,
            cover_letters INTEGER DEFAULT 0,
            applications  INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()


_init()


def track(event: str, user_id: int = 1, meta: str = ""):
    """Fire-and-forget event tracking. Never raises."""
    try:
        with _lock:
            conn = _conn()
            conn.execute(
                f"INSERT INTO events (event, user_id, meta) VALUES ({db.P},{db.P},{db.P})",
                (event, user_id, meta),
            )
            _bump_daily(conn, event)
            conn.commit()
            conn.close()
    except Exception:
        pass


def _bump_daily(conn, event: str):
    today = datetime.date.today().isoformat()
    col_map = {
        "resume_analyzed":   "resumes",
        "resume_uploaded":   "resumes",
        "jobs_searched":     "jobs_searched",
        "cover_letter_gen":  "cover_letters",
        "application_added": "applications",
        "session_start":     "active_users",
    }
    col = col_map.get(event)
    if not col:
        return
    conn.execute(f"""
        INSERT INTO daily_stats (date, {col}) VALUES ({db.P}, 1)
        ON CONFLICT(date) DO UPDATE SET {col} = {col} + 1
    """, (today,))


def get_stats() -> dict:
    """Return all-time totals for display."""
    try:
        conn = _conn()
        totals = conn.execute("""
            SELECT
                COALESCE(SUM(resumes),0)        AS resumes,
                COALESCE(SUM(jobs_searched),0)  AS jobs_searched,
                COALESCE(SUM(cover_letters),0)  AS cover_letters,
                COALESCE(SUM(applications),0)   AS applications,
                COUNT(DISTINCT date)            AS days_active
            FROM daily_stats
        """).fetchone()
        sessions = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as cnt FROM events WHERE event='session_start'"
        ).fetchone()
        conn.close()
        t = dict(totals) if totals else {}
        return {
            "resumes":       t.get("resumes", 0),
            "jobs_searched": t.get("jobs_searched", 0),
            "cover_letters": t.get("cover_letters", 0),
            "applications":  t.get("applications", 0),
            "days_active":   t.get("days_active", 0),
            "sessions":      (dict(sessions).get("cnt", 0) if sessions else 0),
        }
    except Exception:
        return {}


def get_recent_events(limit: int = 20) -> list:
    try:
        conn = _conn()
        rows = conn.execute(
            f"SELECT event, user_id, meta, ts FROM events ORDER BY id DESC LIMIT {db.P}",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []
