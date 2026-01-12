import os
import requests
from typing import Optional, Dict

BOT_TOKEN = os.getenv("POSTER_BOT_TOKEN")
CHAT_ID = os.getenv("AI_AUTOMATION_CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("POSTER_BOT_TOKEN не задан в secrets")

if not CHAT_ID:
    raise RuntimeError("AI_AUTOMATION_CHAT_ID не задан в secrets")


def send_text(text: str):
    """Отправить простой текстовый пост."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload)
    if not resp.ok:
        raise RuntimeError(f"Ошибка Telegram API: {resp.status_code} — {resp.text}")


def send_photo(photo_url: str, caption: str):
    """Отправить фото с подписью."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    payload: Dict[str, str] = {
        "chat_id": CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    resp = requests.post(url, json=payload)
    if not resp.ok:
        raise RuntimeError(f"Ошибка Telegram API (photo): {resp.status_code} — {resp.text}")


def _build_caption(text: str) -> str:
    """Короткое содержание для поста (ограничение до ~1024 символов)."""
    # сократить до 800 символов, сохраняя целые предложения
    limit = 800
    if len(text) <= limit:
        return text

    part = text[:limit]
    # обрезаем по последней точке, чтобы не обрывать смысл
    idx = part.rfind(".")
    if idx > 0:
        part = part[:idx+1]
    return part + " …"


def send_post(payload: Dict[str, Optional[str]]):
    """
    payload должен быть:
    {
       "title": str,
       "text": str,
       "image": Optional[str]
    }
    """
    title = payload.get("title", "").strip()
    text = payload.get("text", "").strip()
    image = payload.get("image")

    if not text and not title:
        # нет содержимого — пропустить
        return

    caption = title
    # добавляем краткую смысловую часть
    if text:
        caption += "\n\n" + _build_caption(text)

    # если есть изображение — публикуем как фото
    if image:
        try:
            send_photo(image, caption)
        except Exception:
            # fallback: если фото не удалось отправить, отправляем как текст
            send_text(caption)
    else:
        send_text(caption)
