# app/content/rss.py

from app.content.fallback import get_fallback_image


def build_rss_post(channel: str, item: dict) -> dict:
    """
    Собирает пост из RSS.
    Если в RSS нет картинки — берём fallback.
    """

    text = item.get("title", "")
    link = item.get("link", "")
    image = item.get("image") or get_fallback_image(channel)

    return {
        "text": f"{text}\n\n{link}",
        "image": image
    }
