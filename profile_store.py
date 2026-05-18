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
import threading
from datetime import datetime
from pathlib import Path

import db as _db

_db_lock = threading.Lock()
_log = logging.getLogger(__name__)

_SQLITE_PATH = Path(__file__).parent / "applications.db"

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
    return _db.connect(_SQLITE_PATH)


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
        _db.create_table(conn, """
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
        # Seed default profile for user_id=1 if none exists
        existing = conn.execute(f"SELECT id FROM user_profiles WHERE user_id=1").fetchone()
        if not existing:
            seed = _serialize(_DEFAULT_PROFILE)
            seed["updated_at"] = datetime.now().isoformat()
            cols = ", ".join(k for k in seed if k != "user_id")
            placeholders = ", ".join(_db.P for k in seed if k != "user_id")
            vals = [v for k, v in seed.items() if k != "user_id"]
            conn.execute(
                f"INSERT INTO user_profiles (user_id, {cols}) VALUES (1, {placeholders})",
                vals,
            )
        # Schema migrations
        for col, definition in [
            ("portfolio_url",  "TEXT DEFAULT ''"),
            ("star_stories",   "TEXT DEFAULT '[]'"),
        ]:
            _db.add_column_if_missing(conn, "user_profiles", col, definition)
        conn.commit()
        conn.close()


def get_profile(user_id: int = 1) -> dict:
    conn = _connect()
    row = conn.execute(
        f"SELECT * FROM user_profiles WHERE user_id={_db.P}", (user_id,)
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
        data = {k: v for k, v in data.items() if k in _PROFILE_COLS}
        fields = ", ".join(f"{k}={_db.P}" for k in data)
        conn.execute(
            f"UPDATE user_profiles SET {fields} WHERE user_id={_db.P}",
            list(data.values()) + [user_id],
        )
        conn.commit()
        conn.close()


def get_resume_text(user_id: int = 1) -> str:
    conn = _connect()
    row = conn.execute(
        f"SELECT resume_text FROM user_profiles WHERE user_id={_db.P}", (user_id,)
    ).fetchone()
    conn.close()
    return (dict(row).get("resume_text") or "") if row else ""


def set_resume_text(text: str, user_id: int = 1):
    with _db_lock:
        conn = _connect()
        conn.execute(
            f"UPDATE user_profiles SET resume_text={_db.P}, updated_at={_db.P} WHERE user_id={_db.P}",
            (text, datetime.now().isoformat(), user_id),
        )
        conn.commit()
        conn.close()


def get_star_stories(user_id: int = 1) -> list:
    conn = _connect()
    try:
        row = conn.execute(
            f"SELECT star_stories FROM user_profiles WHERE user_id={_db.P}", (user_id,)
        ).fetchone()
    except Exception:
        row = None
    conn.close()
    star_val = dict(row).get("star_stories") if row else None
    if star_val:
        try:
            return json.loads(star_val)
        except Exception:
            return []
    return []


def set_star_stories(stories: list, user_id: int = 1) -> bool:
    """Returns True on success, False on failure. Never silently loses data."""
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                f"UPDATE user_profiles SET star_stories={_db.P}, updated_at={_db.P} WHERE user_id={_db.P}",
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

