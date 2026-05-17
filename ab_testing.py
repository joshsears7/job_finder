"""
ab_testing.py
-------------
Resume A/B testing: track multiple resume versions against real application
outcomes. Correlates version → response rate → interviews → offers.
SQLite-backed, thread-safe.
"""

import sqlite3
import threading
import logging
from datetime import datetime, date

_DB = "ab_testing.db"
_lock = threading.Lock()
_log = logging.getLogger(__name__)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init():
    with _lock:
        conn = _connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS resume_versions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                label       TEXT DEFAULT '',
                raw_text    TEXT NOT NULL,
                summary     TEXT DEFAULT '',
                created_at  TEXT NOT NULL,
                is_active   INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS ab_applications (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id     INTEGER NOT NULL REFERENCES resume_versions(id),
                job_title      TEXT NOT NULL,
                company        TEXT NOT NULL,
                applied_date   TEXT NOT NULL,
                status         TEXT DEFAULT 'applied',
                response_days  INTEGER,
                notes          TEXT DEFAULT '',
                created_at     TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_ab_version ON ab_applications(version_id);
        """)
        conn.commit()
        conn.close()


_init()


# ── Resume versions ───────────────────────────────────────────────

def save_version(name: str, raw_text: str, label: str = "", summary: str = "") -> int:
    """Save a resume version. Returns the new version id."""
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "INSERT INTO resume_versions (name, label, raw_text, summary, created_at) VALUES (?,?,?,?,?)",
            (name, label, raw_text, summary, datetime.utcnow().isoformat()),
        )
        vid = cur.lastrowid
        conn.commit()
        conn.close()
    return vid


def get_versions() -> list[dict]:
    """Return all resume versions sorted by creation date desc."""
    with _lock:
        conn = _connect()
        rows = conn.execute(
            "SELECT * FROM resume_versions ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


def delete_version(version_id: int) -> bool:
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM resume_versions WHERE id=?", (version_id,))
        conn.commit()
        conn.close()
    return True


def update_version_label(version_id: int, label: str):
    with _lock:
        conn = _connect()
        conn.execute("UPDATE resume_versions SET label=? WHERE id=?", (label, version_id))
        conn.commit()
        conn.close()


# ── Applications ──────────────────────────────────────────────────

def log_application(
    version_id: int,
    job_title: str,
    company: str,
    applied_date: str = "",
    notes: str = "",
) -> int:
    """Log an application against a specific resume version. Returns app id."""
    if not applied_date:
        applied_date = date.today().isoformat()
    with _lock:
        conn = _connect()
        cur = conn.execute(
            """INSERT INTO ab_applications
               (version_id, job_title, company, applied_date, notes, created_at)
               VALUES (?,?,?,?,?,?)""",
            (version_id, job_title, company, applied_date, notes,
             datetime.utcnow().isoformat()),
        )
        aid = cur.lastrowid
        conn.commit()
        conn.close()
    return aid


def update_application_status(app_id: int, status: str, response_days: int = None, notes: str = None):
    """Update outcome of an AB application."""
    with _lock:
        conn = _connect()
        if response_days is not None and notes is not None:
            conn.execute(
                "UPDATE ab_applications SET status=?, response_days=?, notes=? WHERE id=?",
                (status, response_days, notes, app_id),
            )
        elif response_days is not None:
            conn.execute(
                "UPDATE ab_applications SET status=?, response_days=? WHERE id=?",
                (status, response_days, app_id),
            )
        elif notes is not None:
            conn.execute(
                "UPDATE ab_applications SET status=?, notes=? WHERE id=?",
                (status, notes, app_id),
            )
        else:
            conn.execute(
                "UPDATE ab_applications SET status=? WHERE id=?",
                (status, app_id),
            )
        conn.commit()
        conn.close()


def get_applications(version_id: int = None) -> list[dict]:
    """Get all AB applications, optionally filtered by version."""
    with _lock:
        conn = _connect()
        if version_id:
            rows = conn.execute(
                "SELECT * FROM ab_applications WHERE version_id=? ORDER BY applied_date DESC",
                (version_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ab_applications ORDER BY applied_date DESC"
            ).fetchall()
        conn.close()
    return [dict(r) for r in rows]


# ── Analytics ─────────────────────────────────────────────────────

def compute_stats() -> list[dict]:
    """
    Compute per-version stats:
    applications, responses (any status != applied), interviews, offers,
    response_rate, avg_response_days.
    """
    versions = get_versions()
    all_apps = get_applications()

    results = []
    for v in versions:
        vid  = v["id"]
        apps = [a for a in all_apps if a["version_id"] == vid]
        if not apps:
            results.append({**v, "apps": 0, "responses": 0, "interviews": 0,
                            "offers": 0, "response_rate": 0, "avg_days": None})
            continue

        responses  = [a for a in apps if a["status"] not in ("applied", "no_response", "rejected_no_response")]
        interviews = [a for a in apps if a["status"] in ("interview", "offer", "accepted")]
        offers     = [a for a in apps if a["status"] in ("offer", "accepted")]
        days_list  = [a["response_days"] for a in apps if a.get("response_days")]

        results.append({
            **v,
            "apps":          len(apps),
            "responses":     len(responses),
            "interviews":    len(interviews),
            "offers":        len(offers),
            "response_rate": round(len(responses) / len(apps) * 100, 1) if apps else 0,
            "avg_days":      round(sum(days_list) / len(days_list), 1) if days_list else None,
        })

    return results


def version_comparison() -> dict:
    """
    Head-to-head version comparison. Returns:
    best_response_rate, best_interview_rate, summary insights.
    """
    stats = compute_stats()
    has_data = [s for s in stats if s["apps"] >= 3]  # min 3 apps to be meaningful

    if len(has_data) < 2:
        return {
            "stats": stats,
            "best_response": None,
            "best_interview": None,
            "insight": "Apply with at least 3 applications per version to get meaningful comparison data.",
        }

    best_resp = max(has_data, key=lambda s: s["response_rate"])
    best_int  = max(has_data, key=lambda s: s["interviews"] / max(s["apps"], 1))

    insight = (
        f"Version '{best_resp['name']}' has the highest response rate ({best_resp['response_rate']}%). "
    )
    if best_int["id"] != best_resp["id"]:
        int_rate = round(best_int["interviews"] / best_int["apps"] * 100, 1)
        insight += f"But '{best_int['name']}' converts more interviews ({int_rate}% of apps reach interview stage)."
    else:
        insight += "It also leads on interview conversion."

    return {
        "stats":          stats,
        "best_response":  best_resp,
        "best_interview": best_int,
        "insight":        insight,
    }
