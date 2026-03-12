import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN   = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID    = int(os.environ.get("ADMIN_ID", "0"))   # your Telegram user ID
DATA_FILE   = "attendance.json"

# ConversationHandler state
WAITING_REASON = 1

# ── Data helpers ─────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"players": {}, "sessions": {}, "current_session": None}

def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def current_session(data: dict) -> dict | None:
    sid = data.get("current_session")
    return data["sessions"].get(sid) if sid else None

# ── Admin helpers ─────────────────────────────────────────────────────────────
def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

# ── Commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()

    uid = str(user.id)
    if uid not in data["players"]:
        data["players"][uid] = {"name": user.full_name, "username": user.username or ""}
        save_data(data)

    await update.message.reply_text(
        f"👋 Hey {user.first_name}! You're registered for Kabaddi attendance.\n\n"
        "You'll get a button in the group when training is scheduled.\n"
        "Use /attendance to check the current session anytime."
    )


async def new_session(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin only — /newsession 14 March 7:00 PM"""
    if not is_admin(update):
        await update.message.reply_text("⛔ Only the admin can create sessions.")
        return

    session_label = " ".join(ctx.args) if ctx.args else None
    if not session_label:
        await update.message.reply_text("Usage: /newsession 14 March 7:00 PM")
        return

    data = load_data()
    sid  = datetime.now().strftime("%Y%m%d%H%M%S")
    data["sessions"][sid] = {
        "label": session_label,
        "created_at": datetime.now().isoformat(),
        "attendance": {}     # uid -> {status, reason}
    }
    data["current_session"] = sid
    save_data(data)

    # Build inline keyboard
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Coming",     callback_data=f"attend|yes|{sid}"),
            InlineKeyboardButton("❌ Not Coming", callback_data=f"attend|no|{sid}"),
        ]
    ])

    await update.message.reply_text(
        f"🏉 *Training Session*\n📅 {session_label}\n\nAre you coming?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def attendance_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Anyone can call /attendance"""
    data = load_data()
    sess = current_session(data)

    if not sess:
        await update.message.reply_text("No session scheduled yet.")
        return

    lines = [f"📋 *Attendance — {sess['label']}*\n"]
    for uid, pinfo in data["players"].items():
        record = sess["attendance"].get(uid)
        name   = pinfo["name"]
        if not record:
            lines.append(f"⬜ {name} — No response")
        elif record["status"] == "yes":
            lines.append(f"✅ {name} — Coming")
        else:
            reason = record.get("reason", "—")
            lines.append(f"❌ {name} — Not Coming ({reason})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def edit_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Any player edits their own response — /edit"""
    data = load_data()
    sess = current_session(data)

    if not sess:
        await update.message.reply_text("No active session to edit.")
        return

    sid      = data["current_session"]
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Coming",     callback_data=f"attend|yes|{sid}"),
            InlineKeyboardButton("❌ Not Coming", callback_data=f"attend|no|{sid}"),
        ]
    ])
    await update.message.reply_text(
        f"✏️ Update your attendance for *{sess['label']}*:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def edit_player(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin edits another player — /editplayer @username"""
    if not is_admin(update):
        await update.message.reply_text("⛔ Only the admin can use this.")
        return

    if not ctx.args:
        await update.message.reply_text("Usage: /editplayer @username")
        return

    target_username = ctx.args[0].lstrip("@").lower()
    data = load_data()
    sess = current_session(data)

    if not sess:
        await update.message.reply_text("No active session.")
        return

    # Find player by username
    target_uid = None
    for uid, pinfo in data["players"].items():
        if pinfo.get("username", "").lower() == target_username:
            target_uid = uid
            break

    if not target_uid:
        await update.message.reply_text(f"Player @{target_username} not found. They must /start the bot first.")
        return

    sid      = data["current_session"]
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Coming",     callback_data=f"admin|yes|{sid}|{target_uid}"),
            InlineKeyboardButton("❌ Not Coming", callback_data=f"admin|no|{sid}|{target_uid}"),
        ]
    ])
    pname = data["players"][target_uid]["name"]
    await update.message.reply_text(
        f"✏️ Editing attendance for *{pname}* — {sess['label']}:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def add_player(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin manually adds a player by user ID — /addplayer <user_id> <Name>"""
    if not is_admin(update):
        await update.message.reply_text("⛔ Only the admin can use this.")
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage: /addplayer <user_id> Full Name")
        return

    uid  = ctx.args[0]
    name = " ".join(ctx.args[1:])
    data = load_data()
    data["players"][uid] = {"name": name, "username": ""}
    save_data(data)
    await update.message.reply_text(f"✅ Added {name} (ID: {uid})")


async def list_players(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Only the admin can use this.")
        return
    data = load_data()
    if not data["players"]:
        await update.message.reply_text("No players registered yet.")
        return
    lines = ["👥 *Registered Players*\n"]
    for uid, p in data["players"].items():
        uname = f"@{p['username']}" if p.get("username") else uid
        lines.append(f"• {p['name']} ({uname})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Callback: button presses ──────────────────────────────────────────────────

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    kind  = parts[0]

    data = load_data()

    # ── Player pressing their own button ──
    if kind == "attend":
        _, status, sid = parts
        uid = str(query.from_user.id)

        if sid != data.get("current_session"):
            await query.edit_message_text("⚠️ This session is no longer active.")
            return

        if uid not in data["players"]:
            await query.answer("Please send /start to the bot first in a private chat.", show_alert=True)
            return

        if status == "yes":
            data["sessions"][sid]["attendance"][uid] = {"status": "yes", "reason": ""}
            save_data(data)
            name = data["players"][uid]["name"]
            await query.answer(f"✅ Marked you as Coming, {name}!", show_alert=False)

        else:  # not coming — ask reason via DM
            ctx.user_data["pending_reason"] = {"sid": sid, "uid": uid}
            await query.answer("Please check your DM to give a reason.", show_alert=True)
            try:
                await ctx.bot.send_message(
                    chat_id=uid,
                    text="❓ What's the reason you can't make it? (just type and send)"
                )
            except Exception:
                await query.message.reply_text(
                    f"@{query.from_user.username or query.from_user.first_name} — please send /start to me in a private chat first so I can ask for your reason."
                )
        return

    # ── Admin editing another player ──
    if kind == "admin":
        _, status, sid, target_uid = parts

        if sid != data.get("current_session"):
            await query.edit_message_text("⚠️ This session is no longer active.")
            return

        if status == "yes":
            data["sessions"][sid]["attendance"][target_uid] = {"status": "yes", "reason": ""}
            save_data(data)
            name = data["players"][target_uid]["name"]
            await query.edit_message_text(f"✅ {name} marked as Coming.")
        else:
            ctx.user_data["pending_reason"] = {"sid": sid, "uid": target_uid, "admin": True}
            await query.edit_message_text("Type the reason for this player:")


# ── Conversation: collect reason text ────────────────────────────────────────

async def receive_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pending = ctx.user_data.get("pending_reason")
    if not pending:
        return  # not waiting for a reason from this user

    reason  = update.message.text.strip()
    sid     = pending["sid"]
    uid     = pending["uid"]

    data = load_data()
    if sid in data["sessions"]:
        data["sessions"][sid]["attendance"][uid] = {"status": "no", "reason": reason}
        save_data(data)

    ctx.user_data.pop("pending_reason", None)

    name = data["players"].get(uid, {}).get("name", uid)
    await update.message.reply_text(f"Got it! ❌ {name} — Not Coming: \"{reason}\"")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("newsession",  new_session))
    app.add_handler(CommandHandler("attendance",  attendance_cmd))
    app.add_handler(CommandHandler("edit",        edit_cmd))
    app.add_handler(CommandHandler("editplayer",  edit_player))
    app.add_handler(CommandHandler("addplayer",   add_player))
    app.add_handler(CommandHandler("listplayers", list_players))
    app.add_handler(CallbackQueryHandler(button_handler))

    # Catch plain text messages (for reason collection)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reason))

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
