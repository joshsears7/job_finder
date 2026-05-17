"""
profile_store.py
----------------
SQLite-backed personal profile store.
Multi-user ready (user_id column, default=1).
All JSON list fields stored as JSON strings.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime

_db_lock = threading.Lock()
_log = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "applications.db")

_DEFAULT_PROFILE = {
    "user_id": 1,
    "name": "",
    "email": "",
    "phone": "",
    "linkedin_url": "",
    "github_url": "",
    "portfolio_url": "",
    "current_location": "",
    # Job search
    "target_roles": [],
    "target_cities": ["New York", "Remote"],
    "target_countries": ["US"],
    "min_salary": 60000,
    "max_salary": 120000,
    "salary_type": "annual",
    "open_to_remote": True,
    "open_to_relocate": True,
    "job_type": "full-time",
    # Company preferences
    "target_companies": [],
    "blacklist_companies": [],
    # Profile facts
    "work_auth": "US Citizen",
    "graduation_date": "",
    "school": "",
    "degree": "",
    "majors": "",
    "years_experience": 0,
    # Scanner config
    "auto_save_threshold": 60,   # auto-save jobs scoring >= this
    "scan_interval_hours": 4,    # how often background scanner runs
    "notify_on_fresh": True,     # macOS push on new high-score job
    "fresh_threshold": 72,       # score to trigger immediate notification
    # Stored resume text (populated when user uploads resume in app)
    "resume_text": "",
}


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


_JSON_FIELDS = {
    "target_roles", "target_cities", "target_countries",
    "target_companies", "blacklist_companies",
}


def _serialize(profile: dict) -> dict:
    """Convert list fields to JSON strings for storage."""
    out = dict(profile)
    for f in _JSON_FIELDS:
        if f in out and isinstance(out[f], list):
            out[f] = json.dumps(out[f])
    return out


def _deserialize(row: dict) -> dict:
    """Convert JSON string fields back to lists."""
    out = dict(row)
    for f in _JSON_FIELDS:
        if f in out and isinstance(out[f], str):
            try:
                out[f] = json.loads(out[f])
            except Exception:
                out[f] = []
    return out


# Allowed column names for save_profile() — prevents dynamic SQL injection
_PROFILE_COLS = frozenset(_DEFAULT_PROFILE.keys()) | {"updated_at"}


def init_profiles():
    with _db_lock:
        conn = _connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id              INTEGER UNIQUE DEFAULT 1,
                name                 TEXT DEFAULT '',
                email                TEXT DEFAULT '',
                phone                TEXT DEFAULT '',
                linkedin_url         TEXT DEFAULT '',
                github_url           TEXT DEFAULT '',
                portfolio_url        TEXT DEFAULT '',
                current_location     TEXT DEFAULT '',
                target_roles         TEXT DEFAULT '[]',
                target_cities        TEXT DEFAULT '[]',
                target_countries     TEXT DEFAULT '[]',
                min_salary           REAL DEFAULT 0,
                max_salary           REAL DEFAULT 0,
                salary_type          TEXT DEFAULT 'hourly',
                open_to_remote       INTEGER DEFAULT 1,
                open_to_relocate     INTEGER DEFAULT 1,
                job_type             TEXT DEFAULT 'internship',
                target_companies     TEXT DEFAULT '[]',
                blacklist_companies  TEXT DEFAULT '[]',
                work_auth            TEXT DEFAULT '',
                graduation_date      TEXT DEFAULT '',
                school               TEXT DEFAULT '',
                degree               TEXT DEFAULT '',
                majors               TEXT DEFAULT '',
                years_experience     INTEGER DEFAULT 0,
                auto_save_threshold  INTEGER DEFAULT 60,
                scan_interval_hours  INTEGER DEFAULT 4,
                notify_on_fresh      INTEGER DEFAULT 1,
                fresh_threshold      INTEGER DEFAULT 72,
                resume_text          TEXT DEFAULT '',
                star_stories         TEXT DEFAULT '[]',
                updated_at           TEXT DEFAULT ''
            )
        """)
        # Seed default profile if none exists
        existing = conn.execute("SELECT id FROM user_profiles WHERE user_id=1").fetchone()
        if not existing:
            seed = _serialize(_DEFAULT_PROFILE)
            seed["updated_at"] = datetime.now().isoformat()
            cols = ", ".join(k for k in seed if k != "user_id")
            placeholders = ", ".join("?" for k in seed if k != "user_id")
            vals = [v for k, v in seed.items() if k != "user_id"]
            conn.execute(
                f"INSERT INTO user_profiles (user_id, {cols}) VALUES (1, {placeholders})",
                vals,
            )
        # Migrations — add columns that didn't exist in older schema versions
        for col, definition in [
            ("portfolio_url",  "TEXT DEFAULT ''"),
            ("star_stories",   "TEXT DEFAULT '[]'"),
        ]:
            try:
                conn.execute(f"ALTER TABLE user_profiles ADD COLUMN {col} {definition}")
            except Exception:
                pass  # column already exists
        conn.commit()
        conn.close()


def get_profile(user_id: int = 1) -> dict:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if row:
        return _deserialize(dict(row))
    return dict(_DEFAULT_PROFILE)


def save_profile(profile: dict, user_id: int = 1):
    with _db_lock:
        conn = _connect()
        data = _serialize(profile)
        data["updated_at"] = datetime.now().isoformat()
        data.pop("id", None)
        data.pop("user_id", None)
        # Whitelist columns to prevent dynamic SQL injection
        data = {k: v for k, v in data.items() if k in _PROFILE_COLS}
        fields = ", ".join(f"{k}=?" for k in data)
        conn.execute(
            f"UPDATE user_profiles SET {fields} WHERE user_id=?",
            list(data.values()) + [user_id],
        )
        conn.commit()
        conn.close()


def get_resume_text(user_id: int = 1) -> str:
    conn = _connect()
    row = conn.execute(
        "SELECT resume_text FROM user_profiles WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return (row["resume_text"] or "") if row else ""


def set_resume_text(text: str, user_id: int = 1):
    with _db_lock:
        conn = _connect()
        conn.execute(
            "UPDATE user_profiles SET resume_text=?, updated_at=? WHERE user_id=?",
            (text, datetime.now().isoformat(), user_id),
        )
        conn.commit()
        conn.close()


def get_star_stories(user_id: int = 1) -> list:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT star_stories FROM user_profiles WHERE user_id=?", (user_id,)
        ).fetchone()
    except Exception:
        row = None
    conn.close()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except Exception:
            return []
    return []


def set_star_stories(stories: list, user_id: int = 1) -> bool:
    """Returns True on success, False on failure. Never silently loses data."""
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE user_profiles SET star_stories=?, updated_at=? WHERE user_id=?",
                (json.dumps(stories), datetime.now().isoformat(), user_id),
            )
            conn.commit()
            conn.close()
            return True
        except Exception:
            _log.exception("set_star_stories failed for user_id=%s", user_id)
            conn.close()
            return False


init_profiles()

