"""
BANCRIPFUTBOT PRO - Webhook Server (Plataforma PRO v1)
- Recibe señales desde TradingView (JSON)
- Valida passphrase
- Procesa con engine.py (filtros RR, cooldown, etc.)
- Guarda historial persistente (data/trades.jsonl)
- Endpoints: /, /webhook, /signals, /stats
"""
import os
import json
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Cargar .env
load_dotenv()

# Importar tu motor y almacenamiento (están en la carpeta raíz)
from engine import process_signal
from storage import append_trade

app = Flask(__name__)

WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "BANCRIPFUTBOT").strip()

@app.route("/")
def home():
    return jsonify({"status": "BANCRIPFUTBOT PRO ONLINE"}), 200

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"message": "Use POST para enviar señales"}), 200

    data = request.get_json(silent=True) or {}
    print("📩 Webhook recibido:", json.dumps(data, indent=2))

    # 1) Validar passphrase
    if str(data.get("passphrase", "")).strip() != WEBHOOK_PASSPHRASE:
        return jsonify({"ok": False, "error": "bad passphrase"}), 403

    # 2) Guardar evento RAW (persistente)
    append_trade({
        "type": "WEBHOOK_RAW",
        "payload": data,
        "ts_local": time.strftime("%Y-%m-%d %H:%M:%S")
    })

    # 3) Procesar con engine (manda Telegram, aplica filtros, guarda ENTRY/EXIT)
    try:
        process_signal(data)
    except Exception as e:
        print("❌ Error en process_signal:", str(e))
        append_trade({
            "type": "ERROR",
            "error": str(e),
            "payload": data
        })
        return jsonify({"ok": False, "error": "engine_failed", "detail": str(e)}), 500

    return jsonify({"ok": True}), 200

@app.route("/signals", methods=["GET"])
def get_signals():
    """
    Devuelve últimas N entradas del log trades.jsonl
    """
    limit = min(int(request.args.get("limit", 20)), 200)

    # Leer archivo JSONL
    path = os.path.join(os.path.dirname(__file__), "..", "data", "trades.jsonl")
    path = os.path.abspath(path)

    if not os.path.exists(path):
        return jsonify({"total": 0, "signals": []}), 200

    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(line)

    total = len(lines)
    last = lines[-limit:] if total > 0 else []
    parsed = []
    for s in last:
        try:
            parsed.append(json.loads(s))
        except:
            pass

    return jsonify({"total": total, "signals": parsed}), 200

@app.route("/stats", methods=["GET"])
def stats():
    """
    Estadísticas básicas (rápidas):
    - total eventos
    - conteo por type: ENTRY/EXIT/WEBHOOK_RAW/ERROR
    - conteo por side: BUY/SELL/EXIT_LONG/EXIT_SHORT
    """
    path = os.path.join(os.path.dirname(__file__), "..", "data", "trades.jsonl")
    path = os.path.abspath(path)

    if not os.path.exists(path):
        return jsonify({"total": 0, "by_type": {}, "by_side": {}}), 200

    by_type = {}
    by_side = {}
    total = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                obj = json.loads(line)
            except:
                continue

            t = obj.get("type", "UNKNOWN")
            by_type[t] = by_type.get(t, 0) + 1

            # side puede venir en ENTRY o en payload
            side = obj.get("side")
            if not side:
                payload = obj.get("payload", {})
                if isinstance(payload, dict):
                    side = payload.get("side")
            if side:
                by_side[str(side)] = by_side.get(str(side), 0) + 1

    return jsonify({
        "total": total,
        "by_type": by_type,
        "by_side": by_side
    }), 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 BANCRIPFUTBOT PRO (Plataforma) iniciando en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
