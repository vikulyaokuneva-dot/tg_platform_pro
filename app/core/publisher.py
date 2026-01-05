# app/core/publisher.py

from app.core.telegram import send_post, send_photo, pin_message
from app.core.state import load_state, save_state
from app.content.fallback import get_fallback_image


def publish_job(channel: str, builder):
    """
    Публикация поста в канал.
    Автоматически:
    - добавляет закреп, если его ещё нет
    - всегда публикует картинку (rss или fallback)
    """

    state = load_state()
    is_pinned = state.get("pinned", False)

    result = builder()

    text = result.get("text", "")
    image = result.get("image") or get_fallback_image(channel)

    # 1. Отправляем пост с фото
    message = send_photo(
        channel=channel,
        image=image,
        caption=text
    )

    # 2. Если закрепа ещё не было — закрепляем этот пост
    if not is_pinned:
        pin_message(channel=channel, message_id=message.message_id)
        state["pinned"] = True
        save_state(state)

    return message
