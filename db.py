import os
import sqlite3
from urllib.parse import urlparse
from datetime import datetime, timezone

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def _sqlite_conn():
    # SQLite local (fallback)
    db_path = os.path.join(os.path.dirname(__file__), "data", "bancripfutbot.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c

def _postgres_conn():
    """
    Postgres via DATABASE_URL (Render).
    Usa psycopg2-binary.
    """
    import psycopg2
    import psycopg2.extras

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL vacío")

    # Render a veces usa postgres:// (ok). En algunos servicios puede venir postgresql://
    parsed = urlparse(url)
    dbname = parsed.path.lstrip("/")
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432

    conn = psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port,
        sslmode=os.getenv("PGSSLMODE", "require"),
    )
    conn.autocommit = True
    return conn

def conn():
    """
    Devuelve un context manager-like para usar con `with conn() as c:`
    - SQLite: devuelve connection sqlite
    - Postgres: devuelve connection psycopg2
    """
    db_url = os.getenv("DATABASE_URL", "").strip()
    if db_url:
        return _postgres_conn()
    return _sqlite_conn()

def init_db():
    """
    Crea tablas si no existen.
    Soporta SQLite y Postgres.
    """
    db_url = os.getenv("DATABASE_URL", "").strip()

    if db_url:
        # POSTGRES
        with conn() as c:
            cur = c.cursor(cursor_factory=None)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'USER'
                );
            """)
            cur.execute("""
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
            """)
        return

    # SQLITE
    with conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER'
            );
        """)
        c.execute("""
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
        """)
        c.commit()

