# Niyati & Palak Dual-Bot System

An advanced dual-bot Telegram system powered by AI (OpenAI, Groq, Gemini). Both bots can operate independently in private chats or collaboratively in group chats, interacting naturally like humans.

## Features
- **Independent Identities**: Niyati and Palak have their own distinct personalities.
- **Collaborative Group Presence**: They detect each other in groups and take turns organically without spamming.
- **Hybrid AI Engine**: Switch seamlessly between OpenAI, Groq, and Gemini. Supports API key rotation.
- **Unified Shared Memory**: In groups, both bots read from a shared transcript so they don't contradict each other or repeat answers.
- **Independent Rate Limiting**: Request limits are calculated securely per bot.
- **Supabase / SQLite Support**: Fully scalable PostgreSQL using Supabase, or zero-config local SQLite for testing.

## BotFather Setup
For both bots, talk to `@BotFather` on Telegram and ensure:
1. **Group Privacy**: `Disable` (so bots can read all group messages).
2. **Commands**: Set the following commands:
   ```
   start - Wake up the bot
   help - Show help menu
   about - Who am I?
   mood - Check current mood
   forget - Clear my memory
   grouphelp - Group commands
   ```

## Installation

1. Clone the repository and navigate to the directory:
   ```bash
   git clone <repo-url>
   cd Niyati-Palak-System
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure Environment Variables:
   - Copy `.env.example` to `.env`
   - Fill in your `NIYATI_BOT_TOKEN`, `PALAK_BOT_TOKEN` and their respective usernames.
   - Fill in your preferred AI API keys (`GROQ_API_KEYS`, `GEMINI_API_KEYS`, etc.).

4. Database Setup (Optional for Supabase):
   - If using Supabase, apply the SQL schema located in your database manager.
   - If `SUPABASE_URL` is left blank, the bot automatically creates a local SQLite database (`data.db`).

## Running the Bots

Run both bots simultaneously (they will run in the same process concurrently):
```bash
python main.py
```

If you only configure `NIYATI_BOT_TOKEN`, only Niyati will run. If you provide both, both will run collaboratively.
