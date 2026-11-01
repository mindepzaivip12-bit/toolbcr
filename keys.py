import hmac, hashlib, time
from typing import Tuple
from config import KEY_SECRET, DURATIONS

def sign_payload(payload: str) -> str:
    return hmac.new(KEY_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:12]

def generate_key(game: str, duration: str) -> str:
    if duration not in DURATIONS:
        raise ValueError("Duration không hợp lệ")
    expire = int(time.time()) + DURATIONS[duration]
    payload = f"{game}-{duration}-{expire}"
    return f"{payload}-{sign_payload(payload)}"

def validate_key(key: str) -> Tuple[bool, str, dict]:
    """Return (ok, message, info)."""
    key = key.strip()
    parts = key.split("-")
    if len(parts) != 4:
        return False, "❌ Định dạng key không đúng.\nVD: bcr-1h-1735689600-a1b2c3d4e5f6", {}
    game, duration, expire_str, sig = parts
    if duration not in DURATIONS:
        return False, "❌ Thời hạn không hợp lệ", {}
    try:
        expire = int(expire_str)
    except ValueError:
        return False, "❌ Timestamp không hợp lệ", {}
    payload = f"{game}-{duration}-{expire}"
    expected = sign_payload(payload)
    if not hmac.compare_digest(expected, sig):
        return False, "❌ Key không hợp lệ (sai chữ ký)", {}
    now = int(time.time())
    if expire < now:
        return False, "❌ Key đã hết hạn", {}
    remain = expire - now
    info = {"game": game, "duration": duration, "expire": expire, "remain": remain}
    remain_str = f"{remain//3600}h{(remain%3600)//60}p" if remain > 3600 else f"{remain//60} phút"
    return True, f"✅ Key hợp lệ · còn {remain_str}", info

def format_remain(seconds: int) -> str:
    if seconds < 60: return f"{seconds}s"
    if seconds < 3600: return f"{seconds//60} phút"
    if seconds < 86400: return f"{seconds//3600}h{(seconds%3600)//60}p"
    return f"{seconds//86400} ngày {(seconds%86400)//3600}h"
