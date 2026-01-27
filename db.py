import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Postgres
import psycopg2
from psycopg2.extras import RealDictCursor

DB_PATH = os.getenv("SQLITE_PATH", "app.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _with_sslmode_require(url: str) -> str:
    """
    Render Postgres normalmente requiere SSL. Si no viene sslmode en la URL,
    se lo agregamos como sslmode=require.
    """
    if not url:
        return url
    try:
        u = urlparse(url)
        q = parse_qs(u.query)
        if "sslmode" not in q:
            q["sslmode"] = ["require"]
            new_query = urlencode(q, doseq=True)
            return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))
        return url
    except Exception:
        return url

def _is_postgres() -> bool:
    return DATABASE_URL.lower().startswith(("postgres://", "postgresql://"))

class DBSession:
    """
    Para que tu server.py siga usando:
        with conn() as c:
            c.execute(...)
            c.fetchone()
            c.fetchall()
            c.commit()
    Compatible con SQLite y Postgres.
    """
    def __init__(self):
        self.kind = "postgres" if _is_postgres() else "sqlite"
        self._conn = None
        self._cur = None

    def __enter__(self):
        if self.kind == "postgres":
            url = _with_sslmode_require(DATABASE_URL)
            self._conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
            self._cur = self._conn.cursor()
        else:
            self._conn = sqlite3.connect(DB_PATH)
            self._conn.row_factory = sqlite3.Row
            self._cur = self._conn.cursor()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
        except Exception:
            pass
        try:
            if self._cur:
                self._cur.close()
        except Exception:
            pass
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass

    def execute(self, sql, params=()):
        # SQLite usa ?; Postgres usa %s
        if self.kind == "postgres":
            sql = sql.replace("?", "%s")
        self._cur.execute(sql, params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def commit(self):
        self._conn.commit()

@contextmanager
def conn():
    with DBSession() as s:
        yield s

def init_db():
    """
    Crea tablas si no existen.
    """
    if _is_postgres():
        users_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USER'
        );
        """
        signals_sql = """
        CREATE TABLE IF NOT EXISTS signals (
            id SERIAL PRIMARY KEY,
            ts_utc TEXT NOT NULL,
            symbol TEXT,
            tf TEXT,
            side TEXT,
            price DOUBLE PRECISION,
            tp DOUBLE PRECISION,
            sl DOUBLE PRECISION,
            reason TEXT,
            raw_json TEXT
        );
        """
    else:
        users_sql = """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USER'
        );
        """
        signals_sql = """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            symbol TEXT,
            tf TEXT,
            side TEXT,
            price REAL,
            tp REAL,
            sl REAL,
            reason TEXT,
            raw_json TEXT
        );
        """

    with conn() as c:
        c.execute(users_sql)
        c.execute(signals_sql)
        c.commit()


