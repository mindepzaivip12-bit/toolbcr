import asyncio
import logging
import time
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

from config import TELEGRAM_TOKEN, API_URL, FETCH_TIMEOUT, HTTP_MAX_RETRIES
from keys import validate_key, format_remain
from predictor import make_prediction_for_table, cmp_id

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

LIVE_INTERVAL = 10  # giây / lần refresh


# ============================================================
# BẢNG GIÁ
# ============================================================
PRICE_TABLE = (
    "💎 <b>BẢNG GIÁ KEY</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "⏱ 1 giờ  →  <b>15.000đ</b>\n"
    "📅 1 ngày →  <b>25.000đ</b>\n"
    "📅 3 ngày →  <b>45.000đ</b>\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "💳 Mua key IB: <b>@cskhleminh</b>"
)


# ============================================================
# HTTP FETCH API
# ============================================================
async def fetch_api():
    """Trả về (tables, last_update). Raise nếu thất bại."""
    last_err = None
    for attempt in range(HTTP_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
                r = await client.get(
                    API_URL,
                    params={"_t": int(time.time() * 1000)},
                    headers={"Cache-Control": "no-cache"},
                )
                r.raise_for_status()
                data = r.json()
                if not isinstance(data.get("data"), list):
                    raise ValueError("API data không hợp lệ")
                tables = [t for t in data["data"] if t.get("table") is not None]
                tables.sort(key=lambda x: cmp_id(x["table"], 0))
                return tables, data.get("lastUpdate")
        except Exception as e:
            last_err = e
            log.warning(f"Fetch API lỗi (lần {attempt + 1}): {e}")
            if attempt < HTTP_MAX_RETRIES:
                continue
    raise last_err or Exception("Fetch thất bại")


# ============================================================
# MENU BUILDERS
# ============================================================
def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Chọn game",  callback_data="menu_game")],
        [InlineKeyboardButton("📊 Dự đoán",    callback_data="menu_predict")],
        [InlineKeyboardButton("💎 Bảng giá",   callback_data="menu_price")],
        [InlineKeyboardButton("🔑 Đổi key",    callback_data="menu_changkey")],
        [InlineKeyboardButton(" Hướng dẫn",  callback_data="menu_help")],
    ])


def build_game_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎰 Baccarat",   callback_data="game_bcr")],
        [InlineKeyboardButton("⬅️ Quay lại",  callback_data="menu_main")],
    ])


def build_tables_menu(tables):
    kb, row = [], []
    for t in tables:
        tid = str(t["table"])
        row.append(InlineKeyboardButton(f"Sàn #{tid}", callback_data=f"tbl_{tid}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([
        InlineKeyboardButton(" Làm mới", callback_data="menu_predict"),
        InlineKeyboardButton(" Menu",    callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(kb)


def build_prediction_kb(table_id):
    # ⭐ THÊM nút "Chạy Live" - các nút còn lại giữ nguyên
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Chạy Live",     callback_data=f"live_on_{table_id}")],
        [InlineKeyboardButton("🔄 Cập nhật",      callback_data=f"tbl_{table_id}")],
        [InlineKeyboardButton("🎯 Chọn sàn khác", callback_data="menu_predict"),
         InlineKeyboardButton("   Menu",          callback_data="menu_main")],
    ])


def build_live_kb(table_id):
    # Bàn phím khi đang LIVE
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏹ Dừng Live",      callback_data=f"live_off_{table_id}")],
        [InlineKeyboardButton("🎯 Chọn sàn khác", callback_data="menu_predict"),
         InlineKeyboardButton("   Menu",          callback_data="menu_main")],
    ])


# ============================================================
# LIVE ENGINE
# ============================================================
_live_tasks: dict = {}  # {chat_id: asyncio.Task}


async def _get_prediction_text(tid: str) -> str:
    """Fetch + predict + format — GIỐNG HỆT text gốc, dùng chung cho live & thủ công."""
    tables, _ = await fetch_api()
    t = next((x for x in tables if str(x["table"]) == tid), None)
    if not t:
        raise ValueError(f"Không tìm thấy sàn #{tid}")
    pred = make_prediction_for_table(t.get("result", ""))
    if not pred:
        raise ValueError(f"Sàn #{tid} chưa có dữ liệu")

    pred_icon = "🔴" if pred["pred"] == "T" else "🔵"
    acc = pred.get("accuracy")
    acc_pct = f"{acc * 100:.1f}%" if acc is not None else "đang cập nhật"

    return (
        f"🐼 <b>Sàn #{tid}</b> · Baccarat\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎲 <b>Phiên #{pred['current_session']}</b> → Kết quả: <b>{pred['latest_label']}</b>\n"
        f"🎲 <b>Phiên #{pred['next_session']}</b> → Dự đoán: {pred_icon} <b>{pred['pred_label']}</b>\n"
        f"📊 Độ tin cậy: <b>{pred['conf']}%</b>\n"
        f"🎲 Chính xác : <b>{acc_pct}</b>"
    )


async def _stop_live_async(chat_id: int):
    entry = _live_tasks.pop(chat_id, None)
    if not entry:
        return
    task = entry
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def _start_live(bot, chat_id, message_id, tid, user_id, application):
    # Nếu đã có task cũ → cancel
    old = _live_tasks.pop(chat_id, None)
    if old:
        old.cancel()

    task = asyncio.create_task(
        _live_loop(bot, chat_id, message_id, tid, user_id, application)
    )
    _live_tasks[chat_id] = task


async def _live_loop(bot, chat_id, message_id, tid, user_id, application):
    log.info(f"🔴 LIVE start chat={chat_id} sàn=#{tid}")
    try:
        while True:
            # Kiểm tra key còn hạn không
            ud = application.user_data.get(user_id) or {}
            ki = ud.get("key_info")
            if not ki or ki.get("expire", 0) < int(time.time()):
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=(
                            "❌ Key đã hết hạn.\n"
                            "Nhập key mới: <code>/key &lt;key&gt;</code>\n\n"
                            f"{PRICE_TABLE}"
                        ),
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
                return

            # Cập nhật tin nhắn
            try:
                text = await _get_prediction_text(tid)
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=build_live_kb(tid),
                    parse_mode="HTML",
                )
            except Exception as e:
                s = str(e).lower()
                # text không đổi → bỏ qua, tiếp tục
                if "not modified" in s:
                    pass
                # tin nhắn bị xoá / không sửa được → dừng
                elif "not found" in s or "can't be edited" in s:
                    log.info(f"LIVE stop (message gone) sàn #{tid}")
                    return
                else:
                    log.debug(f"LIVE tick skip sàn #{tid}: {e}")

            await asyncio.sleep(LIVE_INTERVAL)
    except asyncio.CancelledError:
        pass
    except Exception:
        log.exception(f"LIVE loop crash sàn #{tid}")
    finally:
        log.info(f"⏹ LIVE end chat={chat_id} sàn=#{tid}")


# ============================================================
# COMMANDS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await _stop_live_async(update.effective_chat.id)   # dừng live nếu có

    if context.user_data.get("key_info"):
        ki = context.user_data["key_info"]
        remain = max(0, ki["expire"] - int(time.time()))
        await update.message.reply_text(
            f" CHÀO BẠN <b>{user.first_name}</b>!\n"
            f"🔑 Key còn: <b>{format_remain(remain)}</b>\n"
            f"🎮 Game: <b>{ki['game']}</b>",
            reply_markup=build_main_menu(),
            parse_mode="HTML",
        )
        return

    await update.message.reply_text(
        f" Xin chào <b>{user.first_name}</b>!\n\n"
        "🎰 <b>Bontools Baccarat </b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bạn cần nhập key để sử dụng bot.\n\n"
        f"{PRICE_TABLE}\n\n"
        " CÁCH SÀI KEY:\n"
        "<code>/key bcr-1h-1735689600-a1b2c3d4e5f6</code>\n\n"
        " Hỗ trợ: <b>@cskhleminh</b>",
        parse_mode="HTML",
    )


async def key_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _stop_live_async(update.effective_chat.id)   # dừng live nếu có
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Thiếu key.\n"
            "VD: <code>/key bcr-1h-1735689600-a1b2c3d4e5f6</code>\n\n"
            f"{PRICE_TABLE}",
            parse_mode="HTML",
        )
        return

    key = args[0].strip()
    ok, msg, info = validate_key(key)
    if not ok:
        await update.message.reply_text(
            f"{msg}\n\n{PRICE_TABLE}",
            parse_mode="HTML",
        )
        return

    context.user_data["key"] = key
    context.user_data["key_info"] = info
    context.user_data["game"] = info["game"]

    await update.message.reply_text(
        f"{msg}\n"
        f"🎮 Game: <b>{info['game']}</b>\n\n"
        "Chọn thao tác:",
        reply_markup=build_main_menu(),
        parse_mode="HTML",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        " 1 <b>Hướng dẫn</b>\n\n"
        " 2 /start — Bắt đầu\n"
        " 3 /key &lt;key&gt; — Nhập key\n"
        " 4 Chọn game → Chọn sàn → Xem dự đoán\n"
        " 5 Bấm 🔴 Chạy Live để tự cập nhật liên tục\n\n"
        "📊 <b>Bot dự đoán:</b>\n"
        "• Cái/Con cho phiên tiếp theo\n"
        "• Độ tin cậy %\n"
        "• Độ chính xác \n\n"
        f"{PRICE_TABLE}",
        parse_mode="HTML",
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    # ⭐ Dừng mọi phiên LIVE đang chạy của chat này trước khi xử lý callback mới
    await _stop_live_async(q.message.chat_id)

    # Chưa có key → chỉ cho quay về menu chính hoặc xem bảng giá
    if not context.user_data.get("key_info") and data not in ("menu_main", "menu_price"):
        await q.edit_message_text(
            "🔑 Bạn cần nhập key trước:\n<code>/key &lt;key&gt;</code>\n\n"
            f"{PRICE_TABLE}",
            parse_mode="HTML",
        )
        return

    ki = context.user_data.get("key_info")

    # Kiểm tra hạn key mỗi lần dùng
    if ki and data not in ("menu_changkey", "menu_price"):
        if ki["expire"] < int(time.time()):
            context.user_data.clear()
            await q.edit_message_text(
                "❌ Key đã hết hạn.\nNhập key mới: <code>/key &lt;key&gt;</code>\n\n"
                f"{PRICE_TABLE}",
                parse_mode="HTML",
            )
            return

    # ---------- BẢNG GIÁ ----------
    if data == "menu_price":
        kb_rows = []
        if ki:
            kb_rows.append([InlineKeyboardButton("⬅️ Menu", callback_data="menu_main")])
        await q.edit_message_text(
            PRICE_TABLE + "\n\n📩 Nhắn <b>@cskhleminh</b> để mua key ngay!",
            reply_markup=InlineKeyboardMarkup(kb_rows) if kb_rows else None,
            parse_mode="HTML",
        )
        return

    # ---------- MENU CHÍNH ----------
    if data == "menu_main":
        remain = max(0, ki["expire"] - int(time.time())) if ki else 0
        await q.edit_message_text(
            f"🏠 <b>Menu chính</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Key còn: <b>{format_remain(remain) if ki else '—'}</b>\n"
            f"🎮 Game: <b>{ki['game'] if ki else '—'}</b>",
            reply_markup=build_main_menu(),
            parse_mode="HTML",
        )
        return

    # ---------- HƯỚNG DẪN ----------
    if data == "menu_help":
        await q.edit_message_text(
            "ℹ️ <b>Hướng dẫn nhanh</b>\n\n"
            "1. Chọn game\n"
            "2. Chọn sàn\n"
            "3. Xem dự đoán\n"
            "4. Bấm 🔄 Cập nhật để refresh tay\n"
            "5. Bấm 🔴 Chạy Live để tự cập nhật liên tục",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Menu", callback_data="menu_main"),
            ]]),
            parse_mode="HTML",
        )
        return

    # ---------- ĐỔI KEY ----------
    if data == "menu_changkey":
        await q.edit_message_text(
            "🔑 Nhập key mới:\n<code>/key bcr-1h-...</code>",
            parse_mode="HTML",
        )
        return

    # ---------- CHỌN GAME ----------
    if data == "menu_game":
        await q.edit_message_text(
            "🎮 <b>Chọn game</b>",
            reply_markup=build_game_menu(),
            parse_mode="HTML",
        )
        return

    if data == "game_bcr":
        context.user_data["game"] = "bcr"
        await q.edit_message_text(
            "🐼 Đã chọn <b>Baccarat</b>\n\n"
            "Bấm 📊 Dự đoán để tải danh sách sàn.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Dự đoán", callback_data="menu_predict")],
                [InlineKeyboardButton("⬅️ Menu",    callback_data="menu_main")],
            ]),
            parse_mode="HTML",
        )
        return

    # ---------- TẢI DANH SÁCH SÀN ----------
    if data == "menu_predict":
        await q.edit_message_text("⏳ Đang tải danh sách sàn...")
        try:
            tables, _ = await fetch_api()
        except Exception as e:
            await q.edit_message_text(f"❌ Lỗi API: {e}")
            return
        if not tables:
            await q.edit_message_text("⚠️ API không trả về sàn nào.")
            return
        context.user_data["tables_cache"] = tables
        await q.edit_message_text(
            f"🎰 <b>Baccarat</b> · {len(tables)} sàn\n"
            "Chọn sàn để xem dự đoán:",
            reply_markup=build_tables_menu(tables),
            parse_mode="HTML",
        )
        return

    # ---------- DỰ ĐOÁN 1 SÀN (thủ công) ----------
    if data.startswith("tbl_"):
        tid = data[4:]
        await q.edit_message_text(f"⏳ Đang phân tích sàn #{tid}...")
        try:
            text = await _get_prediction_text(tid)
        except Exception as e:
            log.exception("predict error")
            await q.edit_message_text(f"❌ {e}")
            return
        await q.edit_message_text(
            text,
            reply_markup=build_prediction_kb(tid),
            parse_mode="HTML",
        )
        return

    # ---------- BẬT LIVE ----------
    if data.startswith("live_on_"):
        tid = data[len("live_on_"):]
        _start_live(
            context.bot,
            q.message.chat_id,
            q.message.message_id,
            tid,
            q.from_user.id,
            context.application,
        )
        return

    # ---------- TẮT LIVE (quay về khung dự đoán thủ công) ----------
    if data.startswith("live_off_"):
        tid = data[len("live_off_"):]
        # Live đã được stop ở đầu hàm
        try:
            text = await _get_prediction_text(tid)
        except Exception as e:
            await q.edit_message_text(f"❌ {e}")
            return
        await q.edit_message_text(
            text,
            reply_markup=build_prediction_kb(tid),
            parse_mode="HTML",
        )
        return


# ============================================================
# MAIN
# ============================================================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("key",   key_cmd))
    app.add_handler(CommandHandler("help",  help_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))

    log.info("🤖 Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
