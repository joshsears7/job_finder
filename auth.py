"""
auth.py
-------
Lightweight multi-user auth for CareerIQ.
Passwords hashed with bcrypt. Backward-compatible with legacy SHA256 hashes.
"""
import sqlite3, hashlib, secrets, os
import bcrypt
from pathlib import Path

_DB = Path(__file__).parent / "users.db"
DEMO_EMAIL    = "demo@careeriq.app"
DEMO_PASSWORD = "demo1234"

def _conn():
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    return c

def _init():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                email      TEXT UNIQUE NOT NULL,
                name       TEXT NOT NULL,
                pwd_hash   TEXT NOT NULL,
                salt       TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
_init()

def _hash_bcrypt(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def _verify(password: str, stored_hash: str, salt: str) -> bool:
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        return bcrypt.checkpw(password.encode(), stored_hash.encode())
    # Legacy SHA256 path
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest() == stored_hash

def register(email: str, name: str, password: str) -> dict:
    """Returns {ok, error, user_id}"""
    email = email.strip().lower()
    if not email or not password or not name:
        return {"ok": False, "error": "All fields required."}
    if len(password) < 6:
        return {"ok": False, "error": "Password must be at least 6 characters."}
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO users (email, name, pwd_hash, salt) VALUES (?,?,?,?)",
                (email, name, _hash_bcrypt(password), "bcrypt")
            )
            return {"ok": True, "user_id": cur.lastrowid, "name": name}
    except sqlite3.IntegrityError:
        return {"ok": False, "error": "An account with that email already exists."}

def login(email: str, password: str) -> dict:
    """Returns {ok, error, user_id, name}"""
    email = email.strip().lower()
    with _conn() as c:
        row = c.execute(
            "SELECT id, name, pwd_hash, salt FROM users WHERE email=?", (email,)
        ).fetchone()
    if not row:
        return {"ok": False, "error": "No account found for that email."}
    if not _verify(password, row["pwd_hash"], row["salt"]):
        return {"ok": False, "error": "Incorrect password."}
    return {"ok": True, "user_id": row["id"], "name": row["name"]}

def ensure_demo_user() -> dict:
    """Return {ok, user_id, name} for the shared demo account, creating it if needed."""
    with _conn() as c:
        row = c.execute("SELECT id, name FROM users WHERE email=?", (DEMO_EMAIL,)).fetchone()
        if row:
            return {"ok": True, "user_id": row["id"], "name": row["name"]}
        cur = c.execute(
            "INSERT INTO users (email, name, pwd_hash, salt) VALUES (?,?,?,?)",
            (DEMO_EMAIL, "Alex Rivera", _hash_bcrypt(DEMO_PASSWORD), "bcrypt")
        )
        return {"ok": True, "user_id": cur.lastrowid, "name": "Alex Rivera"}

def get_user(user_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT id, email, name FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None

def user_count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
