import os, json
import hmac, hashlib, time
from collections import OrderedDict

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin, current_user
import requests
from dotenv import load_dotenv

from db import init_db, conn, utc_now


# =========================
# CARGA ENV
# =========================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "BANCRIPFUTBOT").strip()

# ✅ Firma HMAC (seguridad webhook)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").encode("utf-8")
MAX_SKEW = int(os.getenv("WEBHOOK_MAX_SKEW_SECONDS", "120"))  # tolerancia reloj (seg)

SECRET_KEY = os.getenv("SECRET_KEY", "DEV_ONLY_CHANGE_ME").strip()


# =========================
# APP
# =========================
app = Flask(__name__)
app.secret_key = SECRET_KEY

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


# =========================
# USERS (Flask-Login)
# =========================
class User(UserMixin):
    def __init__(self, row):
        # row puede ser sqlite3.Row o dict (postgres)
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
    # crea admin/admin123 si no existe
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE username='admin'").fetchone()
        if not r:
            c.execute(
                "INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                ("admin", generate_password_hash("admin123"), "ADMIN")
            )
            c.commit()

def is_admin():
    return hasattr(current_user, "role") and current_user.role == "ADMIN"


# =========================
# TELEGRAM
# =========================
def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado (faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID)")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=20)
        print("📨 Telegram:", r.status_code, r.text[:200])
        return r.status_code == 200
    except Exception as e:
        print("❌ Telegram error:", e)
        return False


# =========================
# UTILIDADES
# =========================
def fnum(x):
    try:
        return float(x)
    except:
        return None

def parse_tv_payload():
    """
    TradingView a veces manda JSON normal y a veces texto plano.
    """
    data = request.get_json(silent=True)
    if data is None:
        raw = request.data.decode("utf-8", errors="ignore").strip()
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw_message": raw}
        else:
            data = {}
    return data


# =========================
# WEBHOOK SECURITY (HMAC + anti-replay)
# =========================
_NONCE_CACHE = OrderedDict()
_NONCE_LIMIT = 2000

def _clean_nonce_cache():
    while len(_NONCE_CACHE) > _NONCE_LIMIT:
        _NONCE_CACHE.popitem(last=False)

def _seen_nonce(nonce: str) -> bool:
    now = int(time.time())
    # purga nonces viejos (más de 10 min)
    for k, ts in list(_NONCE_CACHE.items()):
        if now - ts > 600:
            _NONCE_CACHE.pop(k, None)
        else:
            break
    if nonce in _NONCE_CACHE:
        return True
    _NONCE_CACHE[nonce] = now
    _clean_nonce_cache()
    return False

def _canonical_payload(data: dict) -> str:
    # JSON determinístico: ordena keys y sin espacios
    return json.dumps(data, separators=(",", ":"), sort_keys=True)

def _hmac_hex(message: str) -> str:
    if not WEBHOOK_SECRET:
        return ""
    return hmac.new(WEBHOOK_SECRET, message.encode("utf-8"), hashlib.sha256).hexdigest()

def verify_webhook_signature(data: dict) -> (bool, str):
    """
    Requiere:
      - ts: unix seconds (int)
      - nonce: string
      - sig: hex hmac sha256 (64 chars)

    Firma = HMAC_SHA256(secret, f"{ts}.{nonce}.{canonical_json_without_sig}")

    canonical_json_without_sig = json compacto (sort_keys) del payload SIN 'sig'
    """
    if not WEBHOOK_SECRET:
        return False, "WEBHOOK_SECRET not set"

    try:
        ts = int(data.get("ts"))
    except Exception:
        return False, "missing/invalid ts"

    nonce = str(data.get("nonce", "")).strip()
    sig = str(data.get("sig", "")).strip().lower()

    if not nonce or len(nonce) < 8:
        return False, "missing/invalid nonce"
    if not sig or len(sig) != 64:
        return False, "missing/invalid sig"

    now = int(time.time())
    if abs(now - ts) > MAX_SKEW:
        return False, f"ts skew too large ({now-ts}s)"

    if _seen_nonce(nonce):
        return False, "replay detected (nonce reused)"

    # Firmamos sin el campo sig
    d2 = dict(data)
    d2.pop("sig", None)

    canon = _canonical_payload(d2)
    msg = f"{ts}.{nonce}.{canon}"
    expected = _hmac_hex(msg)

    if not hmac.compare_digest(expected, sig):
        return False, "bad signature"

    return True, "ok"


# =========================
# ROUTES
# =========================
@app.get("/")
def home():
    return jsonify({"status": "BANCRIPFUTBOT PRO ONLINE"}), 200

@app.get("/health")
def health():
    return jsonify({"ok": True}), 200


# ---- LOGIN UI ----
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


# ---- DASHBOARD ----
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

        buys  = c.execute("SELECT COUNT(*) n FROM signals WHERE side='BUY'").fetchone()["n"]
        sells = c.execute("SELECT COUNT(*) n FROM signals WHERE side='SELL'").fetchone()["n"]

    return render_template(
        "dashboard.html",
        rows=rows,
        total=total,
        symbol=symbol,
        tf=tf,
        side=side,
        role=current_user.role,
        buys=buys,
        sells=sells
    )


# ---- EXPORT ----
@app.get("/export.csv")
@login_required
def export_csv():
    if not is_admin():
        return "Forbidden", 403

    with conn() as c:
        rows = c.execute(
            "SELECT id, ts_utc, symbol, tf, side, price, tp, sl, reason "
            "FROM signals ORDER BY id DESC LIMIT 2000"
        ).fetchall()

    lines = ["id,ts_utc,symbol,tf,side,price,tp,sl,reason"]
    for r in rows:
        reason = (r["reason"] or "").replace('"', '""')
        lines.append(
            f'{r["id"]},{r["ts_utc"]},{r["symbol"]},{r["tf"]},{r["side"]},'
            f'{r["price"]},{r["tp"]},{r["sl"]},"{reason}"'
        )

    return app.response_class("\n".join(lines), mimetype="text/csv")


# ---- WEBHOOK (TradingView) ----
@app.post("/webhook")
def webhook():
    init_db()
    data = parse_tv_payload()
    print("📩 WEBHOOK RECEIVED:", data)

    if not data:
        return jsonify({"ok": False, "error": "empty body"}), 400

    # Si vino texto raro (no JSON)
    if "raw_message" in data:
        raw = data.get("raw_message", "")
        with conn() as c:
            c.execute(
                "INSERT INTO signals(ts_utc,symbol,tf,side,price,tp,sl,reason,raw_json) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (utc_now(), "RAW", "RAW", "RAW", None, None, None, "RAW_MESSAGE", json.dumps(data))
            )
            c.commit()
        send_telegram("⚠️ TradingView mandó texto no-JSON:\n" + raw[:3500])
        return jsonify({"ok": True, "telegram_sent": True, "note": "raw"}), 200

    # 1) passphrase
    if str(data.get("passphrase", "")).strip() != WEBHOOK_PASSPHRASE:
        return jsonify({"ok": False, "error": "bad passphrase"}), 403

    # 2) firma HMAC (ts/nonce/sig)
    ok_sig, why = verify_webhook_signature(data)
    if not ok_sig:
        return jsonify({"ok": False, "error": "bad_signature", "detail": why}), 403

    # 3) campos
    symbol = str(data.get("symbol", "BTCUSDT"))
    tf     = str(data.get("tf", "15m"))
    side   = str(data.get("side", "N/A")).upper()
    price  = fnum(data.get("price"))
    tp     = fnum(data.get("tp"))
    sl     = fnum(data.get("sl"))
    reason = str(data.get("reason", ""))

    # 4) guardar en DB
    with conn() as c:
        c.execute(
            "INSERT INTO signals(ts_utc,symbol,tf,side,price,tp,sl,reason,raw_json) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (utc_now(), symbol, tf, side, price, tp, sl, reason, json.dumps(data))
        )
        c.commit()

    # 5) enviar Telegram
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


# =========================
# RUN LOCAL
# =========================
if __name__ == "__main__":
    init_db()
    ensure_admin()
    port = int(os.getenv("PORT", "5000"))
    print(f"🚀 BANCRIPFUTBOT PRO iniciando en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
