# Telegram Bot Example

This repository contains a simple Telegram bot implemented without third-party libraries. It demonstrates a user flow with persistent storage in SQLite and supports basic recovery of the dialogue state.

## Features
* Subscription check for a required channel
* Automatic sending of a free PDF guide to new subscribers
* Survey collecting name, grade, subjects, contact and phone
* Data stored in SQLite
* Placeholder step for payment handling

## Running
1. Set the environment variables:
   - `BOT_TOKEN` – your bot token from BotFather
   - `ADMIN_CHAT_ID` – chat ID to send survey results (optional)
   - `REQUIRED_CHANNEL_ID` – channel ID to verify subscription (optional)
2. Place `first_guide.pdf` and `paid_guide.pdf` in the project directory.
3. Start the bot:

```bash
python3 bot.py
```

The bot uses long polling and stores its state in `bot.db`.
