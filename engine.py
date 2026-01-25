from datetime import datetime, timezone
from config import MAX_SIGNALS_PER_DAY, COOLDOWN_MINUTES, MIN_RR
from storage import load_state, save_state, append_trade
from notifier import send_telegram

def _utc_now():
    return datetime.now(timezone.utc)

def _day_key_utc():
    return _utc_now().strftime("%Y-%m-%d")

def _cooldown_ok(state: dict) -> bool:
    if not state.get("last_signal_ts"):
        return True
    last = datetime.fromisoformat(state["last_signal_ts"])
    delta_min = (_utc_now() - last).total_seconds() / 60
    return delta_min >= COOLDOWN_MINUTES

def _signals_today_ok(state: dict) -> bool:
    day = _day_key_utc()
    if state.get("signals_day") != day:
        state["signals_day"] = day
        state["signals_today"] = 0
    return state["signals_today"] < MAX_SIGNALS_PER_DAY

def _rr_ok(entry: float, tp: float, sl: float, side: str) -> bool:
    # RR = reward / risk
    if side == "BUY":
        reward = abs(tp - entry)
        risk = abs(entry - sl)
    else:
        reward = abs(entry - tp)
        risk = abs(sl - entry)
    if risk == 0:
        return False
    return (reward / risk) >= MIN_RR

def process_signal(payload: dict) -> None:
    """
    payload esperado (desde Pine):
    passphrase, symbol, tf, side, price, tp, sl, reason, time
    side: BUY | SELL | EXIT_LONG | EXIT_SHORT
    """
    state = load_state()

    symbol = str(payload.get("symbol", "N/A"))
    tf = str(payload.get("tf", "N/A"))
    side = str(payload.get("side", "N/A"))
    reason = str(payload.get("reason", "N/A"))

    # Normalizar valores numéricos que llegan como string
    def fnum(x):
        try:
            return float(x)
        except:
            return None

    price = fnum(payload.get("price"))
    tp = fnum(payload.get("tp"))
    sl = fnum(payload.get("sl"))

    # Reset contadores diarios
    _signals_today_ok(state)

    # 1) Manejo de salidas
    if side in ("EXIT_LONG", "EXIT_SHORT"):
        if state["position"] == "FLAT":
            return  # nada que cerrar

        # registrar cierre
        append_trade({
            "type": "EXIT",
            "symbol": symbol,
            "tf": tf,
            "side": side,
            "price": price,
            "state_before": state.copy(),
        })

        send_telegram(
            f"✅ CIERRE\n"
            f"🪙 {symbol} ⏱ {tf}\n"
            f"📌 {side}\n"
            f"💰 Precio: {price}\n"
            f"🧾 {reason}"
        )

        state["position"] = "FLAT"
        state["entry_price"] = None
        state["tp"] = None
        state["sl"] = None
        state["last_signal_ts"] = _utc_now().isoformat()
        save_state(state)
        return

    # 2) Entradas BUY/SELL
    if side not in ("BUY", "SELL"):
        return

    # Bloqueo: solo 1 trade a la vez
    if state["position"] != "FLAT":
        # Si llega una entrada y ya hay posición: ignorar (o podríamos mandar “hold”)
        return

    # Filtros conservadores
    if not _signals_today_ok(state):
        return
    if not _cooldown_ok(state):
        return

    if price is None or tp is None or sl is None:
        return

    if not _rr_ok(price, tp, sl, side):
        # no cumple RR mínimo
        return

    # Registrar entrada
    new_pos = "LONG" if side == "BUY" else "SHORT"

    state["position"] = new_pos
    state["entry_price"] = price
    state["tp"] = tp
    state["sl"] = sl
    state["last_signal_ts"] = _utc_now().isoformat()
    state["signals_today"] = int(state.get("signals_today", 0)) + 1

    save_state(state)

    append_trade({
        "type": "ENTRY",
        "symbol": symbol,
        "tf": tf,
        "side": side,
        "price": price,
        "tp": tp,
        "sl": sl,
        "rr_min": MIN_RR
    })

    send_telegram(
        f"📡 SEÑAL\n"
        f"🪙 {symbol} ⏱ {tf}\n"
        f"📌 {side} ({new_pos})\n"
        f"💰 Entry: {price}\n"
        f"🎯 TP: {tp}\n"
        f"🛑 SL: {sl}\n"
        f"🧠 Filtro: RR≥{MIN_RR} | Señales hoy: {state['signals_today']}/{MAX_SIGNALS_PER_DAY}"
    )
