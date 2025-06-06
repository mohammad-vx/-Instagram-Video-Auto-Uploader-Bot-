# Instagram Video Auto-Uploader Bot 🤖

A Telegram bot for automatically uploading videos to Instagram.

## Features 🌟
- ✅ Automatic video uploading from Telegram to Instagram
- 📝 Uses filename or attached text as post caption
- 🔄 Manages video queue
- 📊 Detailed reports on each video's status
- 🔍 Automatic detection of new videos
- 🎯 Processes one video at a time

## Requirements 📋
```bash
pip install instagrapi requests python-dotenv
```

## Setup ⚙️
1. Modify the configuration variables at the beginning of the file:
```python
CONFIG = {
    'BOT_TOKEN': 'your_telegram_bot_token',
    'CHAT_ID': 'your_chat_id',
    'INSTAGRAM_USERNAME': 'your_instagram_username',
    'INSTAGRAM_PASSWORD': 'your_instagram_password',
}
```

2. Make sure you've created a Telegram bot and obtained its token.
3. Get your chat ID (CHAT_ID).
4. Enter your Instagram account details.

## Running the Bot 🚀
```bash
python instagram_uploader.py
```

## How to Use 📱
1. Send videos to the bot on Telegram.
2. The bot will automatically detect new videos.
3. One video will be uploaded each time you run the bot.
4. You will receive a report on the upload status and a link to the post.

## Notes 📝
- Videos must comply with Instagram's requirements.
- Ensure your login credentials are correct.
- The bot's state is saved in a local database.