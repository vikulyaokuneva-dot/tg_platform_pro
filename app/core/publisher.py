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

    result = builder(job)

    # result может быть строкой или dict
    if isinstance(result, dict):
        text = result.get("text", "")
        image = result.get("image") or get_fallback_image(channel)
        message = send_photo(channel, image, text)
    else:
        message = send_post(channel, result)

    # Автозакреп
    if not is_pinned and channel:
        pin_message(channel=channel, message_id=message["result"]["message_id"])
        state["pinned"] = True
        save_state(state)

    return message
