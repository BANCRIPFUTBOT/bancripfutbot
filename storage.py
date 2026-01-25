import json
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

STATE_PATH = DATA_DIR / "state.json"
TRADES_PATH = DATA_DIR / "trades.jsonl"

def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "position": "FLAT",       # FLAT | LONG | SHORT
            "entry_price": None,
            "tp": None,
            "sl": None,
            "last_signal_ts": None,
            "signals_today": 0,
            "signals_day": None,      # YYYY-MM-DD
        }
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

def append_trade(event: dict) -> None:
    event["ts"] = event.get("ts") or _utc_now()
    with TRADES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
