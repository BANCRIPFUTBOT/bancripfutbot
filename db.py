import sqlite3
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "bancripfutbot.db"

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def init_db():
    with conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT,
            symbol TEXT,
            tf TEXT,
            side TEXT,
            price REAL,
            tp REAL,
            sl REAL,
            reason TEXT,
            raw_json TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT DEFAULT 'FREE'
        )
        """)
        c.commit()
