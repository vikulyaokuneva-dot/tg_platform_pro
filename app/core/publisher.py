# app/core/publisher.py

from app.core.telegram import send_post, send_photo, pin_message
from app.core.state import load_state, save_state
from app.content.fallback import get_fallback_image


def publish_job(name: str, job: dict):
    """
    Публикует один job в канал
    """

    channel = job.get("channel")
    builder = job.get("builder")

    if not callable(builder):
        raise TypeError(f"Builder for job '{name}' is not callable")

    state = load_state()
    is_pinned = state.get("pinned", False)

    # вызываем builder правильно
    result = builder(job)

    # отправка поста
    if isinstance(result, dict):
        text = result.get("text", "")
        image = result.get("image") or get_fallback_image(channel)
        message = send_photo(channel, image, text)
    else:
        message = send_post(channel, result)

    # безопасное извлечение message_id
    message_id = None
    if isinstance(message, dict):
        if "result" in message and isinstance(message["result"], dict):
            message_id = message["result"].get("message_id")
        else:
            message_id = message.get("message_id")

    # автозакреп
    if not is_pinned and channel and message_id:
        pin_message(channel=channel, message_id=message_id)
        state["pinned"] = True
        save_state(state)

    return message
