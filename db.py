"""
db.py — Dual-mode database layer.
Uses PostgreSQL (Neon/Supabase via DATABASE_URL env var) on cloud, SQLite locally.
All database files import from here to get the right connection and helpers.
"""
import os
import re
import sqlite3
import threading
from pathlib import Path

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
IS_POSTGRES: bool  = DATABASE_URL.startswith(("postgresql://", "postgres://"))

# SQL placeholder — use db.P in all parameterized queries
P: str = "%s" if IS_POSTGRES else "?"


# ── SQL translation ────────────────────────────────────────────────

def _pg_query(sql: str) -> str:
    """Translate SQLite query syntax → PostgreSQL."""
    sql = sql.replace("?", "%s")
    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", sql, re.I):
        sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
        if "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


def _pg_schema(sql: str) -> str:
    """Translate CREATE TABLE DDL from SQLite → PostgreSQL."""
    sql = _pg_query(sql)
    sql = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\b", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"datetime\('now'\)", "NOW()", sql, flags=re.I)
    return sql


# ── PostgreSQL wrapper ─────────────────────────────────────────────

class _WrappedCursor:
    """Wraps psycopg2 RealDictCursor — fetchone/fetchall return plain dicts."""

    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row else None

    def fetchall(self):
        return [dict(r) for r in (self._cur.fetchall() or [])]

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def lastrowid(self):
        return None  # meaningless for PostgreSQL; use insert_returning()


class _PGConn:
    """
    Wraps psycopg2 connection with a sqlite3-compatible surface.
    Supports `with conn:` (commit/rollback/close on exit).
    """

    def __init__(self):
        import psycopg2
        import psycopg2.extras
        self._raw = psycopg2.connect(DATABASE_URL)
        self._raw.autocommit = False
        self._factory = psycopg2.extras.RealDictCursor

    def execute(self, sql: str, params=()):
        cur = self._raw.cursor(cursor_factory=self._factory)
        cur.execute(_pg_query(sql), params or ())
        return _WrappedCursor(cur)

    def insert_returning(self, sql: str, params=()) -> int | None:
        """Run INSERT and return the new row id via RETURNING id."""
        sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
        sql = _pg_query(sql).rstrip().rstrip(";")
        if "RETURNING" not in sql.upper():
            sql += " RETURNING id"
        cur = self._raw.cursor(cursor_factory=self._factory)
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row["id"] if row else None

    def commit(self):   self._raw.commit()
    def rollback(self): self._raw.rollback()
    def close(self):    self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            try: self.rollback()
            except Exception: pass
        else:
            self.commit()
        self.close()


# ── Public API ─────────────────────────────────────────────────────

def connect(sqlite_path: str | Path | None = None):
    """
    Return a database connection.
      Cloud (DATABASE_URL set): PostgreSQL _PGConn wrapper.
      Local (no DATABASE_URL):  sqlite3.Connection with WAL mode.
    Both support: conn.execute(sql, params), conn.commit(), conn.close(),
    and `with conn:` for transaction management.
    """
    if IS_POSTGRES:
        return _PGConn()
    assert sqlite_path, "sqlite_path is required when DATABASE_URL is not set"
    conn = sqlite3.connect(str(sqlite_path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def insert_returning(conn, sql: str, params=()) -> int | None:
    """
    INSERT and return the new row's id — works for both backends.
    Use this anywhere you need the auto-generated id after an INSERT.
    """
    if IS_POSTGRES:
        return conn.insert_returning(sql, params)
    cur = conn.execute(sql, params)
    return cur.lastrowid


def create_table(conn, sql: str):
    """Run a CREATE TABLE statement, translating DDL for the active backend."""
    if IS_POSTGRES:
        conn.execute(_pg_schema(sql))
    else:
        conn.execute(sql)


def add_column_if_missing(conn, table: str, column: str, definition: str):
    """
    ALTER TABLE … ADD COLUMN, safe to run even if the column already exists.
    Uses IF NOT EXISTS on PostgreSQL; try/except on SQLite.
    """
    if IS_POSTGRES:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
    else:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            conn.commit()
        except Exception:
            pass
