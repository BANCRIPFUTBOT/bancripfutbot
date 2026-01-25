from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

TG_TOKEN = os.getenv("TG_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")

import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from binance.client import Client

from binance.client import Client
client = Client(API_KEY, API_SECRET, tld="com")
# Para obtener velas de FUTUROS:
klines = client.futures_klines(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_15MINUTE, limit=200)


# ======================
# CONFIGURACIÓN
# ======================
load_dotenv()

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID")
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

SYMBOL = "BTCUSDT"
MIN_MINUTES_BETWEEN_SIGNALS = 10

last_signal_ts = 0

# Estado de posición
position = {
    "side": "FLAT"  # FLAT / LONG / SHORT
}

# ======================
# UTILIDADES
# ======================
def tg_send(msg: str):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT, "text": msg})

def get_df(client, interval, limit=200):
    kl = client.get_klines(symbol=SYMBOL, interval=interval, limit=limit)
    df = pd.DataFrame(kl, columns=[
        "open_time","open","high","low","close","volume",
        "close_time","qav","trades","tbb","tbq","ignore"
    ])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    return df

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def trend(df):
    e50 = ema(df["close"], 50).iloc[-1]
    e200 = ema(df["close"], 200).iloc[-1]
    if e50 > e200:
        return "BULL"
    if e50 < e200:
        return "BEAR"
    return "RANGE"

def momentum(df):
    e20 = ema(df["close"], 20)
    return e20.iloc[-1] - e20.iloc[-5]

def volatility_high(df):
    ranges = df["high"] - df["low"]
    avg_range = ranges.rolling(20).mean().iloc[-1]
    current_range = ranges.iloc[-1]
    return current_range > avg_range * 1.3

def can_send(is_volatile: bool):
    global last_signal_ts
    now = time.time()
    cooldown = MIN_MINUTES_BETWEEN_SIGNALS * 60

    if is_volatile:
        cooldown = 5 * 60

    if now - last_signal_ts >= cooldown:
        last_signal_ts = now
        return True
    return False

# ======================
# MAIN
# ======================
def main():
    client = Client(API_KEY, API_SECRET)
    tg_send("✅ BANCRIPFUTBOT MTF ONLINE\nActivo: BTCUSDT\nModo: Conservador")

    while True:
        try:
            # Cargar timeframes
            df4h = get_df(client, Client.KLINE_INTERVAL_4HOUR)
            df1h = get_df(client, Client.KLINE_INTERVAL_1HOUR)
            df15 = get_df(client, Client.KLINE_INTERVAL_15MINUTE)
            df5 = get_df(client, Client.KLINE_INTERVAL_5MINUTE)

            t4h = trend(df4h)
            t1h = trend(df1h)

            # Filtro maestro
            if t4h != t1h or t4h == "RANGE":
                time.sleep(60)
                continue

            m15 = momentum(df15)
            m5 = momentum(df5)
            price = df5["close"].iloc[-1]
            is_volatile = volatility_high(df15)

            # ======================
            # ENTRADAS
            # ======================
            if position["side"] == "FLAT":

                # LONG
                if t4h == "BULL" and m15 < 0 and m5 > 0:
                    if can_send(is_volatile):
                        tg_send(
                            f"🟢 BTCUSDT — ENTRAR EN LONG\n"
                            f"Sesgo: Alcista (4H + 1H)\n"
                            f"Estructura: Pullback 15m\n"
                            f"Timing: Confirmación 5m\n"
                            f"Precio ref: {price:.2f}"
                        )
                        position["side"] = "LONG"

                # SHORT
                elif t4h == "BEAR" and m15 > 0 and m5 < 0:
                    if can_send(is_volatile):
                        tg_send(
                            f"🔴 BTCUSDT — ENTRAR EN SHORT\n"
                            f"Sesgo: Bajista (4H + 1H)\n"
                            f"Estructura: Rechazo 15m\n"
                            f"Timing: Confirmación 5m\n"
                            f"Precio ref: {price:.2f}"
                        )
                        position["side"] = "SHORT"

            # ======================
            # CIERRES
            # ======================
            elif position["side"] == "LONG":
                if m15 < 0:
                    if can_send(is_volatile):
                        tg_send(
                            f"✅ BTCUSDT — CERRAR LONG\n"
                            f"Motivo: pérdida de momentum 15m\n"
                            f"Precio ref: {price:.2f}"
                        )
                        position["side"] = "FLAT"

            elif position["side"] == "SHORT":
                if m15 > 0:
                    if can_send(is_volatile):
                        tg_send(
                            f"✅ BTCUSDT — CERRAR SHORT\n"
                            f"Motivo: pérdida de momentum 15m\n"
                            f"Precio ref: {price:.2f}"
                        )
                        position["side"] = "FLAT"

            time.sleep(60)

        except Exception as e:
            tg_send(f"⚠️ Error bot: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()

print("API KEY cargada:", bool(API_KEY))
print("API SECRET cargada:", bool(API_SECRET))

