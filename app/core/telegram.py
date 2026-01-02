from telegram import Bot
from app.core.config import POSTER_BOT_TOKEN, CHANNELS

_bot = Bot(token=POSTER_BOT_TOKEN)

def send_post(channel_key: str, text: str, parse_mode="HTML"):
    if channel_key not in CHANNELS:
        raise ValueError(f"Unknown channel: {channel_key}")
    chat_id = CHANNELS[channel_key]
    msg = _bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    return msg.message_id
