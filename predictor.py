import math
from typing import List, Optional, Tuple

# ============ HELPERS ============
def cmp_id(a, b):
    try:
        ai, bi = int(a), int(b)
        return (ai > bi) - (ai < bi)
    except Exception:
        sa, sb = str(a), str(b)
        return (sa > sb) - (sa < sb)

def result_to_history(result: str) -> List[str]:
    """API trả string 'BPTP...' oldest-first. Tách B/P (bỏ T), reverse → newest first."""
    if not result:
        return []
    chars = [c for c in result if c in ("B", "P")]
    chars.reverse()
    return ["T" if c == "B" else "X" for c in chars]

def result_char_label(c: str) -> str:
    return {"B": "Cái", "P": "Con", "T": "Hòa"}.get(c, "—")

# ============ CÁC THUẬT TOÁN ============
def freq_vote(h, w, mode):
    if len(h) < w: return None
    t = sum(1 for i in range(w) if h[i] == "T")
    r = t / w
    s = abs(r - 0.5) * 2
    if s < 0.06: return None
    if mode == "maj":
        return ("T" if r > 0.5 else "X", s)
    return ("X" if r > 0.5 else "T", s)

def streak_vote(h, min_s, mode):
    if len(h) < min_s + 1: return None
    last = h[0]
    s = 1
    while s < len(h) and h[s] == last:
        s += 1
    if s < min_s: return None
    w = min(1.0, 0.2 + 0.12 * (s - min_s + 1))
    if mode == "brk":
        return ("X" if last == "T" else "T", w)
    return (last, w)

def reversion_vote(h, w, thresh):
    if len(h) < w: return None
    t = sum(1 for i in range(w) if h[i] == "T")
    r = t / w
    if r >= thresh:
        return ("X", min(1.0, (r - 0.5) * 2))
    if r <= 1 - thresh:
        return ("T", min(1.0, (0.5 - r) * 2))
    return None

def ema_vote(h, sp, lp):
    if len(h) < lp: return None
    a_s = 2 / (sp + 1)
    a_l = 2 / (lp + 1)
    e_s = 1.0 if h[-1] == "T" else 0.0
    e_l = e_s
    for i in range(len(h) - 2, -1, -1):
        v = 1.0 if h[i] == "T" else 0.0
        e_s = v * a_s + e_s * (1 - a_s)
        e_l = v * a_l + e_l * (1 - a_l)
    diff = e_s - e_l
    if abs(diff) < 0.03: return None
    return ("T" if diff > 0 else "X", min(1.0, abs(diff) * 6))

def momentum_vote(h, w):
    if len(h) < w: return None
    half = (w + 1) // 2
    t_r = sum(1 for i in range(half) if h[i] == "T")
    t_o = sum(1 for i in range(half, w) if h[i] == "T")
    diff = t_r / half - t_o / (w - half)
    if abs(diff) < 0.12: return None
    return ("T" if diff > 0 else "X", min(1.0, abs(diff) * 3))

def markov_vote(h, order):
    if len(h) < order + 5: return None
    state = "".join(h[:order])
    t = x = 0
    for i in range(order, len(h) - 1):
        match = all(h[i + k] == state[k] for k in range(order))
        if match:
            if h[i - 1] == "T": t += 1
            else: x += 1
    total = t + x
    if total < 3: return None
    r = t / total
    if abs(r - 0.5) < 0.08: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2 * min(1, total / 8))

def ngram_vote(h, n):
    if len(h) < n + 4: return None
    pattern = "".join(h[:n])
    t = x = 0
    for i in range(n, len(h) - n + 1):
        match = all(h[i + k] == pattern[k] for k in range(n))
        if match:
            if h[i - 1] == "T": t += 1
            else: x += 1
    total = t + x
    if total < 2: return None
    r = t / total
    if abs(r - 0.5) < 0.06: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2 * min(1, total / 5))

def seasonal_vote(h, period, offset):
    if len(h) < period * 2: return None
    t = c = 0
    for i in range(offset, len(h), period):
        if h[i] == "T": t += 1
        c += 1
    if c < 3: return None
    r = t / c
    if abs(r - 0.5) < 0.08: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2)

def pattern_vote(h, n, w):
    if len(h) < n + 3: return None
    pattern = "".join(h[:n])
    t = x = 0
    lim = min(w, len(h) - n)
    for i in range(1, lim + 1):
        match = all(h[i + k] == pattern[k] for k in range(n))
        if match:
            if h[i - 1] == "T": t += 1
            else: x += 1
    total = t + x
    if total < 2: return None
    r = t / total
    if abs(r - 0.5) < 0.06: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2 * min(1, total / 6))

def alt_vote(h, w):
    if len(h) < w: return None
    flips = sum(1 for i in range(1, w) if h[i] != h[i - 1])
    rate = flips / (w - 1)
    if rate < 0.7: return None
    return ("X" if h[0] == "T" else "T", min(1.0, (rate - 0.5) * 2.5))

def zigzag_vote(h, w):
    if len(h) < w: return None
    flips = sum(1 for i in range(1, w) if h[i] != h[i - 1])
    rate = flips / (w - 1)
    if rate < 0.5 or rate > 0.7: return None
    return ("X" if h[0] == "T" else "T", min(1.0, (rate - 0.4) * 1.8))

def follow_vote(h, w, mode):
    if len(h) < w: return None
    t = sum(1 for i in range(w) if h[i] == "T")
    r = t / w
    if abs(r - 0.5) < 0.12: return None
    wgt = abs(r - 0.5) * 2
    if mode == "win":
        return ("T" if r > 0.5 else "X", wgt)
    return ("X" if r > 0.5 else "T", wgt)

def bigram_vote(h, w):
    if len(h) < 5: return None
    bg = h[0] + h[1]
    t = x = 0
    lim = min(w, len(h) - 2)
    for i in range(2, lim + 1):
        if h[i] + h[i + 1] == bg:
            if h[i - 1] == "T": t += 1
            else: x += 1
    total = t + x
    if total < 2: return None
    r = t / total
    if abs(r - 0.5) < 0.1: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2 * min(1, total / 4))

def trigram_vote(h, w):
    if len(h) < 6: return None
    tg = h[0] + h[1] + h[2]
    t = x = 0
    lim = min(w, len(h) - 3)
    for i in range(3, lim + 1):
        if h[i] + h[i + 1] + h[i + 2] == tg:
            if h[i - 1] == "T": t += 1
            else: x += 1
    total = t + x
    if total < 2: return None
    r = t / total
    if abs(r - 0.5) < 0.1: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2 * min(1, total / 3))

def weighted_vote(h, decay):
    if len(h) < 5: return None
    t = x = 0.0
    for i in range(len(h)):
        w = decay ** i
        if h[i] == "T": t += w
        else: x += w
    total = t + x
    if total == 0: return None
    r = t / total
    if abs(r - 0.5) < 0.04: return None
    return ("T" if r > 0.5 else "X", abs(r - 0.5) * 2)

# ============ SINH ~800 THUẬT TOÁN ============
ALGOS = []
for w in range(2, 61):
    ALGOS.append(lambda h, w=w: freq_vote(h, w, "maj"))
    ALGOS.append(lambda h, w=w: freq_vote(h, w, "min"))
for s in range(2, 13):
    ALGOS.append(lambda h, s=s: streak_vote(h, s, "brk"))
    ALGOS.append(lambda h, s=s: streak_vote(h, s, "cont"))
for ti in range(15):
    th = 0.55 + ti * 0.02
    for w in range(5, 51, 5):
        ALGOS.append(lambda h, w=w, th=th: reversion_vote(h, w, th))
for sp in range(2, 16):
    for lp in range(sp + 3, 36, 3):
        ALGOS.append(lambda h, sp=sp, lp=lp: ema_vote(h, sp, lp))
for w in range(2, 41):
    ALGOS.append(lambda h, w=w: momentum_vote(h, w))
for o in range(1, 11):
    ALGOS.append(lambda h, o=o: markov_vote(h, o))
for n in range(2, 18):
    ALGOS.append(lambda h, n=n: ngram_vote(h, n))
for m in range(2, 19):
    for off in range(m):
        ALGOS.append(lambda h, m=m, off=off: seasonal_vote(h, m, off))
for n in range(2, 9):
    for w in range(10, 51, 10):
        ALGOS.append(lambda h, n=n, w=w: pattern_vote(h, n, w))
for w in range(4, 24):
    ALGOS.append(lambda h, w=w: alt_vote(h, w))
for w in range(4, 24):
    ALGOS.append(lambda h, w=w: zigzag_vote(h, w))
for w in range(4, 24):
    ALGOS.append(lambda h, w=w: follow_vote(h, w, "win"))
    ALGOS.append(lambda h, w=w: follow_vote(h, w, "lose"))
for w in range(10, 61, 5):
    ALGOS.append(lambda h, w=w: bigram_vote(h, w))
for w in range(10, 61, 5):
    ALGOS.append(lambda h, w=w: trigram_vote(h, w))
d = 0.5
while d <= 0.9501:
    dd = d
    ALGOS.append(lambda h, dd=dd: weighted_vote(h, dd))
    d += 0.025

BACKTEST_ALGOS = [a for i, a in enumerate(ALGOS) if i % 5 == 0]

# ============ ENSEMBLE / BACKTEST / TREND ============
def ensemble_vote(history, algos=None):
    algos = algos or ALGOS
    if len(history) < 12: return None
    t_w = x_w = 0.0
    for fn in algos:
        v = fn(history)
        if not v: continue
        pred, wgt = v
        if pred == "T": t_w += wgt
        else: x_w += wgt
    total = t_w + x_w
    if total < 0.5: return None
    dominant = "T" if t_w > x_w else "X"
    margin = abs(t_w - x_w) / total
    return {"pred": dominant, "margin": margin}

def backtest(history, max_steps=8, window=40):
    correct = total = 0
    lim = min(max_steps, len(history) - 12)
    for i in range(max(0, lim)):
        prior = history[i + 1: i + 1 + window]
        if len(prior) < 12: break
        actual = history[i]
        v = ensemble_vote(prior, BACKTEST_ALGOS)
        if v:
            total += 1
            if v["pred"] == actual: correct += 1
    return {"accuracy": correct / total if total else None, "tested": total, "correct": correct}

def ema_of(history, period):
    if not history: return 0.0
    if len(history) == 1: return 1.0 if history[0] == "T" else 0.0
    a = 2 / (period + 1)
    e = 1.0 if history[-1] == "T" else 0.0
    for i in range(len(history) - 2, -1, -1):
        v = 1.0 if history[i] == "T" else 0.0
        e = v * a + e * (1 - a)
    return e

class Trend:
    BUILDING = "BUILDING"
    CONFIRMED = "CONFIRMED"
    EXTENDED = "EXTENDED"
    CHAOTIC = "CHAOTIC"

def detect_trend(history):
    if len(history) < 8:
        return {"state": Trend.BUILDING, "direction": "neutral", "strength": 0.0,
                "streak": 0, "flipRate": 0.5, "tRate": 0.5, "slope": 0.0}
    last = history[0]
    streak = 1
    while streak < len(history) and history[streak] == last:
        streak += 1
    win = min(20, len(history) - 1)
    flips = sum(1 for i in range(1, win + 1) if history[i] != history[i - 1])
    flip_rate = flips / win if win > 0 else 0.5
    w20 = history[:min(20, len(history))]
    t_rate = sum(1 for v in w20 if v == "T") / len(w20)
    ema5, ema15 = ema_of(history, 5), ema_of(history, 15)
    slope = ema5 - ema15
    state, direction, strength = "", "neutral", 0.0
    if flip_rate > 0.6 and len(history) >= 15:
        state, strength = Trend.CHAOTIC, 0.3
    elif streak >= 5:
        state, direction = Trend.EXTENDED, last
        strength = min(1.0, 0.55 + (streak - 5) * 0.1)
    elif streak >= 3:
        state, direction = Trend.CONFIRMED, last
        strength = min(1.0, 0.45 + (streak - 3) * 0.15)
    else:
        state = Trend.BUILDING
        if abs(t_rate - 0.5) > 0.1:
            direction = "T" if t_rate > 0.5 else "X"
            strength = min(1.0, abs(t_rate - 0.5) * 2)
        else:
            strength = max(0.0, min(1.0, abs(slope) * 4))
    return {"state": state, "direction": direction, "strength": strength,
            "streak": streak, "flipRate": flip_rate, "tRate": t_rate, "slope": slope}

def trend_strategy_decision(trend, history):
    s = trend["state"]
    if s == Trend.CONFIRMED: return trend["direction"]
    if s == Trend.EXTENDED:  return "X" if trend["direction"] == "T" else "T"
    if s == Trend.CHAOTIC:   return "X" if history[0] == "T" else "T"
    return None

def trend_strategy_vote(history):
    if len(history) < 20: return None
    correct = tested = 0
    max_test = min(12, len(history) - 12)
    for i in range(max(0, max_test)):
        prior = history[i + 1: i + 1 + 40]
        if len(prior) < 12: break
        t = detect_trend(prior)
        v = trend_strategy_decision(t, prior)
        if v:
            tested += 1
            if v == history[i]: correct += 1
    accuracy = correct / tested if tested >= 3 else None
    current = detect_trend(history)
    current_pred = trend_strategy_decision(current, history)
    if not current_pred: return None
    weight = min(1.0, max(0.1, (accuracy - 0.45) * 4)) if accuracy is not None else 0.25
    return {"pred": current_pred, "accuracy": accuracy, "tested": tested, "weight": weight}

def predict_full(history):
    if len(history) < 12:
        return {"pred": history[0] if history else "T", "reason": "default",
                "tested": 0, "accuracy": None, "margin": 0,
                "trend": detect_trend(history), "trendAccuracy": None}
    trend = detect_trend(history)
    ens = ensemble_vote(history, ALGOS)
    tv = trend_strategy_vote(history)
    bt = backtest(history, 8, 40)
    if tv and tv["accuracy"] is not None and tv["accuracy"] > 0.55 and tv["tested"] >= 5:
        pred, reason = tv["pred"], "trend-" + trend["state"].lower()
    elif ens and ens["margin"] > 0.1:
        pred, reason = ens["pred"], "ensemble"
    elif trend["direction"] != "neutral" and trend["strength"] > 0.3:
        pred, reason = trend["direction"], "trend-follow"
    else:
        pred, reason = ("X" if history[0] == "T" else "T"), "flip-last"
    return {"pred": pred, "reason": reason, "tested": bt["tested"],
            "accuracy": bt["accuracy"], "margin": ens["margin"] if ens else 0,
            "trend": trend, "trendAccuracy": tv["accuracy"] if tv else None}

def compute_confidence(history, ctx):
    if not history or len(history) < 8:
        return {"conf": 50.0, "tier": "weak"}
    sample_score = min(1.0, len(history) / 80)
    reason = ctx.get("reason", "")
    if reason in ("trend-confirmed", "trend-extended"):
        primary = ctx["trend"]["strength"] if ctx.get("trend") else 0.3
    elif reason in ("trend-chaotic", "trend-building"):
        ta = ctx.get("trendAccuracy")
        primary = max(0.0, min(1.0, (ta - 0.45) * 4)) if ta is not None else 0.3
    elif reason in ("ensemble", "trend-follow"):
        margin_score = min(1.0, (ctx.get("margin") or 0) / 0.35)
        bt = ctx.get("accuracy")
        bt_score = max(0.0, min(1.0, (bt - 0.48) * 5)) if bt is not None else 0
        primary = 0.5 * margin_score + 0.5 * bt_score
    else:
        primary = 0.2
    streak = 1
    for i in range(1, len(history)):
        if history[i] == history[0]: streak += 1
        else: break
    streak_bonus = min(0.15, (streak - 1) * 0.03)
    s = min(1.0, 0.75 * primary + 0.25 * sample_score + streak_bonus)
    if s <= 0.4:
        conf, tier = 50 + (s / 0.4) * 12, "weak"
    elif s <= 0.7:
        conf, tier = 62 + ((s - 0.4) / 0.3) * 8, "moderate"
    else:
        conf, tier = 70 + ((s - 0.7) / 0.3) * 29, "strong"
    return {"conf": round(min(conf, 99.5), 1), "tier": tier}

def make_prediction_for_table(result_str: str):
    """Trả dict prediction cho 1 sàn, dựa vào result string từ API (oldest-first)."""
    history = result_to_history(result_str)
    current_session = len(result_str)  # đếm cả T
    next_session = current_session + 1
    latest_char = result_str[-1] if result_str else ""

    if not history:
        return None

    r = predict_full(history)
    c = compute_confidence(history, r)
    return {
        "next_session": next_session,
        "current_session": current_session,
        "latest_char": latest_char,
        "latest_label": result_char_label(latest_char),
        "pred": r["pred"],
        "pred_label": "Cái" if r["pred"] == "T" else "Con",
        "conf": c["conf"],
        "conf_tier": c["tier"],
        "accuracy": r["accuracy"],
        "reason": r["reason"],
        "history_len": len(history),
    }
