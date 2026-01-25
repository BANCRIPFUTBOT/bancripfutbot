import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "BANCRIPFUTBOT")

# Ajustes de estrategia (modo conservador)
MAX_SIGNALS_PER_DAY = int(os.getenv("MAX_SIGNALS_PER_DAY", "5"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "30"))
MIN_RR = float(os.getenv("MIN_RR", "1.2"))  # mínimo Reward/Risk recomendado
