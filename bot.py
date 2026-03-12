import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID  = int(os.environ.get("ADMIN_ID", "0"))
DATA_FILE = "attendance.json"

# ── Data helpers ──────────────────────────────────────────────────────────────
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

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

# ── Build live attendance message ─────────────────────────────────────────────
def build_attendance_message(data: dict, sid: str) -> tuple[str, InlineKeyboardMarkup]:
    sess = data["sessions"][sid]
    lines = [f"🏉 *Training — {sess['label']}*\n"]

    coming, not_coming, no_response = [], [], []

    for uid, pinfo in data["players"].items():
        record = sess["attendance"].get(uid)
        name   = pinfo["name"]
        if not record:
            no_response.append(f"⬜ {name}")
        elif record["status"] == "yes":
            coming.append(f"✅ {name}")
        else:
            reason = record.get("reason") or "—"
            not_coming.append(f"❌ {name} _{reason}_")

    all_rows = coming + not_coming + no_response
    lines.append("\n".join(all_rows) if all_rows else "_No players registered yet_")

    total = len(data["players"])
    lines.append(f"\n✅ {len(coming)}  ❌ {len(not_coming)}  ⬜ {len(no_response)}/{total}")

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Coming",     callback_data=f"attend|yes|{sid}"),
        InlineKeyboardButton("❌ Not Coming", callback_data=f"attend|no|{sid}"),
    ]])

    return "\n".join(lines), keyboard

# ── Edit the live group message ───────────────────────────────────────────────
async def refresh_attendance_message(ctx: ContextTypes.DEFAULT_TYPE, data: dict, sid: str):
    sess       = data["sessions"][sid]
    chat_id    = sess.get("chat_id")
    message_id = sess.get("message_id")
    if not chat_id or not message_id:
        return
    text, keyboard = build_attendance_message(data, sid)
    try:
        await ctx.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Could not refresh attendance message: {e}")

# ── Commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid  = str(user.id)
    if uid not in data["players"]:
        data["players"][uid] = {"name": user.full_name, "username": user.username or ""}
        save_data(data)
    await update.message.reply_text(
        f"👋 Hey {user.first_name}! You're registered for Kabaddi attendance.\n\n"
        "When a session is posted in the group, tap your button there to mark attendance."
    )


async def new_session(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/newsession 14 March 7:00 PM — Admin only"""
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
        "label":      session_label,
        "created_at": datetime.now().isoformat(),
        "attendance": {},
        "chat_id":    None,
        "message_id": None,
    }
    data["current_session"] = sid
    save_data(data)

    text, keyboard = build_attendance_message(data, sid)
    sent = await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # Save message ref so we can edit it on every update
    data["sessions"][sid]["chat_id"]    = sent.chat_id
    data["sessions"][sid]["message_id"] = sent.message_id
    save_data(data)

    # Pin it so it stays visible at the top
    try:
        await ctx.bot.pin_chat_message(
            chat_id=sent.chat_id,
            message_id=sent.message_id,
            disable_notification=True
        )
    except Exception:
        pass  # bot may not have pin permission — not critical


async def edit_player(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/editplayer @username — Admin only"""
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

    target_uid = next(
        (uid for uid, p in data["players"].items()
         if p.get("username", "").lower() == target_username),
        None
    )
    if not target_uid:
        await update.message.reply_text(f"@{target_username} not found. They must /start the bot first.")
        return

    sid      = data["current_session"]
    pname    = data["players"][target_uid]["name"]
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Coming",     callback_data=f"admin|yes|{sid}|{target_uid}"),
        InlineKeyboardButton("❌ Not Coming", callback_data=f"admin|no|{sid}|{target_uid}"),
    ]])
    await update.message.reply_text(
        f"✏️ Editing *{pname}* for {sess['label']}:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def add_player(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/addplayer <user_id> Full Name — Admin only"""
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
    """/listplayers — Admin only"""
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


# ── Button handler ────────────────────────────────────────────────────────────

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    kind  = parts[0]
    data  = load_data()

    if kind == "attend":
        _, status, sid = parts
        uid = str(query.from_user.id)

        if sid != data.get("current_session"):
            await query.answer("⚠️ This session is no longer active.", show_alert=True)
            return
        if uid not in data["players"]:
            await query.answer("Please send /start to the bot in a private chat first.", show_alert=True)
            return

        if status == "yes":
            data["sessions"][sid]["attendance"][uid] = {"status": "yes", "reason": ""}
            save_data(data)
            await query.answer("✅ Marked as Coming!", show_alert=False)
            await refresh_attendance_message(ctx, data, sid)

        else:
            # Record as not coming with empty reason, then ask for reason via DM
            data["sessions"][sid]["attendance"][uid] = {"status": "no", "reason": ""}
            save_data(data)
            ctx.user_data["pending_reason"] = {"sid": sid, "uid": uid}
            await query.answer("Check your DM to give a reason.", show_alert=True)
            try:
                await ctx.bot.send_message(
                    chat_id=uid,
                    text="❓ What's the reason you can't make it? (just type and send)"
                )
            except Exception:
                await query.message.reply_text(
                    f"@{query.from_user.username or query.from_user.first_name} — "
                    "please send /start to me privately first so I can collect your reason."
                )
            await refresh_attendance_message(ctx, data, sid)

    elif kind == "admin":
        _, status, sid, target_uid = parts

        if sid != data.get("current_session"):
            await query.answer("⚠️ This session is no longer active.", show_alert=True)
            return

        if status == "yes":
            data["sessions"][sid]["attendance"][target_uid] = {"status": "yes", "reason": ""}
            save_data(data)
            name = data["players"][target_uid]["name"]
            await query.edit_message_text(f"✅ {name} marked as Coming.")
            await refresh_attendance_message(ctx, data, sid)
        else:
            ctx.user_data["pending_reason"] = {"sid": sid, "uid": target_uid, "admin": True}
            await query.edit_message_text("Type the reason for this player:")


# ── Receive reason via DM ─────────────────────────────────────────────────────

async def receive_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pending = ctx.user_data.get("pending_reason")
    if not pending:
        return

    reason = update.message.text.strip()
    sid    = pending["sid"]
    uid    = pending["uid"]

    data = load_data()
    if sid in data["sessions"]:
        data["sessions"][sid]["attendance"][uid] = {"status": "no", "reason": reason}
        save_data(data)

    ctx.user_data.pop("pending_reason", None)

    name = data["players"].get(uid, {}).get("name", uid)
    await update.message.reply_text(f"Got it! ❌ {name} — Not Coming: \"{reason}\"")

    # Update the live group message with the reason filled in
    await refresh_attendance_message(ctx, data, sid)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",       start))
    app.add_handler(CommandHandler("newsession",  new_session))
    app.add_handler(CommandHandler("editplayer",  edit_player))
    app.add_handler(CommandHandler("addplayer",   add_player))
    app.add_handler(CommandHandler("listplayers", list_players))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reason))

    logger.info("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
