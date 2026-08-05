# Niyati & Palak Deva — Dual Telegram Bot System

Two AI-powered Telegram bots that can operate independently in private chats or collaborate naturally in group chats, interacting like real people.

## Features
- **Independent Identities**: Niyati and Palak Deva have their own distinct personalities, moods, and AI engine instances.
- **Collaborative Group Presence**: When both bots are in the same group, they detect each other and take turns organically using a deterministic coordinator. They never spam or loop endlessly.
- **Hybrid AI Engine**: Supports OpenAI, Groq, and Gemini with automatic failover and key rotation. Each bot has its own rotation state.
- **Shared Group Transcript**: In groups, both bots read from a shared in-memory transcript so they don't contradict each other.
- **Independent Rate Limiting**: Request cooldowns are tracked per `(bot_name, user_id)`.
- **Supabase + In-Memory Fallback**: Uses Supabase REST API for persistent storage. If not configured, data is kept in process memory (lost on restart).

## BotFather Setup

For **both** bots, talk to `@BotFather` on Telegram and configure:

1. **Group Privacy Mode**: Set to **Disabled** (`/setprivacy` → Disable). This is **required** so bots can read all group messages, not just commands and @mentions.
2. **Commands** (`/setcommands`):
   ```
   start - Wake up the bot
   help - Show help menu
   about - Who am I?
   mood - Check current mood
   forget - Clear my memory
   meme - Toggle memes on/off
   shayari - Toggle shayari on/off
   stats - Your personal stats
   grouphelp - Group commands
   ```

## Installation

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd Niyati-Kaviya-main
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your actual tokens and keys
   ```

4. Run:
   ```bash
   python main.py
   ```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `NIYATI_BOT_TOKEN` | Yes | Niyati's Telegram bot token |
| `PALAK_BOT_TOKEN` | No | Palak's token (omit to run Niyati only) |
| `NIYATI_BOT_USERNAME` | No | Niyati's @username (default: `Niyati_personal_bot`) |
| `PALAK_BOT_USERNAME` | No | Palak's @username (default: `palakdevabot`) |
| `GROQ_API_KEYS` | At least one AI key | Comma-separated Groq API keys |
| `GEMINI_API_KEYS` | At least one AI key | Comma-separated Gemini API keys |
| `OPENAI_API_KEYS` | At least one AI key | Comma-separated OpenAI API keys |
| `SUPABASE_URL` | No | Supabase project URL |
| `SUPABASE_KEY` | No | Supabase service role key |
| `ADMIN_IDS` | No | Comma-separated Telegram user IDs for admin commands |

## Database

**With Supabase**: The bot uses Supabase REST API. Required tables: `users`, `groups`, `activities`, `group_fsub_map`. Create them in your Supabase SQL editor.

**Without Supabase**: Data is stored in process memory using Python dicts. All data is **lost on restart**. There is no SQLite fallback.

### Migration Note (bot_name isolation)
A database migration is **mandatory** to upgrade the schema for dual-bot isolation. This will safely add the `bot_name` column, preserve data, and enforce `(bot_name, user_id)` uniqueness.

**Supabase SQL Editor Steps:**
1. Open the Supabase dashboard for your project.
2. Navigate to the **SQL Editor** tab.
3. Open the file `migrations/001_add_bot_name_to_users.sql` from this repository.
4. Copy the entire contents of the file and paste it into the SQL Editor.
5. Click **Run** to execute the migration.

## Bot-to-Bot Communication

When both bots are in the same group:
- A **deterministic coordinator** decides who responds to each message using a seeded random generator (`chat_id:message_id:sender_id`).
- Replies to a specific bot guarantee that bot responds.
- Bot-to-bot reactions are limited (default: max 3 total bot replies per human message, max 1 consecutive).
- Both bots share a transcript so they know what the other said.
- If only one bot is present in a group, it operates normally without waiting for the other.
