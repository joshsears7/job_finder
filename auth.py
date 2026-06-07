"""
auth.py
-------
Lightweight multi-user auth for CareerIQ.
Passwords hashed with bcrypt. Backward-compatible with legacy SHA256 hashes.
Works with SQLite locally and PostgreSQL on cloud (via db.py).
"""

import hashlib
import hmac
import os
from pathlib import Path

import bcrypt

import db

_SQLITE_PATH = Path(__file__).parent / "users.db"
DEMO_EMAIL = "demo@careeriq.app"
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")


def _conn():
    return db.connect(_SQLITE_PATH)


def _init():
    with _conn() as c:
        db.create_table(
            c,
            """
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT UNIQUE NOT NULL,
                name       TEXT NOT NULL,
                pwd_hash   TEXT NOT NULL,
                salt       TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """,
        )


_init()


def _hash_bcrypt(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _verify(password: str, stored_hash: str, salt: str) -> bool:
    if stored_hash.startswith(("$2b$", "$2a$")):
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    # Legacy SHA256 path — constant-time comparison prevents timing attacks
    computed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return hmac.compare_digest(computed, stored_hash)


def register(email: str, name: str, password: str) -> dict:
    """Returns {ok, error, user_id}"""
    email = email.strip().lower()
    if not email or not password or not name:
        return {"ok": False, "error": "All fields required."}
    if len(password) < 6:
        return {"ok": False, "error": "Password must be at least 6 characters."}
    conn = _conn()
    try:
        user_id = db.insert_returning(
            conn,
            f"INSERT INTO users (email, name, pwd_hash, salt) VALUES ({db.P},{db.P},{db.P},{db.P})",
            (email, name, _hash_bcrypt(password), "bcrypt"),
        )
        conn.commit()
        return {"ok": True, "user_id": user_id, "name": name}
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "duplicate" in err or "integrity" in err:
            return {"ok": False, "error": "An account with that email already exists."}
        return {"ok": False, "error": "Registration failed — please try again."}
    finally:
        conn.close()


def login(email: str, password: str) -> dict:
    """Returns {ok, error, user_id, name}"""
    email = email.strip().lower()
    conn = _conn()
    try:
        row = conn.execute(
            f"SELECT id, name, pwd_hash, salt FROM users WHERE email={db.P}", (email,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"ok": False, "error": "Invalid email or password."}
    row = dict(row)
    if not _verify(password, row["pwd_hash"], row["salt"]):
        return {"ok": False, "error": "Invalid email or password."}
    return {"ok": True, "user_id": row["id"], "name": row["name"]}


def ensure_demo_user() -> dict:
    """Return {ok, user_id, name} for the shared demo account, creating it if needed."""
    conn = _conn()
    row = conn.execute(f"SELECT id, name FROM users WHERE email={db.P}", (DEMO_EMAIL,)).fetchone()
    if row:
        conn.close()
        row = dict(row)
        try:
            import demo_seed
            demo_seed.seed(row["id"])
        except Exception:
            pass
        return {"ok": True, "user_id": row["id"], "name": row["name"]}
    user_id = db.insert_returning(
        conn,
        f"INSERT INTO users (email, name, pwd_hash, salt) VALUES ({db.P},{db.P},{db.P},{db.P})",
        (DEMO_EMAIL, "Alex Rivera", _hash_bcrypt(DEMO_PASSWORD), "bcrypt"),
    )
    conn.commit()
    conn.close()
    try:
        import demo_seed
        demo_seed.seed(user_id)
    except Exception:
        pass
    return {"ok": True, "user_id": user_id, "name": "Alex Rivera"}


def get_user(user_id: int) -> dict | None:
    conn = _conn()
    row = conn.execute(f"SELECT id, email, name FROM users WHERE id={db.P}", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def user_count() -> int:
    conn = _conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
    conn.close()
    return row["cnt"] if row else 0
