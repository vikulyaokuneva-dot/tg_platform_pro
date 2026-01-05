# app/core/telegram.py

import requests
from app.core.config import POSTER_BOT_TOKEN


BASE_URL = f"https://api.telegram.org/bot{POSTER_BOT_TOKEN}"


def send_post(channel: str, text: str):
    """
    Отправка текстового сообщения
    """
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": channel,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    response = requests.post(url, json=payload)
    return response.json()


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
    """
    Закрепляет сообщение в канале
    """
    url = f"{BASE_URL}/pinChatMessage"
    payload = {
        "chat_id": channel,
        "message_id": message_id,
        "disable_notification": True,
    }
    response = requests.post(url, json=payload)
    return response.json()
