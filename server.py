import os
import json
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
import requests
from dotenv import load_dotenv

from db import init_db, conn

# -------------------------
# ENV / CONFIG
# -------------------------
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "BANCRIPFUTBOT").strip()

# Mejor que hardcodear:
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_RENDER").strip()

# Admin configurable (en Render lo pones como variables)
ADMIN_USER = os.getenv("ADMIN_USER", "admin").strip()
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123").strip()

# -------------------------
# APP
# -------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Logging (sale bonito en Render)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bancripfutbot")

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


# -------------------------
# HELPERS
# -------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.password_hash = row["password_hash"]
        self.role = row["role"]

@login_manager.user_loader
def load_user(user_id):
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return User(r) if r else None

def ensure_admin():
    """Crea el admin si no existe (ADMIN_USER / ADMIN_PASS)."""
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE username=?", (ADMIN_USER,)).fetchone()
        if not r:
            c.execute(
                "INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                (ADMIN_USER, generate_password_hash(ADMIN_PASS), "ADMIN")
            )
            c.commit()
            log.info("✅ Admin creado: %s", ADMIN_USER)

def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("⚠️ Telegram no configurado (faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID)")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}

    try:
        r = requests.post(url, json=payload, timeout=20)
        log.info("📨 Telegram: %s %s", r.status_code, r.text[:200])
        return r.status_code == 200
    except Exception as e:
        log.exception("❌ Telegram error: %s", e)
        return False

def fnum(x):
    try:
        return float(x)
    except Exception:
        return None

def parse_tv_payload():
    """
    Soporta TradingView:
    - application/json
    - text/plain (raw)
    """
    data = request.get_json(silent=True)
    if data is not None:
        return data

    raw = request.data.decode("utf-8", errors="ignore").strip()
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except Exception:
        return {"raw_message": raw}

def db_insert_signal(ts_utc, symbol, tf, side, price, tp, sl, reason, raw_json):
    with conn() as c:
        c.execute(
            "INSERT INTO signals(ts_utc,symbol,tf,side,price,tp,sl,reason,raw_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (ts_utc, symbol, tf, side, price, tp, sl, reason, raw_json)
        )
        c.commit()


# -------------------------
# ROUTES
# -------------------------
@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "BANCRIPFUTBOT", "ts": utc_now()}), 200

@app.get("/")
def home():
    return jsonify({"status": "BANCRIPFUTBOT PRO ONLINE", "ts": utc_now()}), 200

@app.get("/login")
def login():
    init_db()
    ensure_admin()
    return render_template("login.html")

@app.post("/login")
def login_post():
    init_db()
    ensure_admin()

    u = request.form.get("username", "").strip()
    p = request.form.get("password", "").strip()

    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone()

    if not row or not check_password_hash(row["password_hash"], p):
        flash("Usuario o clave incorrecta")
        return redirect(url_for("login"))

    login_user(User(row))
    return redirect(url_for("dashboard"))

@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.get("/dashboard")
@login_required
def dashboard():
    symbol = request.args.get("symbol", "").strip()
    tf = request.args.get("tf", "").strip()
    side = request.args.get("side", "").strip()

    q = "SELECT * FROM signals WHERE 1=1"
    params = []

    if symbol:
        q += " AND symbol=?"; params.append(symbol)
    if tf:
        q += " AND tf=?"; params.append(tf)
    if side:
        q += " AND side=?"; params.append(side)

    q += " ORDER BY id DESC LIMIT 200"

    with conn() as c:
        rows = c.execute(q, tuple(params)).fetchall()
        total = c.execute("SELECT COUNT(*) n FROM signals").fetchone()["n"]

    return render_template(
        "dashboard.html",
        rows=rows,
        total=total,
        symbol=symbol,
        tf=tf,
        side=side,
        role=current_user.role
    )

@app.post("/webhook")
def webhook():
    init_db()
    ensure_admin()

    data = parse_tv_payload()
    log.info("📩 WEBHOOK RECEIVED: %s", str(data)[:500])

    if not data:
        return jsonify({"ok": False, "error": "empty body"}), 400

    # Caso texto no-JSON
    if "raw_message" in data:
        raw = data.get("raw_message", "")
        db_insert_signal(
            utc_now(), "RAW", "RAW", "RAW", None, None, None,
            "RAW_MESSAGE", json.dumps(data)
        )
        send_telegram("⚠️ TradingView envió texto no-JSON:\n" + raw[:3500])
        return jsonify({"ok": True, "note": "raw_message received"}), 200

    # Validación passphrase
    if str(data.get("passphrase", "")).strip() != WEBHOOK_PASSPHRASE:
        return jsonify({"ok": False, "error": "bad passphrase"}), 403

    # Parse campos
    symbol = str(data.get("symbol", "BTCUSDT")).strip().upper()
    tf = str(data.get("tf", "15m")).strip()
    side = str(data.get("side", "N/A")).strip().upper()
    price = fnum(data.get("price"))
    tp = fnum(data.get("tp"))
    sl = fnum(data.get("sl"))
    reason = str(data.get("reason", "")).strip()

    db_insert_signal(
        utc_now(), symbol, tf, side, price, tp, sl, reason, json.dumps(data)
    )

    icon = "🟢" if side == "BUY" else "🔴" if side == "SELL" else "✅"
    msg = (
        f"{icon} BANCRIPFUT PRO SIGNAL\n"
        f"🪙 {symbol} ⏱ {tf}\n"
        f"📌 {side}\n"
        f"💰 {price}\n"
        f"🎯 TP: {tp}\n"
        f"🛑 SL: {sl}\n"
        f"🧾 {reason}"
    )
    telegram_sent = send_telegram(msg)

    return jsonify({"ok": True, "telegram_sent": telegram_sent}), 200


# -------------------------
# LOCAL RUN (Render usa gunicorn)
# -------------------------
if __name__ == "__main__":
    init_db()
    ensure_admin()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

