# 🏉 Kabaddi Attendance Bot

## Setup

### 1. Create the bot
- Message @BotFather on Telegram → `/newbot`
- Copy the **Bot Token**

### 2. Get your Telegram User ID
- Message @userinfobot on Telegram
- Copy your **User ID** (this is your ADMIN_ID)

### 3. Add bot to your group
- Add the bot to your Kabaddi group
- Make it an **admin** (so it can send messages)

### 4. Deploy to Railway (free)
1. Push this folder to a GitHub repo
2. Go to railway.app → New Project → Deploy from GitHub
3. Set environment variables:
   - `BOT_TOKEN` = your bot token
   - `ADMIN_ID`  = your Telegram user ID

### 5. Each player must /start the bot once
- Share the bot link (t.me/yourbotname) with the team
- Everyone sends `/start` once in private — this registers them

---

## Commands

| Command | Who | What it does |
|---|---|---|
| `/newsession 14 March 7PM` | Admin | Creates session, posts group message with buttons |
| `/attendance` | Anyone | Shows full attendance list |
| `/edit` | Any player | Re-prompts their own attendance buttons |
| `/editplayer @username` | Admin | Changes attendance for any player |
| `/addplayer <id> Name` | Admin | Manually register a player |
| `/listplayers` | Admin | See all registered players |

---

## Flow

```
Admin: /newsession 14 March 7:00 PM

[Group chat]
Bot: 🏉 Training Session
     📅 14 March 7:00 PM
     Are you coming?
     [✅ Coming]  [❌ Not Coming]

Players tap ✅ → recorded silently
Players tap ❌ → Bot DMs them asking for reason

Anyone: /attendance
Bot: 📋 Attendance — 14 March 7:00 PM
     ✅ Ravi — Coming
     ❌ Priya — Not Coming (out of town)
     ⬜ Arun — No response
```
