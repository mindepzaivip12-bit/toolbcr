import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8748135141:AAEpu-agcgKG79OMrr-3E-VYw7hNaQCKm4s")

# SECRET dùng để ký key - PHẢI GIỐNG với secret trong generate_key.html
KEY_SECRET = os.getenv("KEY_SECRET", "bontools_bcr_secret_2024_CHANGE_ME")

API_URL = "https://apibcr-t1gk.onrender.com/api/baccarat"
FETCH_TIMEOUT = 8
HTTP_MAX_RETRIES = 2

DURATIONS = {
    "1h":  3600,
    "6h":  21600,
    "1d":  86400,
    "7d":  604800,
    "30d": 2592000,
}

GAMES = {"bcr": "Baccarat"}

# username của bạn (không có @) để nhận lệnh admin, để "" nếu không cần
ADMIN_USERNAME = ""  # ví dụ "your_username"
