chat_id = CHANNELS.get(channel_key)

if not chat_id:
    print(f"[SKIP] Channel '{channel_key}' has no CHAT_ID")
    return None

msg = _bot.send_message(chat_id=chat_id, text=text)
return msg.message_id


_bot = Bot(token=POSTER_BOT_TOKEN)

def send_post(channel_key: str, text: str, parse_mode="HTML"):
    if channel_key not in CHANNELS:
        raise ValueError(f"Unknown channel: {channel_key}")
    chat_id = CHANNELS[channel_key]
    msg = _bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
    return msg.message_id
