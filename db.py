import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
LOCAL_SQLITE = os.getenv("SQLITE_PATH", "app.db").strip()

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def _is_postgres():
    return DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

def _normalize_pg_url(url: str) -> str:
    # Render a veces da postgres://, psycopg2 acepta mejor postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url

@contextmanager
def conn():
    """
    Devuelve una conexión con una interfaz 'c.execute(...)' compatible.
    - En SQLite usa sqlite3.
    - En Postgres usa psycopg2 + cursor tipo dict.
    Además convierte placeholders '?' (SQLite) a '%s' (Postgres).
    """
    if _is_postgres():
        import psycopg2
        from psycopg2.extras import RealDictCursor

        url = _normalize_pg_url(DATABASE_URL)

        # Render Postgres suele requerir SSL
        # Si tu DATABASE_URL ya trae ?sslmode=require, no pasa nada.
        if "sslmode=" not in url:
            joiner = "&" if "?" in url else "?"
            url = url + joiner + "sslmode=require"

        pg = psycopg2.connect(url, cursor_factory=RealDictCursor)
        try:
            cur = pg.cursor()

            class PGCompat:
                def execute(self, q, params=()):
                    # Convierte ? ? ? a %s %s %s para Postgres
                    if params is None:
                        params = ()
                    if "?" in q:
                        q = q.replace("?", "%s")
                    cur.execute(q, params)
                    return self

                def fetchone(self):
                    return cur.fetchone()

                def fetchall(self):
                    return cur.fetchall()

                def commit(self):
                    pg.commit()

                def close(self):
                    try:
                        cur.close()
                    except:
                        pass
                    try:
                        pg.close()
                    except:
                        pass

            c = PGCompat()
            yield c
        finally:
            try:
                pg.commit()
            except:
                pass
            try:
                pg.close()
            except:
                pass

    else:
        db = sqlite3.connect(LOCAL_SQLITE)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.commit()
            db.close()

def init_db():
    """
    Crea tablas si no existen.
    Compatible con Postgres y SQLite.
    """
    with conn() as c:
        # users
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """)
        # signals
        c.execute("""
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
        )
        """)
        try:
            c.commit()
        except:
            pass


