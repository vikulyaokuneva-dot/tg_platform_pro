import os
import requests


BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")
CHAT_ID = os.getenv("AI_AUTOMATION_CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("POSTER_BOT_TOKEN not set")

if not CHAT_ID:
    raise RuntimeError("AI_AUTOMATION_CHAT_ID not set")


def send_post(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    response = requests.post(url, json=payload, timeout=10)

    if not response.ok:
        raise RuntimeError(
            f"Telegram API error {response.status_code}: {response.text}"
        )
