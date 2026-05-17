"""
analytics.py
------------
Lightweight usage analytics stored in SQLite.
Tracks real events so resume metrics are honest numbers.
"""

import sqlite3, datetime, threading
from pathlib import Path

_DB = Path(__file__).parent / "analytics.db"
_lock = threading.Lock()

def _conn():
    c = sqlite3.connect(_DB, check_same_thread=True, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c

def _init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                event     TEXT    NOT NULL,
                user_id   INTEGER DEFAULT 1,
                meta      TEXT    DEFAULT '',
                ts        TEXT    DEFAULT (datetime('now'))
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date          TEXT PRIMARY KEY,
                active_users  INTEGER DEFAULT 0,
                resumes       INTEGER DEFAULT 0,
                jobs_searched INTEGER DEFAULT 0,
                cover_letters INTEGER DEFAULT 0,
                applications  INTEGER DEFAULT 0
            )
        """)
_init()

def track(event: str, user_id: int = 1, meta: str = ""):
    """Fire-and-forget event tracking. Never raises."""
    try:
        with _lock:
            with _conn() as c:
                c.execute(
                    "INSERT INTO events (event, user_id, meta) VALUES (?,?,?)",
                    (event, user_id, meta)
                )
                _bump_daily(c, event)
    except Exception:
        pass

def _bump_daily(c, event: str):
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
    c.execute(f"""
        INSERT INTO daily_stats (date, {col}) VALUES (?, 1)
        ON CONFLICT(date) DO UPDATE SET {col} = {col} + 1
    """, (today,))

def get_stats() -> dict:
    """Return all-time totals for display."""
    try:
        with _conn() as c:
            totals = c.execute("""
                SELECT
                    COALESCE(SUM(resumes),0)       AS resumes,
                    COALESCE(SUM(jobs_searched),0)  AS jobs_searched,
                    COALESCE(SUM(cover_letters),0)  AS cover_letters,
                    COALESCE(SUM(applications),0)   AS applications,
                    COUNT(DISTINCT date)            AS days_active
                FROM daily_stats
            """).fetchone()
            sessions = c.execute(
                "SELECT COUNT(DISTINCT user_id) FROM events WHERE event='session_start'"
            ).fetchone()[0]
            return {
                "resumes":       totals["resumes"],
                "jobs_searched": totals["jobs_searched"],
                "cover_letters": totals["cover_letters"],
                "applications":  totals["applications"],
                "days_active":   totals["days_active"],
                "sessions":      sessions,
            }
    except Exception:
        return {}

def get_recent_events(limit: int = 20) -> list:
    try:
        with _conn() as c:
            rows = c.execute(
                "SELECT event, user_id, meta, ts FROM events ORDER BY id DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []
