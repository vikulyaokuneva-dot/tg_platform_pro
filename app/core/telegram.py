from telegram import Bot
from app.core.config import POSTER_BOT_TOKEN, CHANNELS

_bot = Bot(token=POSTER_BOT_TOKEN)


def send_post(channel_key: str, text: str, parse_mode="HTML"):
    chat_id = CHANNELS.get(channel_key)

    if not chat_id:
        print(f"[SKIP] Channel '{channel_key}' has no CHAT_ID")
        return None

    msg = _bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=False,
    )

    return msg.message_id
