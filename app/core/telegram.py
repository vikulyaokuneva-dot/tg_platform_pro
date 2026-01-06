# app/core/telegram.py

import requests
from app.core.config import POSTER_BOT_TOKEN


BASE_URL = f"https://api.telegram.org/bot{POSTER_BOT_TOKEN}"


def send_post(channel: str, text: str):
    response = requests.post(url, json=payload)
    data = response.json()

    if not data.get("ok"):
        print("TG ERROR send_post:", data)

    return data



def send_photo(channel: str, image: str, caption: str):
    """
    Отправка изображения с подписью
    """
    url = f"{BASE_URL}/sendPhoto"
    payload = {
        "chat_id": channel,
        "photo": image,
        "caption": caption,
        "parse_mode": "HTML",
    }
    response = requests.post(url, json=payload)
    return response.json()


def pin_message(channel: str, message_id: int):
    url = f"{BASE_URL}/pinChatMessage"
    payload = {
        "chat_id": channel,
        "message_id": message_id,
        "disable_notification": True,
    }
    if not is_pinned and channel and message_id:
    pin_message(channel=channel, message_id=message_id)
    state["pinned"] = True
    save_state(state)
    response = requests.post(url, json=payload)
    return response.json()
   
    
