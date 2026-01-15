import os
import requests


BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")
CHAT_ID = os.getenv("AI_AUTOMATION_CHAT_ID")


def publish(content: dict):
    """
    content = {
        "title": str,
        "text": str,
        "image": str | None
    }
    """

    if not BOT_TOKEN or not CHAT_ID:
        print("[ERROR] Telegram credentials not set")
        return

    title = content.get("title", "").strip()
    text = content.get("text", "").strip()
    image = content.get("image")

    if not title or not text:
        print("[SKIP] empty title or text")
        return

    message = f"🤖 {title}\n\n{text}"

    # --- если есть картинка ---
    if image:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "caption": message,
            "parse_mode": "HTML",
        }
        files = {
            "photo": image
        }
    else:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }
        files = None

    response = requests.post(url, data=payload, files=files, timeout=20)

    if response.status_code != 200:
        print("[ERROR] Telegram API:", response.text)
    else:
        print("[TELEGRAM] message sent")
